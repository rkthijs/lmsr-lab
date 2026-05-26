# AGENTS.md — Project Steering File

This file provides guidance for AI agents (and human contributors) working in this repository. It will evolve as the project grows.

## Project Overview

**LMSR Prediction Market Engine** (core of an internal company forecasting / prediction market tool)

This repository implements the mathematical heart of a prediction market system as detailed in the primary design conversation:

**Primary source of truth**: [DESIGN.md](./DESIGN.md) — full transcript of the detailed design discussion covering LMSR vs other mechanisms, numerical stability, resolution accounting, calibration scoring (Brier + log score), dynamic liquidity, database schema, atomic trade execution, and the long-term vision for an internal tool.

The current focus is a high-quality, numerically stable **BinaryLMSRMarket** engine that can later be embedded into a larger system (DB-backed API, scoring layer, UI, etc.).

Key properties implemented (per the spec):
- LMSR cost function with log-sum-exp stability (`np.logaddexp`)
- Configurable liquidity parameter `b`
- Separate user position ledger (enforces non-negative holdings)
- Built-in market-maker fee
- Instantaneous impact + slippage preview (critical for good UX)
- Resolution with market-maker P/L and accounting identity
- Play-money friendly (easy to add real balances later)

**Core math reference** (from the conversation):
- `C(q) = b · ln(Σ exp(qᵢ / b))`
- Prices via stable softmax
- Trade cost computed to avoid catastrophic cancellation on small deltas

**Current maturity**: Solid, tested-in-practice core LMSR engine + Streamlit prototype. Full system (DB schema, calibration leaderboard, API, multi-outcome, dynamic b) is the longer-term target described in `DESIGN.md`.

## Repository Layout

```
/home/bob/Projects/test
├── DESIGN.md              # PRIMARY DESIGN SOURCE — structured design doc (math, architecture, data model)
├── AGENTS.md              # This steering file (how to work in the repo)
├── README.md              # User-facing overview, math, usage examples, adaptive b guide
├── CONTRIBUTING.md        # Contribution guidelines
├── DEMO_SCRIPT.md         # Walkthrough script + talking points for the Streamlit demo
├── pyproject.toml         # Modern packaging (hatchling, lmsr-lab name, ruff/mypy config, extras)
├── app.py                 # Streamlit demo (full-featured: multi-market, portfolio, leaderboard, b explorer)
├── src/lmsr/
│   ├── __init__.py        # Public exports (BinaryLMSRMarket, LMSRMarketSimulator, scoring, adaptive strategies)
│   ├── market.py          # Core `BinaryLMSRMarket` — numerically stable LMSR engine (fixed + adaptive b)
│   ├── simulator.py       # `LMSRMarketSimulator` — multi-market system, users, payouts, scores, accounting
│   ├── scoring.py         # Brier, Log score, Murphy decomposition + helpers
│   └── adaptive.py        # Dynamic liquidity strategies (LinearVolumeB, LogVolumeB, BoundedB, TradeCountB, ...)
├── tests/                 # pytest suite (45+ tests, priority area — never weaken)
├── examples/              # Rich histories (Kelly + illustrative), replay tools, generators, PDF reports
├── .hermes/plans/         # Old implementation plans (reference only; see plan for future phases)
├── .venv/
└── .git/
```

**Do not** commit or edit anything inside `.venv/`.

**Always read `DESIGN.md` (at least the relevant sections) before making significant changes to the market math or architecture.**

## Running the Project

### Activate environment
```bash
source .venv/bin/activate
# or use full paths below
```

### Run the Streamlit demo
```bash
PYTHONPATH=. .venv/bin/streamlit run app.py
# or
.venv/bin/streamlit run app.py --server.runOnSave true
```

The UI lets you:
- Adjust liquidity parameter `b`
- Trade Yes/No shares (with fee)
- Preview impact & slippage before trading
- View positions
- Resolve the market and see market-maker P/L

### Quick smoke test (Python)
```bash
.venv/bin/python -c '
import sys
sys.path.insert(0, ".")
from src.lmsr.market import BinaryLMSRMarket
m = BinaryLMSRMarket(b=20, fee_rate=0.02)
print("Prices:", m.price())
m.trade("alice", 10, 0)
print("After buy 10 Yes:", m.price())
print("OK")
'
```

## Core Implementation Notes

**Primary engine**: `BinaryLMSRMarket` (`src/lmsr/market.py`)
- `q` = outstanding shares vector `[q_yes, q_no]`
- `user_positions` = separate ledger per user (prevents negative holdings; DESIGN.md requirement)
- `_cost` / pricing use `np.logaddexp` + stable softmax for numerical stability
- Supports both fixed `b` (float) and adaptive/dynamic `b` (callable strategy from `adaptive.py`)
- `fee_rate` applied on trades; quote/impact/slippage previews available
- `resolve(outcome)` computes simple market-maker P/L = total_revenue - payout (basic engine only)

**Higher-level system**: `LMSRMarketSimulator` (`src/lmsr/simulator.py`) is now the typical entry point for experiments
- Immutable `Trade` log (append-only source of truth)
- Explicit `Payout` + per-trade `Score` (Brier + Log) records on resolution
- `User` + `UserPortfolio` with cross-market positions, realized PnL, balances
- Automatic accounting identity verification on every resolution
- `save()` / `load()` (pickle for now)
- Global leaderboard

**Adaptive liquidity** (`src/lmsr/adaptive.py`):
- Strategies are callables `b(q) -> float` (or stateful like `TradeCountB`)
- Use `BoundedB(...)` wrapper in production to keep `b` sane
- Market exposes `.is_adaptive_b`, `.set_b_strategy()`, and guards the `.b` setter

**Invariants to preserve** (across both layers):
- Prices always sum to 1.0
- Buying Yes increases p_yes (and vice versa)
- User cannot sell more shares than they hold
- `total_revenue` only increases on trades
- Accounting identity holds after resolution (simulator enforces)

## Coding & Contribution Guidelines

1. **Keep the market engine pure**
   - Core LMSR math and stability logic stays in `BinaryLMSRMarket` (or small helpers in `market.py`)
   - Simulator, scoring, and adaptive strategies live in their own modules
   - No new runtime dependencies for the core (numpy only)
   - Prefer `np` vectorized code over Python loops

2. **Testing**
   - All new behavior **must** come with tests in `tests/`
   - Use `pytest` (already configured in pyproject.toml dev deps)
   - Current suite: 45+ tests passing (test_lmsr.py + test_simulator.py)
   - Key categories: cost/price math + sum-to-1, round-trip consistency, impact/slippage, resolution accounting + identity checks, adaptive b behavior, edge cases (tiny b, huge trades, sells, zero shares, resolution before/after trades)

3. **UI changes**
   - `app.py` is intentionally a single-file demo for now (Streamlit)
   - When it grows, consider extracting components but keep `LMSRMarketSimulator` / `BinaryLMSRMarket` as the only source of truth
   - Demo-specific bugs fixed in past reviews; many long lines are UI strings (acceptable)

4. **Documentation**
   - Update this `AGENTS.md` when you introduce new conventions, commands, or architectural decisions (it was allowed to drift; recent DESIGN.md polish made this urgent)
   - Add or improve docstrings and type hints on any public API you touch
   - Keep the math comments accurate and cross-referenced to DESIGN.md
   - README.md is the primary user doc; keep it in sync with delivered features

5. **General agent rules**
   - Before editing core logic (market.py, simulator.py, adaptive.py, scoring.py), read the latest versions + this file + relevant DESIGN.md sections
   - Run the smoke test (or full `pytest`) after any change that affects trading, pricing, resolution, or adaptive b
   - Prefer small, reviewable diffs
   - Never delete or weaken existing tests (once they exist)
   - Use the project `.venv` Python for all verification, smoke tests, and linting
   - If you create new files, add them to the appropriate directory (`tests/`, `examples/`, `src/...`)
   - Run `ruff check .` (and ideally `ruff format`) before committing; mypy is configured but tolerates some numpy `Any` returns

6. **Packaging & Tooling**
   - `pyproject.toml` is in place (PEP 621 + hatchling). Package name: `lmsr-lab`
   - Ruff (lint + format) and mypy are configured and part of `dev` extras
   - Keep `.gitignore` sensible (ignore `__pycache__`, `.venv`, `.hermes` local state, build artifacts)

## Current Status & Roadmap (as of late May 2026)

The project has significantly exceeded the original conservative scope (single `BinaryLMSRMarket` engine). It is now a high-quality, well-tested, educational/research-oriented **in-memory prediction market simulator** with:

- Full multi-market `LMSRMarketSimulator` (trades, users, portfolios, payouts, per-trade Brier/Log scores, accounting identity, leaderboard)
- First-class support for both fixed and dynamic/adaptive liquidity (`b`) strategies
- Rich example tooling (16+ histories including large Kelly-generated ones, replay + comparison, PDF report generation)
- Polished Streamlit demo (auto-seeded markets, confirmation dialogs, interactive b explorer, adaptive strategy support)
- Proper packaging, 45+ passing tests, ruff/mypy config, and extensive documentation (polished DESIGN.md + README)

See the plan file (`.hermes/plans/2026-05-21_...-lmsr-prediction-market-plan.md`) and the "Remaining Gaps vs Original Vision" section in DESIGN.md for context.

### Delivered (solid, ready for research / soft demo use)
- Numerically stable core + simulator with strong invariants
- Adaptive b fully integrated and surfaced in UI
- Calibration scoring attached to every resolved trade
- Kelly-based history generators + realistic rug-pull / trend scenarios
- Demo polish + `DEMO_SCRIPT.md` for walkthroughs
- Accounting identity as a first-class checked property

### Remaining notable gaps (mostly future architecture / productionization)
These are expected — the deliberate focus was an excellent research simulator, not yet a production platform.

- [ ] **Persistence**: Replace pickle `save()`/`load()` with a proper SQL backend (reference schema already in DESIGN.md). Needed for concurrency, auditability, and real use.
- [ ] **API layer**: Clean, stable API (FastAPI candidate) for external agents/bots, UIs, and programmatic trading strategies. High priority for agent-based research (see plan item #1).
- [ ] **Professional frontend**: Modern web UI (e.g. Next.js/React) over the API layer, keeping Python engine as source of truth. Streamlit remains the quick demo vehicle for now.
- [ ] **Bot / agent ergonomics**: Higher-level client or thin wrapper making it trivial for RL agents, Kelly bots, etc. to participate in markets.
- [ ] **CLI**: Small entry point for common experiment tasks (replay histories with different b, batch scoring, etc.).
- [ ] **JSON state**: Convenience (de)serialization for simulator state alongside pickle (easier sharing of experiment setups).
- [ ] **Advanced scoring / analytics**: Deeper integration of per-trade scores into portfolio views; more Murphy decomposition tooling or visualization.
- [ ] **Dynamic b research**: Continued experimentation with better default adaptive strategies and volume-sensitivity rules (see DESIGN.md and adaptive.py module docstring).

**Near-term small wins** (easy to pick up):
- Add more adaptive b + extreme edge-case tests (suite is already strong)
- A lightweight `examples/experiments.py` for parameter sweeps (fixed vs. adaptive comparisons, calibration curves, etc.)
- Minor docstring / type polish on public APIs (ruff + mypy surface low-hanging fruit)

When in doubt about priority or design for any of the above, re-read DESIGN.md and the plan in `.hermes/plans/`.

## Questions or Ambiguities?

When an agent is unsure about requirements, math, or design choices:
1. Re-read this file and `src/lmsr/market.py`
2. Re-read the original plan in `.hermes/plans/`
3. Ask the user for clarification before making large changes

---

**Last updated**: 2026-05 (refreshed after DESIGN.md polish + project maturation; layout, core notes, and roadmap synchronized with delivered simulator + adaptive + scoring + examples state)
**Maintainer note**: Treat this file as living documentation. Keep it concise but actionable. Update it whenever architecture, tooling, or scope meaningfully changes.