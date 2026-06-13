"""
Lightweight experiment runner for LMSR studies.

Focus areas (as called out in the project roadmap):
- Parameter sweeps over fixed `b`
- Fixed vs adaptive/dynamic `b` comparisons
- Impact on price paths and (especially) forecaster calibration
- Using Brier/Log scores + Murphy decomposition

This is meant to be importable for notebooks/scripts and runnable directly
for quick demos:

    python examples/experiments.py

It reuses:
- LMSRMarketSimulator + TradingAgent (for realistic multi-user trading)
- Adaptive strategies (LinearVolumeB, BoundedB, ...)
- scoring module (brier_score, log_score, ForecasterScores, decomposition)

Example programmatic usage:

    from examples.experiments import (
        simulate_belief_market,
        run_fixed_b_sweep,
        compare_fixed_vs_adaptive,
    )

    # Run one market with believers who have noisy beliefs around true_p=0.7
    # b=50 chosen as a "medium liquidity" value using the b-recommendation tool
    # (subsidy≈500, typical_size=40, desired_move≈8% → rec_b around 40-70 range).
    scores = simulate_belief_market(
        true_p=0.7,
        num_traders=40,
        b=50.0,
        trades_per_trader=2,
    )
    print(scores["mean_brier"], scores["mean_log_score"])

    # Sweep
    results = run_fixed_b_sweep(true_p=0.7, b_values=[10, 25, 50, 100])
    for b, s in results.items():
        print(b, s["mean_brier"])

    # Head-to-head
    comp = compare_fixed_vs_adaptive(true_p=0.75, num_traders=30)
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

# Make runnable directly from repo root
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np

from src.lmsr import LMSRMarketSimulator, TradingAgent
from src.lmsr.adaptive import BoundedB, LinearVolumeB
from src.lmsr.scoring import ForecasterScores


def _noisy_beliefs(num: int, true_p: float, noise: float = 0.12, seed: int | None = None) -> np.ndarray:
    """Generate beliefs centered on true_p with Gaussian noise (clipped to [0.01, 0.99])."""
    rng = np.random.default_rng(seed)
    beliefs = true_p + rng.normal(0, noise, size=num)
    return np.clip(beliefs, 0.01, 0.99)


def simulate_belief_market(
    true_p: float = 0.7,
    num_traders: int = 30,
    b: float | Any = 40.0,
    fee_rate: float = 0.02,
    trades_per_trader: int = 2,
    belief_noise: float = 0.12,
    seed: int | None = 42,
    initial_subsidy: float = 500.0,
) -> dict[str, Any]:
    """
    Simulate a market where traders have noisy beliefs around `true_p`.

    Each trader places a few Kelly-style bets. At the end we resolve the market
    with the true outcome (Bernoulli draw with p=true_p) and score every trade's
    forecast (the market price at the time of the trade).

    Returns a dict with mean scores + full Murphy decomposition.
    """
    rng = np.random.default_rng(seed)
    beliefs = _noisy_beliefs(num_traders, true_p, belief_noise, seed)

    sim = LMSRMarketSimulator()
    market = sim.create_market(
        title=f"Belief experiment (true_p={true_p})",
        b=b,
        fee_rate=fee_rate,
        initial_subsidy=initial_subsidy,
    )

    forecaster = ForecasterScores()
    agents = [TradingAgent(sim, f"trader_{i}") for i in range(num_traders)]

    for _t in range(trades_per_trader):
        for _i, (agent, p_belief) in enumerate(zip(agents, beliefs, strict=True)):
            # Simple approx Kelly: bet fraction of "edge" if we have balance
            current_price = agent.get_prices(market.id)[0]
            edge = p_belief - current_price
            if abs(edge) < 0.03:  # too close to current price, skip
                continue

            # Scale trade size by belief strength and remaining balance
            balance = agent.get_balance()
            size = min(15.0, max(2.0, balance * 0.15 * abs(edge) / 0.2))

            if edge > 0:
                res = agent.buy_yes(market.id, shares=size)
            else:
                # Selling Yes when you think it's overpriced
                current_pos = agent.get_position(market.id)[0]
                sell_size = min(size, current_pos + 5.0)  # allow some short for demo
                res = agent.sell_yes(market.id, shares=sell_size)

            if "error" not in res:
                # Record the forecast (market price at time of trade)
                forecast = res.get("price_after", (current_price, 1 - current_price))[0]
                forecaster.forecasts.append(float(forecast))

    # Resolve with the true outcome
    outcome = "yes" if rng.random() < true_p else "no"
    sim.resolve_market(market.id, outcome)
    true_outcome = 1.0 if outcome == "yes" else 0.0

    # Fill outcomes (every recorded price is treated as a forecast of the final binary outcome)
    forecaster.outcomes = [true_outcome] * len(forecaster.forecasts)

    scores = forecaster.compute(n_bins=8)
    scores["true_p"] = true_p
    scores["num_traders"] = num_traders
    scores["b_strategy"] = str(b) if not callable(b) else "adaptive"
    return scores


def run_fixed_b_sweep(
    true_p: float = 0.7,
    b_values: list[float] | None = None,
    num_traders: int = 25,
    trades_per_trader: int = 2,
    seed: int = 123,
) -> dict[float, dict[str, Any]]:
    """Sweep over several fixed b values and return calibration scores."""
    if b_values is None:
        b_values = [5.0, 15.0, 30.0, 60.0, 120.0]

    results = {}
    for b in b_values:
        res = simulate_belief_market(
            true_p=true_p,
            num_traders=num_traders,
            b=b,
            trades_per_trader=trades_per_trader,
            seed=seed,
        )
        results[b] = res
    return results


def compare_fixed_vs_adaptive(
    true_p: float = 0.72,
    num_traders: int = 30,
    fixed_bs: list[float] | None = None,
    adaptive_alphas: list[float] | None = None,
    seed: int = 7,
) -> dict[str, Any]:
    """
    Direct head-to-head between several fixed b values and several adaptive strategies.
    Returns a comparison table (dict) + raw results.
    """
    if fixed_bs is None:
        fixed_bs = [10.0, 25.0, 50.0, 100.0]
    if adaptive_alphas is None:
        adaptive_alphas = [0.03, 0.06, 0.12]

    results: dict[str, Any] = {"fixed": {}, "adaptive": {}}

    # Fixed
    for b in fixed_bs:
        res = simulate_belief_market(true_p=true_p, num_traders=num_traders, b=b, seed=seed)
        results["fixed"][b] = {
            "mean_brier": res["mean_brier"],
            "mean_log_score": res["mean_log_score"],
            "reliability": res["decomposition"]["reliability"],
        }

    # Adaptive (using Bounded + Linear for safety)
    # Alphas chosen around the recommendation tool's suggested_alpha = rec_b / total_volume
    # for a few-thousand-share market (see app.py b explorer). Lower alphas = slower b growth.
    for alpha in adaptive_alphas:
        strat = BoundedB(LinearVolumeB(alpha=alpha, min_b=8), min_b=8, max_b=300)
        res = simulate_belief_market(true_p=true_p, num_traders=num_traders, b=strat, seed=seed)
        results["adaptive"][alpha] = {
            "mean_brier": res["mean_brier"],
            "mean_log_score": res["mean_log_score"],
            "reliability": res["decomposition"]["reliability"],
            "final_b": res.get("final_b", None),  # not populated here but placeholder
        }

    return results


def print_comparison_table(results: dict[str, Any]) -> None:
    """Pretty print a simple comparison of mean Brier scores."""
    print("\nFixed b results:")
    print(f"{'b':>8}  {'mean_brier':>12}  {'mean_log':>12}  {'reliability':>12}")
    print("-" * 50)
    for b, s in sorted(results["fixed"].items()):
        print(f"{b:>8.1f}  {s['mean_brier']:>12.4f}  {s['mean_log_score']:>12.4f}  {s['reliability']:>12.4f}")

    print("\nAdaptive (Bounded(LinearVolumeB(alpha))) results:")
    print(f"{'alpha':>8}  {'mean_brier':>12}  {'mean_log':>12}  {'reliability':>12}")
    print("-" * 50)
    for alpha, s in sorted(results["adaptive"].items()):
        print(f"{alpha:>8.3f}  {s['mean_brier']:>12.4f}  {s['mean_log_score']:>12.4f}  {s['reliability']:>12.4f}")


def main() -> None:
    """Run a small self-contained demo when the file is executed directly."""
    print("=== LMSR Experiments Demo ===\n")

    # 1. Quick single run
    # b=40 picked via recommendation tool defaults (smallish subsidy + moderate bet size
    # and desired price impact to keep the demo responsive while still realistic).
    print("1. Single belief-market simulation (fixed b=40)")
    scores = simulate_belief_market(true_p=0.68, num_traders=20, b=40.0, trades_per_trader=2)
    print(f"   mean_brier={scores['mean_brier']:.4f}  mean_log={scores['mean_log_score']:.4f}")
    print(f"   decomposition: {scores['decomposition']}")

    # 2. Fixed b sweep
    print("\n2. Fixed-b sweep")
    sweep = run_fixed_b_sweep(true_p=0.68, b_values=[10, 25, 50, 100], num_traders=18)
    for b, s in sweep.items():
        print(f"   b={b:>5.0f}  brier={s['mean_brier']:.4f}  log={s['mean_log_score']:.4f}")

    # 3. Head-to-head fixed vs adaptive
    print("\n3. Fixed vs Adaptive comparison (true_p=0.75)")
    comp = compare_fixed_vs_adaptive(true_p=0.75, num_traders=22, seed=99)
    print_comparison_table(comp)

    print("\nDone. Import the functions to run your own sweeps or larger Monte Carlo studies.")


if __name__ == "__main__":
    main()
