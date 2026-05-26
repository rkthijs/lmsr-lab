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

- Set `fee_rate=0.0` when creating markets in your own scripts if you want cleaner price paths (the default simulator uses 2%).
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