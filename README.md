# LMSR Prediction Market Simulator

**lmsr-lab** — An educational and research-oriented simulator for Robin Hanson's Logarithmic Market Scoring Rule (LMSR) for binary prediction markets.

This project was built following the detailed design conversation in [`DESIGN.md`](./DESIGN.md), which explores how to create a clean, numerically stable LMSR engine suitable for internal forecasting tools.

---

## Background & Motivation

Traditional prediction markets (especially crypto ones) are often designed for public, permissionless, real-money environments. For **internal company forecasting** or low-stakes experimental use, the requirements are very different:

- No need for trustless settlement (you control resolution)
- Play money or points are sufficient
- Small number of users (no need for blockchain scalability)
- Strong emphasis on **calibration** (how well people’s forecasts match reality)

In the original design discussion, the conclusion was to build a lightweight, self-hosted system using **LMSR** as the core market maker mechanism.

### Why LMSR?

LMSR has several properties that make it particularly suitable for internal tools:

- **Bounded loss**: The market maker’s worst-case loss is bounded by `b · ln(n)` (where `n` is the number of outcomes). For binary markets this is simply `b · ln(2)`.
- **Clean probabilities**: Prices are always a valid probability distribution.
- **Single intuitive parameter**: The liquidity parameter `b` directly controls how much prices move per trade.
- **Good theoretical calibration properties**: LMSR is a strictly proper scoring rule, which aligns well with wanting honest reporting and good calibration.

---

## Mathematical Foundation

### Core LMSR Formulas

For a binary market with outcomes *Yes* and *No*, let:

- `q = [q_yes, q_no]` = outstanding shares in each outcome
- `b` = liquidity parameter

**Cost function** (how much it costs the market maker to reach a certain state):

$$
C(q) = b \cdot \ln \left( e^{q_\text{yes}/b} + e^{q_\text{no}/b} \right)
$$

Or more generally for multiple outcomes:

$$
C(q) = b \cdot \ln \left( \sum_i \exp(q_i / b) \right)
$$

**Price** of outcome *i*:

$$
p_i = \frac{\exp(q_i / b)}{\sum_j \exp(q_j / b)}
$$

This is simply the softmax of the share vector `q / b`.

**Cost of a trade** (buying `Δq` shares):

The cost to the trader is:

$$
\Delta C = C(q + \Delta q) - C(q)
$$

### Numerical Stability (Important Detail)

A naive implementation of `C(q + Δq) - C(q)` suffers from **catastrophic cancellation** when trades are small relative to existing volume. This project uses the algebraically equivalent but numerically stable form (derived in the design discussion):

$$
\Delta C = b \cdot \ln \left( \sum_i p_i \cdot \exp(\Delta q_i / b) \right)
$$

where `p_i` are the prices *before* the trade.

All price calculations in this simulator use the stable softmax form:

$$
p_i = \exp\left( \frac{q_i}{b} - \text{LSE}(q/b) \right)
$$

where `LSE` is the log-sum-exp operation.

---

## Why This Project?

Most existing LMSR implementations are either:

- Very basic (no user tracking, no resolution accounting)
- Tied to specific frontends or blockchains
- Missing proper calibration scoring

This simulator was built to be **educational and research-friendly**, making it easy to:

- Experiment with different values of `b`
- Study how price paths evolve under different trading patterns (including rug-pull style histories)
- Explore calibration scoring (Brier score, Log score, Murphy decomposition)
- Understand the relationship between liquidity, price impact, and information aggregation

See the [`examples/`](./examples/) directory for ready-made trade histories and tools to replay them with different `b` values.

---

## Core Components

- **`BinaryLMSRMarket`** (`src/lmsr/market.py`)  
  The numerically stable core engine.

- **`LMSRMarketSimulator`** (`src/lmsr/simulator.py`)  
  The higher-level multi-market system that adds:
  - Trade history
  - Payout records
  - Stored resolution scores
  - User balances and portfolio tracking
  - Accounting identity verification
  - Leaderboard
  - Optional SQLite persistence (`db_path=...`) — see Persistence section below. The in-memory mode (default) and pickle `save`/`load` remain available for experiments.

- **Calibration Scoring** (`src/lmsr/scoring.py`)  
  Brier score, Log score, and Murphy decomposition.

- **Adaptive Liquidity Strategies** (`src/lmsr/adaptive.py`)  
  Support for dynamic/adaptive `b` (in addition to classic fixed `b`).
  Includes `LinearVolumeB`, `LogVolumeB`, `BoundedB`, `TradeCountB`, etc.
  See the module for details and usage.

---

## Getting Started

### Run the Demo

```bash
source .venv/bin/activate
streamlit run app.py
```

The app includes live trading, portfolio views, stored scoring, and a global leaderboard.

### Programmatic Usage

```python
from src.lmsr.simulator import LMSRMarketSimulator

sim = LMSRMarketSimulator()                    # pure in-memory (default)
# sim = LMSRMarketSimulator(db_path="my.db")    # durable SQLite (state survives restarts)

# Create a market with subsidy ≈ 1000 (educational default)
m = sim.create_market(
    title="Will revenue beat target?",
    b=45.0,
    initial_subsidy=1000.0
)

# Trade
sim.place_trade(m.id, "alice", 12, 0)
sim.place_trade(m.id, "bob", 0, 8)

# Resolve
result = sim.resolve_market(m.id, "yes")
print("Accounting check:", result["accounting_identity"])

# View user's portfolio across markets
portfolio = sim.get_user_portfolio("alice")
print(portfolio)
```

### Bot & Agent Ergonomics (for RL, scripts, and automated traders)

For bots, reinforcement learning agents, Kelly-based scripts, or market-making bots, use the higher-level `TradingAgent` wrapper. It provides a much more ergonomic API scoped to a single `user_id`.

```python
from src.lmsr import LMSRMarketSimulator, TradingAgent
from src.lmsr.adaptive import LinearVolumeB, BoundedB

sim = LMSRMarketSimulator()
agent = TradingAgent(sim, user_id="my_bot")

m = agent.create_market(
    "Will revenue beat target?",
    b=BoundedB(LinearVolumeB(alpha=0.05), min_b=10, max_b=300)
)

agent.buy_yes(m.id, shares=25)
print("Prices:", agent.get_prices(m.id))
print("Current b (adaptive):", agent.get_current_b(m.id))
print("My position:", agent.get_position(m.id))
print("Balance:", agent.get_balance())

# Evaluate before acting
quote = agent.quote(m.id, shares_yes=10)
print("Hypothetical cost:", quote)
```

See the dedicated bot section below and `examples/README.md` for the full collection (including the new `simple_bots.py` library and the 300-round UI demo).

---

## Educational Examples

The `examples/` directory is designed for exploration, including a significantly expanded set of bot examples (see below).

```bash
# Replay a history with different b values
python examples/replay_history.py

# Or programmatically
from examples.replay_history import load_history, compare_b_values
history = load_history("examples/trade_histories/kelly_rug_pull.json")
compare_b_values(history, b_values=[15, 30, 60, 120])
```

You can also use the **Interactive b Explorer** tab in the Streamlit app to load any history and move a slider for `b`.

**CLI (new)**

After `pip install -e .` (or from source with the package installed):

```bash
lmsr --help
lmsr replay examples/trade_histories/kelly_rug_pull.json --b 10,25,50 --plot
lmsr compare examples/trade_histories/balanced_trades.json --b 15,30,60
```

The CLI provides a small entry point for the most common experiment tasks (replay + b-comparison). It dispatches to the tools in `examples/`. More subcommands (batch scoring, experiment runner) will be added over time.

**Bot & Agent Examples (significantly expanded)**

```bash
python examples/simple_bots.py          # Library of 7 basic strategies (random, trend, contrarian, belief, etc.)
python examples/interleaved_bots.py     # Clean two-bot interleaving demo (trend vs mean-reversion)
python examples/trading_agent.py        # Original broader tour + round-trips
python examples/ui_300_round_bots.py    # 300-round unresolved market (true p≈0.8, starts at 0.5)
```

The new `examples/simple_bots.py` provides reusable single-step implementations of the simplest bot types. All modern examples now:
- Use the three values users care about (cash balance, mark-to-market position value, total equity).
- Demonstrate interleaving strategies on the same market.
- Use the built-in b-recommendation tool (see the 🧮 expander in the Streamlit app) to choose plausible liquidity instead of magic numbers.
- Enforce integer shares only.

A long-running unresolved 300-round bot demo (with an informed "bull" that knows the true probability is ~0.8 while the market starts mispriced at 0.5) is available as a one-click scenario in the Streamlit UI under **"🚀 Quick Demo Scenarios"** → **"Long Bot Activity Demo (300 rounds, Open)"**.

See `examples/README.md` for full details, composition examples, and how to use these bots in your own research or RL setups.

### Professional Separate Frontend + Backend (completely independent of Streamlit)

A full professional stack lives in `frontend/` (Next.js + React + TypeScript + Tailwind). This is a **separate UI entity** — do **not** touch or depend on the Streamlit demo (`app.py`).

**What it provides**
- **Backend (enhanced FastAPI)**: Admin views to see *all activity* across every user and every market (`/admin/activity`, `/admin/users`, `/admin/markets`), plus the ability to resolve any market. All normal user-scoped endpoints remain available (`/users/{id}/account` for the three values, `/users/{id}/portfolio`, per-user observe, trades, etc.).
- **Frontend (user level + admin)**: Top dropdown lets you switch any user and instantly see *exactly* what that user sees (cash balance, position value at current market prices, total account value, their portfolio, per-market positions, and trade as them). Admin tab shows global activity + resolve controls. Built around the 300-round bot demo (price drifts from 0.5 toward the true ~0.8; contrarian, random, LP etc. participate on both sides).

**Easiest way to run (one command for backend + data)**

```bash
# Make executable once
chmod +x start-professional-ui.sh

# Run it (handles venv + install + seeds the 300-round demo into lmsr_demo.db + starts the backend)
./start-professional-ui.sh
```

In a second terminal start the frontend:
```bash
cd frontend
npm run dev
```

Open http://localhost:3000.

- Use the top user dropdown to switch between the 300-round bot users (`bull`, `contrarian`, `bear` who buys No when price is high, boosted `random`, etc.) and see exactly what each one sees.
- Switch to the Admin tab to see global activity across everyone and resolve markets.
- In the Admin tab there is now a **Demo Scenarios** section at the top with a dropdown. The primary one is the comprehensive "Full Teaching Demo (Multi-Market)" (merges balanced trading, rug pull, high-activity, experts-vs-punters, long trends, etc. into one rich multi-market state). The separate "Long Bot Activity Demo (300 rounds, Open)" is also available. "Load Selected Scenario" (or "Reset (empty)") replaces the current DB state exactly as the Streamlit scenario buttons do.

The script is the easiest on-ramp for collaborators. Everything uses the same persistent `lmsr_demo.db` as the rest of the project and has zero dependency on the Streamlit demo.

See `examples/README.md` for the full "Professional Separate Frontend + Backend" section with manual steps and more details.

### Professional Separate Frontend + Backend (completely independent of Streamlit)

A full professional stack lives in `frontend/` (Next.js + React + TypeScript + Tailwind). This is a **separate UI entity** — do not touch or depend on the Streamlit demo (`app.py`).

**What it provides**
- **Backend (enhanced FastAPI)**: Admin views to see *all activity* across every user and every market, plus the ability to resolve any market. All the normal user-scoped endpoints (`/users/{id}/account` for the three values, `/users/{id}/portfolio`, per-user observe, trades, etc.) are still there so the frontend can show exactly what each user sees.
- **Frontend (user level + admin)**: Top dropdown lets you switch any user and instantly see *exactly* what that user sees (cash balance, position value at current prices, total account value, their portfolio, per-market positions, and trade as them). Admin tab shows global activity feed + resolve controls. Designed around the 300-round bot demo (price drifts from 0.5 toward the true ~0.8; contrarian, random, LP, inventory etc. all participate on both sides).

**Easiest way to run (one command for backend + data)**

```bash
# Make executable once
chmod +x start-professional-ui.sh

# Run it
./start-professional-ui.sh
```

This script will:
- Activate/create the project `.venv` and `pip install -e ".[api]"`.
- Run `python examples/ui_300_round_bots.py` (300 interleaved rounds of the simple bots, populates `lmsr_demo.db` with many users like `bull`, `contrarian`, `bear` (who buys No when price is high), boosted random, etc.).
- Start the FastAPI backend in the foreground (`lmsr serve`).

**In a second terminal** start the frontend:

```bash
cd frontend
npm run dev
```

Open http://localhost:3000.

- Use the top user dropdown to switch between the 300-round bot users and see exactly what each one "sees".
- Switch to the Admin tab to see all activity and resolve markets. The Admin tab also exposes the (now consolidated) demo scenarios (dropdown + Load): the main "Full Teaching Demo (Multi-Market)" plus the separate 300-round bot demo.
- Backend must be on port 8000 (API docs at /docs).

**Manual steps** (useful for development)

```bash
# Setup (once)
source .venv/bin/activate || python -m venv .venv && source .venv/bin/activate
pip install -e ".[api]"

# Seed the rich 300-round unresolved demo (recommended)
python examples/ui_300_round_bots.py

# Start backend (one terminal)
lmsr serve --reload
# or
uvicorn lmsr.api:app --reload --port 8000

# Start frontend (another terminal)
cd frontend
npm run dev
```

Then open http://localhost:3000 as above.

The bash script `start-professional-ui.sh` is the easiest on-ramp for collaborators. Everything is separate from Streamlit, uses the same persistent `lmsr_demo.db`, and gives you the full admin + per-user experience described in the roadmap.

**Experiments & Parameter Studies**

```bash
python examples/experiments.py
```

Lightweight harness for sweeps (fixed vs adaptive `b`), calibration curves, and scoring comparisons using the simulator + `TradingAgent`. Great for research questions around liquidity and forecaster performance. See the file and `examples/README.md` for usage.

**FastAPI Backend (new)**

The project now includes a FastAPI layer (see plan item for "API layer"):

```bash
pip install -e ".[api]"
lmsr serve --port 8000
# or
uvicorn lmsr.api:app --reload
```

Visit http://localhost:8000/docs for interactive OpenAPI UI.

It exposes the full simulator (markets, trades with user_id, observe, portfolio, leaderboard, resolve) and supports both fixed and adaptive `b`. Perfect for remote bots and custom frontends while keeping the Python engine as the source of truth.

See `src/lmsr/api.py` for the implementation and example client snippets.

---

## Fixed vs Adaptive Liquidity (`b`)

By default, `b` is a fixed constant (classic LMSR). However, the library also supports **dynamic/adaptive `b`** strategies. These allow liquidity to change over time — typically growing with trading volume — which helps reduce excessive early volatility (the "thin market problem").

### Basic Usage

```python
from src.lmsr import BinaryLMSRMarket, LMSRMarketSimulator
from src.lmsr.adaptive import LinearVolumeB, LogVolumeB, BoundedB

# Fixed b (traditional)
m_fixed = BinaryLMSRMarket(b=60)

# Adaptive: b grows linearly with total shares, but capped
adaptive = BoundedB(
    LinearVolumeB(alpha=0.05, min_b=10),
    min_b=10,
    max_b=350
)
m_adaptive = BinaryLMSRMarket(b=adaptive)

# Use with the simulator
sim = LMSRMarketSimulator()
m = sim.create_market("Test Market", b=LogVolumeB(alpha=10, min_b=8))
```

### Comparison of Available Strategies

| Class                | Growth Behavior                      | Best For                                      | Stateful?          |
|----------------------|--------------------------------------|-----------------------------------------------|--------------------|
| `FixedB` / `ConstantB` | Constant                            | Baseline, classic LMSR                        | No                 |
| `LinearVolumeB`      | Linear in total shares               | General purpose, most common choice           | No                 |
| `SqrtVolumeB`        | Square root of total shares          | Slower growth than linear                     | No                 |
| `LogVolumeB`         | Logarithmic (very slow)              | Long-running or high-volume markets           | No                 |
| `BoundedB`           | Wrapper that clips any strategy      | Production use (prevent extremes)             | No                 |
| `TradeCountB`        | Linear in number of trades           | When participation matters more than size     | Yes (use `.step()`) |

### Recommended Strategies

- `LinearVolumeB` — Most common. Good default for many experiments.
- `LogVolumeB` — Grows very slowly. Excellent for long-running markets.
- `BoundedB(...)` — Wrap any strategy to enforce hard min/max bounds (highly recommended for real use).

See `src/lmsr/adaptive.py` for the full list, detailed documentation, and more examples.

---

## Persistence (New)

By default `LMSRMarketSimulator()` is fully in-memory (fast for tests and experiments). For durable storage (state survives restarts of the demo, API server, or your scripts) you can pass a `db_path`:

```python
from src.lmsr import LMSRMarketSimulator

# File-backed (recommended for the demo / long-running use)
sim = LMSRMarketSimulator(db_path="my_simulation.db")

# Or an in-memory DB (great for isolated tests)
sim = LMSRMarketSimulator(db_path=":memory:")
```

**What gets persisted**
- Markets (metadata + adaptive strategy parameters)
- Trades (the immutable append-only log)
- User balances
- Payouts and per-trade calibration scores on resolution

On startup with a `db_path`, the simulator **replays** the trade history into the LMSR engines so that positions, prices, and the sell-guard state are derived exactly as described in `DESIGN.md`. This keeps the on-disk format simple and auditable.

**The demo / API server**
The Streamlit demo and `lmsr serve` now use a local SQLite file (`lmsr_demo.db` in the current directory) by default. Your markets, trades, and balances will survive restarting the server or the Streamlit app.

**Migration / compatibility**
- Old pickle `save()` / `load()` still work for full object snapshots (useful for experiments).
- Passing `db_path=None` (the default) gives the classic pure in-memory behavior.
- The relational schema follows the one documented in `DESIGN.md` (with TEXT ids for compatibility with the existing "m1"/"alice" style identifiers).

See the docstring of `LMSRMarketSimulator` and `src/lmsr/db.py` for more details.

---

## Project Structure

```
.
├── app.py                      # Streamlit demo
├── src/lmsr/
│   ├── market.py               # Core LMSR engine (numerically stable)
│   ├── scoring.py              # Brier, Log score, Murphy decomposition
│   ├── simulator.py            # Multi-market system + User/Trade/Payout/Score models
│   ├── db.py                   # SQLite persistence backend (new)
│   ├── api.py                  # FastAPI layer
│   ├── cli.py                  # Small CLI (replay, compare, serve)
│   └── agent.py                # TradingAgent for bots / RL
├── examples/
│   ├── trade_histories/        # Ready-made histories (including Kelly + rug pulls)
│   └── replay_history.py       # Tools to explore different b values
├── tests/
├── DESIGN.md                   # Primary design source (detailed math + architecture)
├── AGENTS.md                   # Project steering guidelines
└── README.md
```

---

## License & Ownership

This project is maintained by **Robert Thijs Kozma** in a personal capacity.  
It is licensed under the [MIT License](LICENSE).

The repository lives under a personal GitHub account and is not owned by any company.

---

Built as an educational and research tool following the design in `DESIGN.md`.