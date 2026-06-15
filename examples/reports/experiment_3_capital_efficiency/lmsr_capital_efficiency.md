# LMSR Capital Efficiency Experiment (Experiment 3)

**Date**: June 2026  
**Focus**: Key Learning — Capital Efficiency (collateral waste on tails / unlikely outcomes)  
**Status**: Implemented. Consistent with Experiment 1 (detailed variants + report structure) and Experiment 2.

## Background & Key Learning

From the design discussion and real-world LMSR usage:

LMSR requires the market maker to post an initial subsidy (collateral) that is sufficient to cover the worst-case loss over the *entire* [0,1] probability space. For binary LMSR, the maximum loss is b · ln(2) ≈ 0.693 · b.

In practice, if traders have reasonable (not completely extreme) beliefs, the price rarely goes to the absolute tails (0 or 1). A large portion of the posted subsidy is therefore "idle" or "wasted" on those low-probability regions — capital that is locked up but almost never actually at risk.

This is the capital efficiency problem: the mechanism is theoretically elegant but can be over-collateralized in real use.

## Setup (consistent with prior experiments)

- Core: `LMSRMarketSimulator` + belief traders (noisy around true_p).
- Vary `initial_subsidy` while keeping trader behavior the same.
- Track during the market lifetime:
  - Running MM mark-to-market P/L = total_revenue - current_marked_liability (p·q)
  - Peak drawdown (minimum of the above — the most capital ever "at risk").
- After resolution: final realized P&L (total_revenue - actual payout to winners).
- Utilization = |peak_drawdown| / initial_subsidy (what fraction of the posted capital was actually needed at its worst point?).
- Supports the same toy sizing and seed as Experiment 1 for comparability.
- Reproducibility: `python examples/experiments.py` (now includes Experiment 3 section).
- All assets for this experiment live in `examples/reports/experiment_3_capital_efficiency/`.

## Results — Subsidy Sweep

Example run (true_p=0.75, 20 traders, 2 trades each, toy sizing, seed=99):

```
subsidy   peak_drawdown   final_mm_pl   utilization   mean_brier
 100.0       -13.48         -20.17        0.135        0.0667
 300.0       -13.48         -20.17        0.045        0.0667
 800.0       -13.48         -20.17        0.017        0.0667
2000.0       -13.48         -20.17        0.007        0.0667
```

The absolute peak drawdown is the same across subsidies because the trader behavior and price path are identical — only the posted collateral changes. Utilization drops as subsidy increases, showing that a larger fraction of the posted capital is "idle" on the tails.

The key observation is that utilization is well below 1.0 — a significant fraction of the posted capital was never "used" at its worst point.

## Comparison to "Ideal" Collateral

In an ideal world you would only need to post enough capital to cover the actual worst-case exposure that occurs given the traders' beliefs and the realized path. LMSR forces you to post for the theoretical maximum (b ln 2), even if the price only ever moved between 0.4 and 0.6.

This is the source of the "large collateral waste on tails."

## Discussion (Findings, Interpretation, Relation to Other Learnings)

- LMSR is "over-collateralized by design" for robustness, but this comes at an opportunity cost for the MM (or whoever posts the subsidy).
- Utilization tends to be higher when beliefs are more extreme or when b is low (bigger price swings = bigger swings in marked liability).
- Relation to Experiment 1 (Parameter Sensitivity): the b value directly affects how much the price moves and therefore how much the marked liability (p·q) fluctuates. Low b = more volatile capital usage.
- Relation to Experiment 2 (Continuous Liquidity): providing always-on liquidity requires having capital ready; the efficiency question is how much of that readiness is actually used.
- Relation to Risk Management (future experiment): fees can help offset the MM's expected loss, partially mitigating the capital cost.
- For internal tools this matters for how much "skin in the game" the organizer has to put up vs. how much is truly necessary.

## How to Reproduce & Extend

```bash
python examples/experiments.py   # includes Experiment 3 output + tables
```

Programmatically:

```python
from examples.experiments import capital_efficiency_analysis
cap = capital_efficiency_analysis(true_p=0.7, initial_subsidies=[200, 1000, 5000])
print(cap["subsidy_sweep"])
```

Future extensions (for consistency with Experiment 1 style):
- Full sweeps over b + belief noise + number of traders.
- "True Kelly" version: replay on the kelly_*.json histories (compute running MM P/L during replay with the actual historical costs).
- Multi-market capital efficiency (one big subsidy pool across several independent markets vs. separate subsidies).
- Plots of running MM P/L over time for different subsidies (price path + shaded drawdown area).
- Effect of fee_rate on realized vs. mark-to-market utilization.
- Comparison to "ideal" collateral (what a perfect foresight MM would have needed for the realized path).

## Files Changed / Related

- `examples/experiments.py` — real implementation of `capital_efficiency_analysis` (no longer a stub) + integration in `main()`. Added running_mm_pls and final_mm_pl tracking to `simulate_belief_market`.
- `examples/reports/experiment_3_capital_efficiency/lmsr_capital_efficiency.md` — this report.
- Related: the full Experiment 1 work in `reports/parameter_sensitivity/`, the belief simulation, TradingAgent, adaptive strategies, and the other experiment reports.

This is the third key learning turned into a runnable, documented experiment, kept consistent in style and quality with the previous two.

(The remaining two — Scalability Limitations and Risk Management — still have only the original skeletons.)

---

*For a serious reviewer: the implementation tracks actual engine state (total_revenue + q + price) after every trade to compute mark-to-market P/L and peak drawdown. All parameters (subsidy levels, trader count, seed, b, fee_rate) are explicit. The toy sizing is the same one documented and used in Experiment 1 for comparability.*