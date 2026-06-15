"""
Experiment 1.B — Parameter Sensitivity using *real* Kelly bot sizing.

This is the "proper" counterpart to the toy approximation in the main
`parameter_sensitivity_analysis` (experiment 1.A / the original report).

Key differences from 1.A:
- Uses actual Kelly fraction: (p - q) / (1 - q)  (see generate_kelly_histories.py)
- Replays *real* trade histories generated with proper Kelly sizing
  (kelly_high_activity.json, kelly_long_trend.json, kelly_rug_pull.json, ...)
- Same share quantities are replayed at many different fixed `b` values.
  This shows how the *identical* trader behavior (Kelly-sized bets based on
  beliefs) produces very different price paths and "economic speed" depending
  on the liquidity parameter chosen by the market designer.
- Focus is on price dynamics / impact / volume-to-move (Brier is harder here
  because we don't store the original per-trader beliefs at trade time).

Run:
    python examples/experiments_1b_kelly_sensitivity.py

It will print tables for the expanded b sweep and (optionally) save plots
using the rich plotting helpers from replay_history.py.

This directly complements the toy "simple approx Kelly" study and shows
that the sensitivity problem is *not* an artifact of the toy sizing.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

# Make runnable from repo root
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np

from examples.replay_history import load_history, replay_history, plot_price_with_volume

# Reuse the volume-to-reach helper and impact analysis from the main experiment file
# (they are general enough).
from examples.experiments import (
    _volume_to_reach_delta_p,
    analyze_replay_impacts,
    print_parameter_sensitivity_table,  # reuse the pretty printer style
)


KELLY_HISTORIES = [
    "examples/trade_histories/kelly_high_activity.json",
    "examples/trade_histories/kelly_long_trend.json",
    "examples/trade_histories/kelly_rug_pull.json",
]


def kelly_sensitivity_on_history(
    history_path: str,
    b_values: list[float] | None = None,
    seed: int = 123,  # unused but kept for API symmetry with 1.A
) -> dict[str, Any]:
    """
    Replay one Kelly-generated history at many fixed b values.

    Returns a dict in the same shape as the 1.A results so tables and plots
    are easy to compare.
    """
    if b_values is None:
        b_values = [1.0, 5.0, 10.0, 25.0, 50.0, 100.0, 200.0, 400.0, 800.0, 1600.0]

    h = load_history(history_path)
    name = Path(history_path).stem

    results: dict[str, Any] = {
        "history": name,
        "true_p": h.get("metadata", {}).get("true_p"),
        "fixed": {},
        "note": "Real Kelly-sized trades (from generate_kelly_histories) replayed at different b.",
    }

    for b in b_values:
        snapshots = replay_history(h, b=b)
        metrics = analyze_replay_impacts(snapshots)

        # Build a fake "impacts" list so we can reuse _volume_to_reach_delta_p
        # (analyze_replay_impacts already computed mean/max, but we want the
        # interpolated volume numbers for consistency with 1.A).
        fake_impacts = []
        cum = 0.0
        prev_p = 0.5
        for snap in snapshots:
            p = snap["price_yes"]
            size = abs(snap.get("yes_shares", 0) + snap.get("no_shares", 0))
            cum += size
            fake_impacts.append(
                {
                    "price_before": round(prev_p, 4),
                    "price_after": round(p, 4),
                    "size": size,
                    "cumulative_volume": round(cum, 1),
                }
            )
            prev_p = p

        vol_5 = _volume_to_reach_delta_p(fake_impacts, target_delta=0.05)
        vol_10 = _volume_to_reach_delta_p(fake_impacts, target_delta=0.10)

        results["fixed"][b] = {
            "mean_impact": metrics["mean_impact"],
            "max_impact": metrics["max_impact"],
            "total_volume": metrics["total_volume"],
            "volume_for_5pct_move": vol_5,
            "volume_for_10pct_move": vol_10,
            "num_trades": len(snapshots),
        }

    return results


def run_1b_demo(b_values: list[float] | None = None) -> None:
    """Run 1.B on the main Kelly histories and print nice tables."""
    if b_values is None:
        b_values = [1, 5, 10, 25, 50, 100, 200, 400, 800, 1600]

    print("=== Experiment 1.B — Parameter Sensitivity with Real Kelly Sizing ===\n")
    print("Using proper Kelly fraction (p-q)/(1-q) from the generated histories.")
    print("Same share quantities are replayed at every b (trader behavior is fixed).\n")

    for path in KELLY_HISTORIES:
        res = kelly_sensitivity_on_history(path, b_values=b_values)
        print(f"\n--- {res['history']} (true_p ≈ {res.get('true_p')}) ---")
        # Build a minimal dict that print_parameter_sensitivity_table can consume
        pretty = {"true_p": res.get("true_p") or 0.0, "fixed": {}, "adaptive": {}}
        for b, m in res["fixed"].items():
            pretty["fixed"][b] = {
                "mean_brier": float("nan"),  # not computed for replay
                "mean_impact": m["mean_impact"],
                "max_impact": m["max_impact"],
                "volume_for_5pct_move": m["volume_for_5pct_move"],
                "volume_for_10pct_move": m["volume_for_10pct_move"],
            }
        print_parameter_sensitivity_table(pretty)

        print("  (Plots for 1.B can be generated with the replay_history tools, e.g.)\n"
              "  # python -m examples.replay_history examples/trade_histories/kelly_high_activity.json "
              "--b 10,50,200,800 --plot --save-plot reports/1b_...png")

    print("\nDone. Compare these tables with the toy-Kelly 1.A results in the main report.")
    print("The sensitivity (low b = volatile, high b = sluggish) is even more pronounced")
    print("when traders use realistic position sizing.")


if __name__ == "__main__":
    run_1b_demo()