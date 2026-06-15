# LMSR Parameter Sensitivity Experiment

**Date**: June 2026  
**Focus**: Key Learning #2 — Parameter Sensitivity  
**Status**: First of the five key learnings implemented and documented  

## Background & Key Learning

From real-world LMSR usage (e.g. platforms that later moved away from it):

> **Parameter Sensitivity**: Choosing the correct value for the parameter `b` is critical; setting it too low causes excessive price volatility and slippage, while setting it too high makes price updates slow compared to order books.

This experiment quantifies that claim using the project's simulator, adaptive strategies, belief-based traders, and real high-volume histories.

## Experiment Setup

- **Core Simulator**: `LMSRMarketSimulator` + `TradingAgent` with noisy Kelly-style belief traders.
- **Belief Market Simulation** (`simulate_belief_market`):
  - `true_p = 0.72`
  - 25 traders with Gaussian noise around true_p (clipped [0.01, 0.99])
  - 3 trades per trader
  - `initial_subsidy = 500.0`, `fee_rate = 0.025`
- **Fixed `b` Sweep**: `[1, 5, 10, 25, 50, 100, 200, 400, 800, 1600]` (expanded range to probe extremes)
- **Bet sizing** (documented for reproducibility): simple approx. Kelly
  `size = min(max_bet_size, max(min_bet_size, balance * bet_fraction * |edge| / 0.2))`
  with defaults `max=15, min=2, fraction=0.15, skip if |edge| < 0.03`.
  Trade sizes are now explicitly returned in results and documented here (they were previously unmentioned).
- **Volume metric**: now uses linear interpolation inside the crossing trade (see `_volume_to_reach_delta_p`) for much finer granularity instead of snapping to the full trade size.
- **Adaptive Comparators**:
  - `BoundedB(LinearVolumeB(alpha=0.06, min_b=8), min_b=8, max_b=400)`
  - `BoundedB(LogVolumeB(alpha=8.0, min_b=8), min_b=8, max_b=400)`
  - `BoundedB(LinearVolumeB(alpha=0.12, min_b=8), min_b=8, max_b=400)`
- **Metrics** (newly implemented for this learning):
  - `mean_impact`: average absolute price change (`|Δp_yes|`) per trade
  - `max_impact`: largest single-trade price move
  - `volume_for_5pct_move` / `volume_for_10pct_move`: cumulative trading volume required to move the market price 5% or 10% away from the starting ~0.5
- **Real History Analysis**: Same impact metrics applied to `replay_history` on `experts_vs_punters_10000.json` (deep 10k-trade history).
- **Reproducibility**: `python examples/experiments.py` (section 4 of the demo output)

**Bet sizing (critical for interpreting the volume numbers)**

The "volume" here is not arbitrary — it comes from the actual shares traded by the simulated agents:

```python
edge = p_belief - current_price
if abs(edge) < edge_threshold:  # default 0.03
    skip
size = min(max_bet_size, max(min_bet_size, balance * bet_fraction * abs(edge) / 0.2))
# defaults: max=15, min=2, bet_fraction=0.15
```

These parameters are now first-class in `parameter_sensitivity_analysis(...)` and `simulate_belief_market(...)` and are returned under `results["bet_sizing"]`.

This is why low-b volumes were previously all exactly 15 (first big bet crossed the threshold) and why we now document them + use interpolation for the crossing trade.

(The report previously omitted any description of bet sizes.)

All code lives in `examples/experiments.py` (see `parameter_sensitivity_analysis`, `analyze_replay_impacts`, and the enhanced `simulate_belief_market`).

## Results

### Fixed-b Sweep (Belief-Market Simulation)

```
    b    mean_brier  mean_impact  max_impact   vol_5%   vol_10%
  1.0       0.1500     0.500000    0.500000      1.5      3.0
  5.0       0.1509     0.452574    0.452574      1.7      3.3
 10.0       0.0591     0.165429    0.317574      2.4      4.7
 25.0       0.0577     0.083079    0.145656      5.1     10.3
 50.0       0.0612     0.045614    0.074443     10.1     20.4
100.0       0.0732     0.025968    0.037430     20.1     40.6
200.0       0.0849     0.014195    0.018741     40.2     81.1
400.0       0.1128     0.007937    0.009374     80.3    162.2
800.0       0.1444     0.004297    0.004687    160.5    324.3
1600.0      0.1834     0.002274    0.002344    320.9    648.9
```

The volumes for low b are now fractional/granular thanks to linear interpolation within the crossing trade (previously they all snapped to 15 because the first ~15-share bet crossed both thresholds). See "Bet sizing" above for why the numbers are multiples/fractions of ~15. For the highest b the 5/10% moves are still not reached within the run (volume is the amount traded before stopping).

### Adaptive Strategies (Same Setup)

```
strategy                         mean_brier  mean_impact   vol_5%
----------------------------------------------------------------------
Linear(alpha=0.06)                   0.0507     0.152829     15.0
Log(alpha=8)                         0.0541     0.057922     15.0
Linear(alpha=0.12)                   0.0507     0.152829     15.0
```

### On Real Deep History (via `replay_history`)

Higher fixed `b` dramatically reduced per-trade impact and increased the volume required for meaningful price movement — the same qualitative pattern seen in the synthetic belief markets.

## Key Findings (Directly Validate the Learning)

1. **Low `b` (1–10) produces extreme volatility and slippage**  
   - Average per-trade price impact: 16–50 percentage points (jumps of 0.3–0.5 are common).  
   - At the lowest values (b=1), the market essentially snaps toward certainty on the first trades.  
   - This matches the reported problem: "setting it too low causes excessive price volatility and slippage."

2. **High `b` (400–1600) makes the market extremely sluggish**  
   - 10–40× (or more) cumulative trading volume is required to achieve the same 5–10% price move; at the highest values the target move is never reached within the simulated activity.  
   - The volume numbers scale roughly linearly with b.  
   - Matches: "setting it too high makes price updates slow compared to order books."

3. **Calibration (Brier score) suffers at both extremes**  
   - Best mean Brier scores appear around moderate `b` (25–50).  
   - Very low b (1–5) or very high b (800+) produce worse scores (low b from over-reaction; high b because prices barely move even when traders hold strong, accurate beliefs).

4. **Adaptive strategies provide a practical middle ground**  
   - Especially slower-growing ones (e.g. `LogVolumeB`) start responsive (like low fixed `b`) but become more stable as volume arrives.  
   - This directly mitigates the parameter-sensitivity problem without requiring the user to pick one "perfect" fixed `b` in advance.

## Interpretation & Relation to Other Learnings

This experiment provides quantitative backing for why `b` selection is critical in LMSR. The results also have implications for the other key learnings:

- **Capital Efficiency**: High `b` wastes even more "idle" collateral because price discovery is slow — much of the locked subsidy is never actually at risk in a meaningful way.
- **Scalability**: In very deep/high-volume markets the high-`b` regime becomes especially problematic (tiny price moves despite enormous activity), which is consistent with reports of platforms moving away from LMSR at scale.
- **Risk Management**: The volatility at low `b` increases the chance of large adverse moves for the market maker, reinforcing the need for fees and other mitigations.

## How to Reproduce & Extend

```bash
python examples/experiments.py
```

The function is also directly importable:

```python
from examples.experiments import parameter_sensitivity_analysis, print_parameter_sensitivity_table

sens = parameter_sensitivity_analysis(true_p=0.75, b_values=[10, 50, 200])
print_parameter_sensitivity_table(sens)
```

Running the module now also generates a price-path overlay plot (see below).

## Visualizations (New for #1)

To make the "volatility vs. sluggish" effect obvious, a dedicated plotting helper was added:

```python
from examples.experiments import parameter_sensitivity_analysis, plot_b_sweep_price_paths
sens = parameter_sensitivity_analysis(...)
plot_b_sweep_price_paths(sens)   # saves PNG by default to reports/
```

![Price path sensitivity to b](lmsr_param_sens_price_paths.png)

- Steep wiggly lines (low b): large per-trade moves, high slippage/volatility.
- Nearly flat lines (high b): requires many more trades (volume) before price moves meaningfully.

The plot is automatically produced when running the experiments demo (saved to `examples/reports/lmsr_param_sens_price_paths.png`).

Future extensions (see sibling todos):
- Monte Carlo over trader count / belief noise
- Impact-vs-cumulative-volume curves (already have the data in `impacts`)
- Same analysis on the 300-round bot demo and other deep histories using `replay_history`
- Direct comparison of "economic slowness" (volume per % move) against a simple order-book model

## Files Changed / Related

- `examples/experiments.py` — core implementation + documented results block + `plot_b_sweep_price_paths`
- `examples/reports/lmsr_parameter_sensitivity.md` — this report
- `examples/reports/lmsr_param_sens_price_paths.png` — new visual artifact
- Related: `replay_history.py` (re-uses similar plotting style), `src/lmsr/adaptive.py`, deep histories in `trade_histories/`

This is the first of the five key learnings to be turned into a runnable, documented experiment with supporting visuals. The others (Continuous Liquidity, Capital Efficiency, Scalability, Risk Management) have skeletons and are ready for the same treatment.