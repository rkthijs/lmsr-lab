"""
Experiments 1.B + 1.D — Parameter Sensitivity using *real* Kelly bot sizing
(on the generated kelly_*.json histories).

This file covers the "true Kelley" half of the four-variant study:

- 1.B. Fixed b with true Kelly
- 1.D. Adaptive b with true Kelly (replay of the same Kelly-sized trades
  while the market uses an adaptive b strategy)

Compare with:
- 1.A / 1.C in the main experiments.py (approximate/toy Kelly in small
  controlled belief-market simulations)

See the report (lmsr_parameter_sensitivity.md) for the full clearly-marked
structure and cross-comparison. All discussion is at the end of the report.

Run:
    python examples/experiments_1b_kelly_sensitivity.py
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

from src.lmsr.adaptive import BoundedB, LinearVolumeB, LogVolumeB, SqrtVolumeB


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
    1.B: Replay one Kelly-generated history at many *fixed* b values.

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


def kelly_adaptive_sensitivity_on_history(
    history_path: str,
    adaptive_strats: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    1.D: Replay one Kelly-generated history while using *adaptive* b strategies.

    The share quantities come from true Kelly traders, but the price path
    and impacts are determined by the adaptive liquidity rule chosen for the market.
    """
    if adaptive_strats is None:
        adaptive_strats = {
            "Bounded(Linear α=0.06)": BoundedB(LinearVolumeB(alpha=0.06, min_b=8), min_b=8, max_b=400),
            "Bounded(Log α=8)": BoundedB(LogVolumeB(alpha=8.0, min_b=8), min_b=8, max_b=400),
            "Bounded(Sqrt α=0.10)": BoundedB(SqrtVolumeB(alpha=0.10, min_b=8), min_b=8, max_b=400),
        }

    h = load_history(history_path)
    name = Path(history_path).stem

    results: dict[str, Any] = {
        "history": name,
        "true_p": h.get("metadata", {}).get("true_p"),
        "adaptive": {},
        "note": "Real Kelly-sized trades replayed under different adaptive b strategies.",
    }

    for name, strat in adaptive_strats.items():
        snapshots = replay_history(h, b=strat)
        metrics = analyze_replay_impacts(snapshots)

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

        results["adaptive"][name] = {
            "mean_impact": metrics["mean_impact"],
            "max_impact": metrics["max_impact"],
            "total_volume": metrics["total_volume"],
            "volume_for_5pct_move": vol_5,
            "volume_for_10pct_move": vol_10,
            "num_trades": len(snapshots),
        }

    return results


def run_1b_demo(b_values: list[float] | None = None) -> None:
    """Run 1.B (fixed) and 1.D (adaptive) on the main Kelly histories."""
    if b_values is None:
        b_values = [1, 5, 10, 25, 50, 100, 200, 400, 800, 1600]

    print("=== 1.B + 1.D: Parameter Sensitivity — True Kelly (replayed histories) ===\n")

    # === 1.B: Fixed b with true Kelly ===
    print("=== 1.B. Fixed b with True Kelly ===\n")
    print("Using proper Kelly fraction (p-q)/(1-q) from the generated histories.")
    print("Same share quantities are replayed at every fixed b (trader behavior is fixed).\n")

    for path in KELLY_HISTORIES:
        res = kelly_sensitivity_on_history(path, b_values=b_values)
        print(f"\n--- {res['history']} (true_p ≈ {res.get('true_p')}) ---")
        pretty = {"true_p": res.get("true_p") or 0.0, "fixed": {}, "adaptive": {}}
        for b, m in res["fixed"].items():
            pretty["fixed"][b] = {
                "mean_brier": float("nan"),
                "mean_impact": m["mean_impact"],
                "max_impact": m["max_impact"],
                "volume_for_5pct_move": m["volume_for_5pct_move"],
                "volume_for_10pct_move": m["volume_for_10pct_move"],
            }
        print_parameter_sensitivity_table(pretty)

        print("  (Plots for 1.B can be generated with the replay_history tools, e.g.)\n"
              "  # python -m examples.replay_history examples/trade_histories/kelly_high_activity.json "
              "--b 10,50,200,800 --plot --save-plot reports/1b_...png")

    # === 1.D: Adaptive b with true Kelly ===
    print("\n\n=== 1.D. Adaptive b with True Kelly ===\n")
    print("Same real Kelly-sized trades from the histories, but now the market uses")
    print("an adaptive b strategy during the replay. This shows how different adaptive")
    print("rules interact with realistic trader position sizing.\n")

    for path in KELLY_HISTORIES[:1]:  # one history for brevity in demo
        res = kelly_adaptive_sensitivity_on_history(path)
        print(f"\n--- {res['history']} (true_p ≈ {res.get('true_p')}) ---")
        pretty = {"true_p": res.get("true_p") or 0.0, "fixed": {}, "adaptive": {}}
        for name, m in res["adaptive"].items():
            pretty["adaptive"][name] = {
                "mean_brier": float("nan"),
                "mean_impact": m["mean_impact"],
                "max_impact": m["max_impact"],
                "volume_for_5pct_move": m["volume_for_5pct_move"],
                "volume_for_10pct_move": m["volume_for_10pct_move"],
            }
        print_parameter_sensitivity_table(pretty)

    print("\nDone. See the report for the full 1.A–1.D structure and consolidated discussion.")


if __name__ == "__main__":
    run_1b_demo()