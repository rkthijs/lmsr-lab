# Examples

This directory contains example trade histories and helper scripts to explore how the liquidity parameter `b` affects price paths in the LMSR simulator.

## Trade Histories

Located in `trade_histories/`, these are simple JSON files describing sequences of buy orders.

Each file has the structure:

```json
{
  "name": "Descriptive Name",
  "description": "What this history is meant to illustrate",
  "trades": [
    {"user": "alice", "yes": 10, "no": 0},
    {"user": "bob",   "yes": 0,  "no": 5}
  ]
}
```

Current histories:

**Arbitrary / illustrative** (all extended to >100 trades with sell-all examples)
- `balanced_trades.json` — Users buying on both sides (now 107 trades)
- `strong_early_conviction.json` — Heavy early buying on one side (now 105 trades)
- `late_buyers.json` — Small early trades followed by larger moves (now 107 trades)
- `long_gradual_trend.json` — 20 small consistent buys in one direction (now 105 trades)
- `oscillating_trades.json` — Alternating buys between Yes and No (now 107 trades)
- `whale_then_correction.json` — One massive early trade followed by corrective trades (now 105 trades)
- `mixed_high_activity.json` — Noisy market with many users and mixed directions (now 107 trades)
- `slow_build_then_surge.json` — Slow accumulation followed by a late surge (now 107 trades)

**Principled (Kelly criterion + ~1000 initial subsidy)**
- `kelly_rug_pull.json` — 107 trades. One "whale" slowly accumulates using Kelly sizing, then dumps hard (includes sells).
- `kelly_long_trend.json` — 114 trades. Many Kelly bettors with moderately bullish beliefs slowly push the price (includes sells).
- `kelly_high_activity.json` — 117 trades. Noisy, realistic high-volume market with Kelly-sized bets from many users with different beliefs (includes sells).
- `experts_vs_punters_10000.json` — **New**: 5620 trades. True probability = 0.85. Small group of well-calibrated "experts" + large crowd of noisy/biased "punters". Designed to be replayed with high liquidity (b = 200–1000) to study long-horizon information aggregation.

Feel free to create your own histories to test different scenarios.

## Replaying Histories

Use the `replay_history.py` module to load a history and replay it with different values of `b`.

### Programmatic usage

```python
from examples.replay_history import load_history, compare_b_values, print_price_paths

history = load_history("examples/trade_histories/balanced_trades.json")

# Compare several b values side-by-side
results = compare_b_values(history, b_values=[10, 25, 50, 100])

# Just print the Yes-price path for each b
print_price_paths(results)
```

### Running directly (with optional plotting)

```bash
# Basic table output
python examples/replay_history.py

# With matplotlib plot
python examples/replay_history.py --plot

# Custom history + specific b values + save plot
python examples/replay_history.py \
    --history examples/trade_histories/very_long_pump_and_rug.json \
    --b 15,30,60 \
    --plot \
    --save-plot my_rug_plot.png
```

### Plotting Price Paths

If you have matplotlib installed (`pip install matplotlib`), you can generate nice plots:

```python
from examples.replay_history import load_history, compare_b_values, plot_price_paths

history = load_history("examples/trade_histories/rug_pull_classic.json")
results = compare_b_values(history, b_values=[10, 25, 50, 100], print_table=False)

plot_price_paths(
    results,
    title="Rug Pull Price Paths",
    save_path="rug_pull_comparison.png"
)
```

### Generating a Full PDF Report

There is also a dedicated report generator that creates a multi-page PDF analyzing several rug-pull and long-trend histories side-by-side:

```bash
python examples/generate_rug_analysis_report.py
```

Options:

```bash
python examples/generate_rug_analysis_report.py \
    --b 100,200,400,800 \
    --output examples/reports/my_rug_analysis.pdf
```

The generated PDF includes:
- Price path plots for each history across different `b` values
- Summary statistics tables (max/min price, range, etc.)
- Key observations and recommendations

The default output is saved to `examples/reports/rug_pull_b_analysis.pdf`.

### Custom usage

You can easily load any history file and experiment:

```python
history = load_history("examples/trade_histories/strong_early_conviction.json")
compare_b_values(history, b_values=[5, 15, 30, 80])
```

## What to Look For

When comparing different `b` values on the same trade history:

- **Low b** (e.g. 5–15): Prices move quickly and dramatically. Early trades have large impact.
- **Medium b** (e.g. 25–40): More balanced movement.
- **High b** (e.g. 80+): Prices move slowly. The market is "deeper" and later trades have less impact.

This is especially visible in `strong_early_conviction.json` and `late_buyers.json`.

## Tips

- Set `fee_rate=0.0` when creating markets in your own scripts if you want cleaner price paths (the default simulator uses 2.5%).
- The `replay_history()` function returns raw data you can plot with matplotlib, pandas, etc.
- You can extend the histories with selling (`negative` values) if you want to explore more complex scenarios.

## Creating Your Own Histories

You have two easy ways:

1. Manually create a `.json` file in `trade_histories/` following the schema.
2. Use the principled generator (recommended for realistic examples):

```bash
python examples/generate_kelly_histories.py
```

This script simulates users who size their bets using (approximate) Kelly criterion on a market with `initial_subsidy ≈ 1000`. It produces much more natural position sizes than fixed-share histories.

## Experiments & Parameter Studies

`examples/experiments.py` is a lightweight harness for the kinds of studies mentioned in the project roadmap (parameter sweeps, fixed vs adaptive `b` comparisons, calibration analysis).

```bash
python examples/experiments.py
```

Programmatic usage:

```python
from examples.experiments import (
    run_fixed_b_sweep,
    compare_fixed_vs_adaptive,
    print_comparison_table,
)

sweep = run_fixed_b_sweep(true_p=0.7, b_values=[10, 25, 50, 100])
comp = compare_fixed_vs_adaptive(true_p=0.75)
print_comparison_table(comp)
```

It uses `TradingAgent`, adaptive strategies, and the scoring module to run Monte-Carlo-style belief markets and report mean Brier/Log scores + Murphy decompositions. Extend it for your own research questions.

## Command-Line Interface

After installing the package (`pip install -e .`), you can use the `lmsr` CLI for common tasks:

```bash
lmsr replay examples/trade_histories/kelly_rug_pull.json --b 10,25,50
lmsr compare examples/trade_histories/balanced_trades.json --b 15,30,60 --plot
lmsr --help
```

This is the small entry point referenced in the project roadmap for replaying histories and b-comparisons without remembering full Python invocation paths. More subcommands will be added over time.

## Bot & Automated Agent Examples

This project now includes a growing collection of simple, reusable bot strategies built on top of the high-level `TradingAgent` API (recommended for RL agents, scripted bots, Kelly strategies, etc.).

### Core Bot Implementations
- `examples/simple_bots.py` — A clean library of the simplest bot archetypes:
  - Random / Noise trader (baseline + liquidity)
  - Threshold / Band trader
  - Trend Follower (momentum)
  - Contrarian / Mean Reversion (seeded initial position so it visibly sells when price is pushed high)
  - Belief-based / Fundamental (Kelly-style, with `true_p`)
  - Inventory / Probe bot (maintains a target position)
  - Simple Liquidity Provider (buys the cheaper side to earn fees)

  All are implemented as single-step functions so they are trivial to interleave on the same market.

- `examples/interleaved_bots.py` — A focused, minimal example showing a trend follower and a contrarian running *interleaved* on one adaptive market (every round both get a turn). Demonstrates the three values (cash balance, position value/MTM, total account value) at every step.

- `examples/trading_agent.py` — The original broader tour: fixed-b single-agent walkthrough, exact vs. partial round-trips, and a sequential multi-agent example. Updated to use the new bot helpers and the three-value accounting.

- `examples/ui_300_round_bots.py` — A long-running (300 rounds) unresolved market populated by interleaved bots with a known true probability (p_yes ≈ 0.8) while the market starts mispriced at 0.5. The informed "bull" gradually pushes the price toward the true value; the seeded contrarian sells into the move; random noise, inventory, and LP add realistic volume. Leaves the market open — perfect for the Streamlit UI.

### Running the Bot Examples
```bash
python examples/simple_bots.py          # See all archetypes interleaved on one market
python examples/interleaved_bots.py     # Pure two-strategy interleaving demo
python examples/trading_agent.py        # Original multi-part tour
python examples/ui_300_round_bots.py    # 300-round unresolved demo (for UI seeding)
```

All of them emphasize:
- The three account values users actually care about (cash, position value at current prices, total equity).
- Integer shares only.
- Clean Before/After reporting with costs and fees.
- Using the b-recommendation tool (see the 🧮 expander in the Streamlit app) to choose plausible liquidity parameters instead of magic numbers.

### Using in the Streamlit UI
The long 300-round bot demo is now available as a one-click scenario (users deliberately overlap with names from the Kelly histories used in Full Teaching / rug-pull etc. so that the "Viewing as" switcher and portfolio views feel richer when you explore multiple demos):
- Run the app: `python -m streamlit run app.py`
- In the sidebar, open "🚀 Quick Demo Scenarios"
- Click **"Long Bot Activity Demo (300 rounds, Open)"**

This populates an unresolved market with real trade history, growing adaptive `b`, open positions across several "users", and accumulated MM fees — excellent for exploring the Portfolio tab, trade impact, and live price discovery.

### Programmatic Usage
```python
from examples.simple_bots import (
    trend_follower, mean_reversion, belief_trader,
    random_trader, liquidity_provider
)
from src.lmsr import LMSRMarketSimulator, TradingAgent

sim = LMSRMarketSimulator()
m = sim.create_market("Demo", b=60, initial_subsidy=500)

trend = TradingAgent(sim, "trend")
meanr = TradingAgent(sim, "contrarian")
bull  = TradingAgent(sim, "bull")

for _ in range(50):
    trend_follower(trend, m.id)
    mean_reversion(meanr, m.id)
    belief_trader(bull, m.id, true_p=0.82, size=5)

print("Bull total value:", bull.get_total_value())
```

See the docstrings in `simple_bots.py` for parameter details on each strategy. The functions are intentionally tiny so you can copy-paste or compose them however you like.

## Command Line

See the section above for the `lmsr` CLI (replay + b comparison).

## FastAPI Backend

The `lmsr serve` command (or `uvicorn lmsr.api:app`) starts a FastAPI server that wraps the simulator. This is the HTTP API layer that lets remote agents, bots, and other UIs interact with markets without being in the same Python process.

Install with the api extra and run:

```bash
pip install -e ".[api]"
lmsr serve
```

Full details and request/response examples are in `src/lmsr/api.py` (OpenAPI docs available at /docs when running).

## Persistence in Examples & Experiments

All the example scripts (replay, experiments, trading_agent, etc.) accept or can be easily modified to use a persistent database:

```python
from src.lmsr import LMSRMarketSimulator

sim = LMSRMarketSimulator(db_path="experiment_run.db")
# ... run your sweeps or agents ...
# On the next run with the same db_path you will see the previous state.
```

This is especially useful when you want to continue an experiment across multiple Python sessions or inspect the state with the `lmsr` CLI or the Streamlit demo later.

## Professional Separate Frontend + Backend (completely independent of Streamlit)

A full professional stack lives in `frontend/` (Next.js + React + TypeScript + Tailwind). This is a **separate UI entity** — do **not** touch or run the Streamlit demo (`app.py`) for this.

### Easiest way for others (recommended)
```bash
# Make executable once
chmod +x start-professional-ui.sh

# Run it (handles venv, install, seeds the 300-round demo into lmsr_demo.db, then starts the backend)
./start-professional-ui.sh
```

In a second terminal start the frontend:
```bash
cd frontend
npm run dev
```

Open http://localhost:3000.

- Top user dropdown lets you switch any of the 300-round bot users (`bull`, `contrarian`, `bear` (who buys No when price is high), boosted `random`, `inv`, `lp`, etc.) and instantly see *exactly* what that user sees (cash balance, position value at current prices, total account value, their portfolio, per-market positions, and trade as them).
- Admin tab:
  - Global activity across every user/market + controls to resolve any market.
  - **Demo Scenarios** panel at the top: dropdown + "Load Selected Scenario" button. This gives you *all* the curated demos that exist in the Streamlit app (via the exact same `SCENARIO_REGISTRY` in `examples/demo_seeding.py`): Balanced Trading, Kelly Rug Pull (resolved), High-Activity Kelly, Very Long Gradual Trend, Full Teaching Demo (multi-market), Experts vs Punters, and the 300-round bot activity. "Reset (empty)" is also available. Loading a scenario fully replaces the DB state (markets, users, history, balances) just like the Streamlit scenario buttons.

The backend uses the enhanced FastAPI admin endpoints (`/admin/activity`, `/admin/users`, `/admin/markets`, `/admin/.../resolve`) plus all normal user-scoped ones. CORS is enabled. The market is left unresolved with ~300 rounds of realistic bot activity (true p≈0.8, starts mispriced at 0.5, price drifts toward the true value, activity on both sides).

### Manual steps
```bash
# Setup (once)
source .venv/bin/activate || python -m venv .venv && source .venv/bin/activate
pip install -e ".[api]"

# Seed the rich 300-round unresolved demo (gives you the many bot users + history)
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

### What the 300-round example provides
- Informed "bull" (true_p=0.82) gradually buys Yes and pushes price from 0.5 toward ~0.8.
- Seeded "contrarian" (mean-reversion) sells into the move.
- Boosted random, inventory, LP, threshold, and a low-belief bear (who buys No when price is high) add realistic volume and positions on both sides.
- Adaptive b grows, fees accumulate, lots of open interest.
- Perfect for trying the new professional UI's user switcher and admin view.

See the root `README.md` for the full "Professional Separate Frontend + Backend" section with the complete run instructions (the `start-professional-ui.sh` script is the easiest on-ramp for collaborators).

Everything uses the same persistent `lmsr_demo.db` as the rest of the project and is completely separate from Streamlit (as requested).

The demo / `lmsr serve` uses `lmsr_demo.db` by default so your work survives restarts. Use `db_path=":memory:"` in tests for isolation.