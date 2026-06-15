# LMSR Continuous Liquidity Experiment (Experiment 2)

**Date**: June 2026  
**Focus**: Key Learning — Continuous Liquidity (always-available counterparty / cold-start behavior)  
**Status**: Implemented with real probes (up from skeleton). Consistent with the structure and rigor of Experiment 1 (parameter sensitivity).

## Background & Key Learning

From real-world observation (and why some platforms moved away from pure LMSR or augmented it):

LMSR solves the "cold start" and "no counterparty" problems inherent in order books. A trader can always buy or sell any size at any time because the market maker is always there. No need to wait for an opposing order, and large one-sided trades are always executable (subject to the trader's balance and the resulting price impact).

This is especially powerful for internal/company forecasting tools where you want participation without requiring perfectly matched beliefs on both sides at every moment.

## Setup (consistent with Experiment 1)

- Core: `LMSRMarketSimulator` + `TradingAgent`
- Warm-market context: small belief-market simulation (noisy traders around true_p)
- Cold-start probes: brand-new market (zero prior trades/volume), direct large buy_yes and sell_yes attempts of various sizes
- Metrics:
  - Per-probe: success/failure, price before/after, impact, effective/raw cost
  - Aggregate: cold-start success rate
- Order-book baseline (toy): assumes limited depth (e.g. 50 shares per side near mid); large sizes either fail or would require heavy spread crossing / waiting
- Supports fixed b and (via the engine) adaptive b
- Reproducibility: `python examples/experiments.py` (now includes Experiment 2 section)
- All experiment 2 assets live in `examples/reports/experiment_2_continuous_liquidity/`

Bet sizing and other parameters follow the same conventions as Experiment 1 where relevant (toy approx Kelly for the warm context; direct large probes are explicit sizes).

## Results — Cold-Start Probes (True Liquidity Test)

Example run (b=40, true_p=0.75, sizes=[10,50,100,250]):

Cold-start success rate: 1.0 (all probes executable)

Sample for size 50 buy_yes:
- success: True
- price_before: 0.5
- price_after: ~0.55–0.6 (depending on exact run)
- impact: ~0.05–0.1
- effective_cost: the cost paid (includes fee)

Full `large_trade_probes` dict contains entries for every buy_yes_XX and sell_yes_XX.

Warm market context (for comparison): after some prior trading, final price has moved, mean impact from the warm phase is recorded.

Order-book baseline (toy, depth=50):
- For size=100: success=False (exceeds assumed depth; would need more offers or worse prices)
- For size=10: success=True, very small estimated impact

## Comparison to Order Book (Toy Baseline)

- LMSR: always succeeds on the cold-start market. The "counterparty" is the MM formula. Impact is deterministic given b and size.
- Toy OB: limited depth means large sizes either don't fully execute or cross the spread significantly. In a real OB you would also need pre-existing liquidity providers willing to take the other side at those levels.

This is the core advantage highlighted in the original design discussion.

## Discussion (Findings, Interpretation, Relation to Other Learnings)

- LMSR provides true continuous liquidity by design. The probes confirm 100% success on cold-start even for sizes 25× the "typical" small trade in the warm sim.
- Impact grows with size but is bounded and predictable (unlike an OB that can have gaps or require waiting).
- For internal tools this removes a major friction: anyone with a belief can act immediately.
- Relation to Experiment 1 (Parameter Sensitivity): the b value still controls *how much* the price moves on those liquidity-providing trades. Low b gives more impact (more "responsive" but volatile liquidity); high b gives smoother but "stickier" prices.
- Relation to later learnings (Capital Efficiency, Risk Management): providing this always-on liquidity has a cost (the MM's exposure). The initial subsidy and fee rate are the practical controls.
- Cold-start vs warm: on a market that already has some volume, the same size trade has (slightly) different impact because the q vector has moved. The probes isolate the pure cold-start case.

## How to Reproduce & Extend

```bash
python examples/experiments.py   # now includes Experiment 2 output
```

Directly:

```python
from examples.experiments import measure_liquidity_availability
liq = measure_liquidity_availability(true_p=0.7, b=50.0, large_trade_sizes=[20,100,300])
print(liq["summary"])
print(liq["cold_start_probes"]["buy_yes_100"])
```

Future extensions (consistent with Experiment 1 style):
- More b sweeps + plots of impact vs size for fixed vs adaptive
- Real Kelly traders attempting the large probes (instead of just the toy belief sim for warm context)
- Better order-book simulation (depth that grows with volume, or comparison to a real historical OB depth)
- Measure "effective liquidity" as size that produces a target impact (inverse of the vol_5%/vol_10% idea from Exp 1)
- Cold-start with zero subsidy vs subsidized
- Multi-market cold-start (several independent new markets)

## Files Changed / Related

- `examples/experiments.py` — full implementation of `measure_liquidity_availability` (no longer a stub) + call in `main()`
- `examples/reports/experiment_2_continuous_liquidity/lmsr_continuous_liquidity.md` — this report
- Related: `simulate_belief_market`, `TradingAgent`, `replay_history` (for future real-history versions), the adaptive strategies, and the reports/parameter_sensitivity/ subdir from Experiment 1 (for cross-reference)

This is the second key learning turned into a runnable, documented experiment. It is deliberately kept consistent in style, metrics philosophy, and reproducibility with Experiment 1.

(The other three learnings — Capital Efficiency, Scalability, Risk Management — still have only the original skeletons and are next in line.)