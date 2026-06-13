# Design Document — LMSR Prediction Market Platform

**Internal Forecasting & Calibration Tool**

> **Primary source of truth for this project.** All major architectural, mathematical, and data-model decisions should be traceable to this document.

- **Origin**: Design conversation exported from https://claude.ai/share/b4580732-4d55-4ba0-8177-063a5f6d0527 (May 2025, Bob + Claude)
- **Current implementation**: Python prototype in `src/lmsr/` (`BinaryLMSRMarket`, `LMSRMarketSimulator`, scoring, persistence, leaderboard)
- **Purpose**: Educational/research-grade internal tool for exploring prediction markets, liquidity effects (`b`), Kelly-style position sizing, and forecaster calibration — **not** a public blockchain platform.

---

## 1. Goals & Non-Goals

### Goals
- Numerically stable, mathematically rigorous **binary LMSR** markets.
- Play-money balances with proper double-entry-style accounting.
- First-class **calibration scoring** (Brier + Log + Murphy decomposition) attached to individual trades.
- Immutable append-only trade log; all other state (positions, P/L) is **derived**.
- Easy experimentation with liquidity parameter `b` (1–1500 range in current UI/examples).
- Strong invariants: accounting identity after resolution, replayability of any market from its trade history.

### Non-Goals (at least in v1)
- Real-money / crypto settlement.
- High-scale public platform.
- Order-book matching or complex combinatorial markets.
- Dynamic/adaptive `b` (documented as future work).
- Multi-outcome or scalar markets (binary first).

---

## 2. Why LMSR for an Internal Tool

After evaluating options (CPMM / Uniswap-style, order books, parimutuel, dynamic parimutuel, fixed-odds, pure scoring rules), **LMSR was chosen** for internal / thin-market use cases.

**Key reasons**
- Bounded worst-case loss for the market maker: `b · ln(2)` for binary markets (important when the organization controls the subsidy).
- Prices are always a valid probability distribution (softmax).
- Single intuitive knob `b` controls price sensitivity vs. subsidy cost.
- Clean theoretical connection to proper scoring rules and Bayesian updating.
- Works well with very low participation — exactly the regime of most internal forecasting tools.

**Comparison of mechanisms (from the design conversation)**

| Mechanism       | Liquidity Needed | Price Quality | Complexity | Best For                  |
|-----------------|------------------|---------------|------------|---------------------------|
| LMSR (subsidized) | None            | Very good     | Medium     | Internal / thin markets   |
| CPMM            | LP deposit       | Good          | Low        | Crypto / community        |
| Order Book (CLOB) | High           | Best          | High       | Large liquid public markets |
| Parimutuel      | None             | Poor (final only) | Low     | Simple pools              |
| Pure Scoring (Metaculus-style) | None     | N/A           | Low        | Direct probability reporting |

**Decision**: Start with **binary LMSR, fixed `b` per market**, play money, 2.5% asymmetric fee. Add dynamic `b`, multi-outcome, etc., later.

---

## 3. Mathematical Foundation (LMSR)

### Cost Function
```
C(q) = b · ln( Σ exp(qᵢ / b) )
```
where `q = [q_yes, q_no]` = outstanding shares in each outcome.

### Prices
```
p_yes = exp(q_yes / b) / (exp(q_yes / b) + exp(q_no / b))
p_no  = 1 − p_yes
```
Prices are the softmax of the share vector (always sum to 1).

### Cost of a Trade
Naïve `C(q + Δq) − C(q)` suffers from catastrophic cancellation on small trades. The implementation uses the algebraically equivalent stable form:
```
ΔC = b · ln( Σ pᵢ · exp(Δqᵢ / b) )
```
where `pᵢ` are the prices *before* the trade (see `market.py:_raw_cost_delta`).

### Bounded Loss
For binary markets the market maker’s worst-case loss is `b · ln(2) ≈ 0.693b`.

### Numerical Stability Techniques (Implemented)
- Stable log-sum-exp (`_lse`) via `numpy.logaddexp`.
- Stable softmax for prices (`_stable_prices`).
- The `ΔC` identity above.
- All monetary quantities use `float` (Python) / `NUMERIC(20,8)` in any future SQL schema; never `float` for balances in production accounting.

References in the original conversation: log-sum-exp trick, catastrophic cancellation, resolution math.

---

## 4. Data Model

### Current Implementation (Python Dataclasses)

See `src/lmsr/simulator.py`:

- `Trade` — immutable record (id, market_id, user_id, shares_yes/no, raw_cost, fee, effective_cost, price_after, market_q_after, timestamp)
- `Payout` — one per user per resolved market
- `Score` — per-trade Brier + log score recorded at resolution time
- `Market` — metadata + `BinaryLMSRMarket` engine + lists of trades/payouts/scores + status
- `User` — id, balance (default 1000), display_name
- `UserPortfolio` — aggregated view across all markets (positions, realized PnL, counts)
- `LMSRMarketSimulator` — multi-market orchestrator, position cache, leaderboard, optional SQLite persistence (db_path) + legacy pickle support

**Important invariant**: Positions are always **recomputed** from the trade log (`_recompute_positions`). The engine also maintains its own `user_positions` only for the “insufficient shares to sell” guard.

### Reference SQL Schema (Future / Production)

The following is the canonical DDL discussed in the design conversation (lightly cleaned for readability).

```sql
CREATE TABLE users (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    display_name  TEXT,
    balance       NUMERIC(20,8) NOT NULL DEFAULT 1000,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE markets (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    title               TEXT NOT NULL,
    description         TEXT,
    resolution_criteria TEXT,
    b                   NUMERIC(10,4) NOT NULL,           -- liquidity parameter
    fee_rate            NUMERIC(5,4) NOT NULL DEFAULT 0.025,
    initial_subsidy     NUMERIC(20,8) NOT NULL DEFAULT 0,
    status              TEXT NOT NULL DEFAULT 'open',     -- open / closed / resolved
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    close_at            TIMESTAMPTZ,
    resolved_at         TIMESTAMPTZ,
    resolution_outcome  TEXT
);

CREATE TABLE trades (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    market_id         UUID NOT NULL REFERENCES markets(id),
    user_id           UUID NOT NULL REFERENCES users(id),
    shares_yes        NUMERIC(20,8) NOT NULL,
    shares_no         NUMERIC(20,8) NOT NULL,
    raw_cost          NUMERIC(20,8) NOT NULL,
    fee               NUMERIC(20,8) NOT NULL,
    effective_cost    NUMERIC(20,8) NOT NULL,
    price_after_yes   NUMERIC(10,8) NOT NULL,
    price_after_no    NUMERIC(10,8) NOT NULL,
    q_after_yes       NUMERIC(20,8) NOT NULL,
    q_after_no        NUMERIC(20,8) NOT NULL,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);
-- Immutable append-only audit log

CREATE TABLE payouts (
    market_id   UUID NOT NULL REFERENCES markets(id),
    user_id     UUID NOT NULL REFERENCES users(id),
    amount      NUMERIC(20,8) NOT NULL,
    outcome     TEXT NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (market_id, user_id)
);

CREATE TABLE scores (
    market_id       UUID NOT NULL REFERENCES markets(id),
    user_id         UUID NOT NULL REFERENCES users(id),
    trade_id        UUID NOT NULL REFERENCES trades(id),
    forecast_prob   NUMERIC(10,8) NOT NULL,   -- price_after_yes at trade time
    outcome         NUMERIC(3,2),             -- 1.0 or 0.0 after resolution
    brier_score     NUMERIC(10,8),
    log_score       NUMERIC(10,8),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (market_id, trade_id)
);
```

**Positions** table (optional materialized view — always recomputable from `trades`):

```sql
CREATE TABLE positions (
    user_id    UUID NOT NULL,
    market_id  UUID NOT NULL,
    outcome    TEXT NOT NULL,           -- 'yes' or 'no'
    shares     NUMERIC(20,8) NOT NULL,
    PRIMARY KEY (user_id, market_id, outcome)
);
```

### The Critical Accounting Invariant

From the design conversation:

```sql
CREATE VIEW market_accounting AS
SELECT
    m.id,
    m.initial_subsidy AS subsidy,
    COALESCE(SUM(t.effective_cost), 0) AS total_revenue,
    COALESCE(SUM(p.amount), 0)         AS total_paid_out,
    m.initial_subsidy
      + COALESCE(SUM(t.effective_cost), 0)
      - COALESCE(SUM(p.amount), 0)     AS remainder
FROM markets m
LEFT JOIN trades t ON t.market_id = m.id
LEFT JOIN payouts p ON p.market_id = m.id
GROUP BY m.id, m.initial_subsidy;
```

**Implementation note** (current Python): `simulator.check_accounting_identity()` verifies:
1. `total_payouts_recorded == engine.q[winning]` (the hard correctness check).
2. Surfaces `remainder` for diagnostics.

`remainder` is the market maker’s net P/L on that market and is **not** required to be exactly zero (LMSR has a random but bounded P/L). The view exists to detect implementation bugs (double payouts, missing revenue, etc.).

---

## 5. Core Operations

### Trade Flow (Atomic in a real DB)
1. Lock market + relevant outcome rows.
2. Compute cost via stable LMSR engine (`quote`).
3. Check user balance (for positive cost) and current position (cannot go negative on either side).
4. Execute: update `q`, update engine `user_positions`, add to `total_revenue`.
5. Insert immutable `Trade` row (denormalized `price_after`, `q_after` for cheap charting/scoring).
6. Debit/credit user balance.
7. Insert stub `Score` row (scores filled at resolution).

The Python simulator mirrors this with `place_trade` + append to `Market.trades`.

### Resolution
- Admin (or automated job) calls `resolve_market(market_id, "yes"|"no")`.
- Payouts created for every user who holds winning-side shares (`amount = shares_on_winning`).
- Balances credited.
- Per-trade `Score` rows populated using the price at the moment of the trade (`price_after_yes`).
- Accounting identity check run automatically; warning attached to result if payout records are inconsistent.
- Market status → `resolved`.

Resolution is deliberately simple for binary case: a winning share redeems for exactly 1.0 unit.

---

## 6. Scoring Layer

This was repeatedly called “the most mathematically interesting part for an internal tool.”

### Proper Scoring Rules
- **Brier** (quadratic, intuitive): `(p − o)²`
- **Log** (information-theoretic, harsher on overconfidence): `o·log(p) + (1−o)·log(1−p)`

Both are **proper** — truthful reporting is optimal.

### Murphy Decomposition (1973)
```
Brier = Reliability − Resolution + Uncertainty
```
- **Reliability** (lower better): how well stated probs match observed frequencies.
- **Resolution** (higher better): how much information the forecaster adds beyond the base rate.
- **Uncertainty**: base-rate variance (fixed for a set of markets).

Extremely useful for diagnosing forecasters (see `scoring.py:brier_decomposition` and `ForecasterScores`).

### What Gets Scored
In a trading market we score the **price after each individual trade** (the trader’s revealed belief at the moment they acted). This is stored in the `Score.forecast_prob` column and is the cleanest incentive-compatible choice.

Leaderboards (`get_leaderboard`) support sorting by average Brier, average log score, or total realized PnL, with a minimum-trade filter.

---

## 7. Current Prototype Architecture (`src/lmsr/`)

```
market.py      — Pure LMSR engine (BinaryLMSRMarket)
                 Numerically hardened price / cost / quote / trade / resolve
scoring.py     — Pure functions: brier_score, log_score, brier_decomposition, ForecasterScores
simulator.py   — Application layer
                 • LMSRMarketSimulator (multi-market)
                 • Immutable Trade / Payout / Score records
                 • Derived positions + UserPortfolio
                 • Global leaderboard
                 • Accounting identity check
                 • Optional SQLite persistence (db_path) + legacy pickle support + replay
```

Examples and the Streamlit app (`app.py`) consume this API.

Trade histories in `examples/trade_histories/` are JSON (simple `{user, yes, no}` arrays) and are replayed for `b`-sensitivity studies and rug-pull analysis.

---

## 8. Open Items / Future Evolution

This section captures the currently identified directions for evolving the system beyond the current in-memory research simulator.

### API & Integration
- **Agent / Bot API** — Expose a clean, stable, and well-documented API that allows external agents and automated trading bots to participate in markets. This API should support both fixed-b and adaptive-b markets and enable large-scale simulations, reinforcement learning agents, Kelly-based strategies, and market-making bots.

### Architecture & Deployment
- **Backend / Frontend Separation** — Introduce a proper API layer (FastAPI is the leading candidate) to decouple the simulation engine from any user interface. This enables multiple frontends and clearer separation of concerns.
- **Professional Web Demo** — Build a production-quality demonstration using a Python (FastAPI) backend that wraps the existing engine, paired with a modern Node.js frontend (e.g. React/Next.js). The goal is a professional-looking interface suitable for internal stakeholders while preserving the Python core as the single source of truth. Long-term, this path may lead to retiring or de-emphasizing the current Streamlit application.

### Data Persistence Layer
- **Robust SQL Database Backend** — Move from the current in-memory + pickle model to a production-grade SQL database (PostgreSQL) with proper schema, transactions, concurrency control (row-level or optimistic locking), migrations, and full support for users, balances, trades, payouts, and scores. This is a prerequisite for real-world trading scenarios.
- **Internal Blockchain for Audit Trails (Exploratory / Low Priority)** — Investigate the use of a strictly internal (private/permissioned) blockchain or hash-chained ledger to provide tamper-proof, verifiable audit trails for trades, balance changes, and resolutions. This component must remain completely invisible from outside the system and is currently considered low-priority research.

### Other Open Items
- **Dynamic `b`** — Basic support for adaptive/liquidity-sensitive `b` now exists via `src/lmsr/adaptive.py`. Further research into effective default strategies and their theoretical properties remains valuable.
- Multi-outcome and scalar markets.
- Proper JSON (de)serialization of histories and full simulator state (in addition to pickle).
- Richer calibration visualizations (e.g., reliability diagrams).
- Kelly-criterion position-sizing helpers exposed in the public API.
- Admin capabilities for market creation and resolution.

---

## 9. References & Further Reading

- Robin Hanson, “Logarithmic Market Scoring Rules for Modular Combinatorial Information Aggregation” (2002).
- Othman, Pennock, Reeves, Sandholm — “Practical Liquidity-Sensitive Automated Market Making” (2013).
- Murphy (1973) — Brier score decomposition.
- DESIGN.md (this file) and the original Claude transcript (git history) for the full dialogue.

---

**End of synthesized design document.**

> The raw exported chat transcript that originally populated this file has been replaced by the structured version above for readability and long-term maintainability. The original conversational material remains in the git history for provenance.
