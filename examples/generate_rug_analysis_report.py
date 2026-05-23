#!/usr/bin/env python3
"""
Generate a PDF report analyzing how different liquidity parameters (b)
affect price paths in various rug-pull and long-trend scenarios.

Usage:
    python examples/generate_rug_analysis_report.py
    python examples/generate_rug_analysis_report.py --output my_report.pdf --b 10,20,40,80
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import List

import numpy as np
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages

# Allow running this script directly from the project root
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from examples.replay_history import (
    load_history,
    compare_b_values,
    plot_price_with_volume,
)

# Default histories to analyze (prioritizing the principled Kelly-based ones)
DEFAULT_HISTORIES = [
    "examples/trade_histories/kelly_rug_pull.json",
    "examples/trade_histories/kelly_long_trend.json",
    "examples/trade_histories/kelly_high_activity.json",
    "examples/trade_histories/very_long_pump_and_rug.json",
    "examples/trade_histories/very_long_gradual_trend.json",
]

def compute_summary_stats(snapshots: List[dict]) -> dict:
    """Compute more interesting probabilistic statistics for a price path."""
    prices = np.array([s["price_yes"] for s in snapshots])
    deltas = np.diff(prices)

    qv = np.sum(deltas ** 2)                    # Realized quadratic variation
    tv = np.sum(np.abs(deltas))                 # Total variation
    roughness = tv / np.sqrt(qv) if qv > 0 else 0
    step_vol = np.sqrt(qv / len(deltas)) if len(deltas) > 0 else 0
    max_step = np.max(np.abs(deltas)) if len(deltas) > 0 else 0

    return {
        "steps": len(prices),
        "start_price": prices[0],
        "end_price": prices[-1],
        "max_price": np.max(prices),
        "min_price": np.min(prices),
        "quadratic_variation": qv,
        "total_variation": tv,
        "roughness": roughness,
        "step_volatility": step_vol,
        "max_one_step_move": max_step,
        "final_deviation_from_0.5": abs(prices[-1] - 0.5),
    }


def generate_report(
    history_paths: List[str],
    b_values: List[float],
    output_path: str = "examples/reports/rug_pull_analysis.pdf",
    title: str = "LMSR Rug Pull & Long Trend Analysis",
) -> None:
    """
    Generate a multi-page PDF comparing price paths across different b values
    for a list of trade histories.
    """
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with PdfPages(output_path) as pdf:
        # Title page
        fig, ax = plt.subplots(figsize=(11, 8.5))
        ax.axis("off")
        ax.text(0.5, 0.7, title, fontsize=24, ha="center", weight="bold")
        ax.text(0.5, 0.55, "Impact of Liquidity Parameter (b) on Price Paths", fontsize=14, ha="center")
        ax.text(0.5, 0.45, f"b values analyzed: {b_values}", fontsize=12, ha="center")
        ax.text(0.5, 0.35, "Generated from example trade histories in examples/trade_histories/", fontsize=10, ha="center", style="italic")
        pdf.savefig(fig, bbox_inches="tight")
        plt.close(fig)

        # One page per history
        for hist_path in history_paths:
            print(f"Processing: {hist_path}")
            history = load_history(hist_path)
            name = history.get("name", Path(hist_path).stem)

            results = compare_b_values(history, b_values=b_values, print_table=False)

            # Generate price + volume plot and keep the figure open for adding the table
            fig = plot_price_with_volume(
                history,
                results,
                title=f"{name} — Price Path + Volume by b",
                show=False,
                save_path=None,
                close_fig=False,
                figsize=(11, 9.5),          # taller figure to leave room for the table
            )

            if fig is None:
                print(f"  Skipping {name} (matplotlib issue)")
                continue

            # Reserve space at the bottom and add the table there cleanly
            fig.subplots_adjust(bottom=0.20)

            ax_table = fig.add_axes([0.08, 0.03, 0.84, 0.14])
            ax_table.axis("off")

            table_data = [
                ["b", "QV", "TV", "Roughness", "Step Vol", "Max Step", "Final |p-0.5|"]
            ]
            for b in b_values:
                snaps = results[b]
                stats = compute_summary_stats(snaps)
                table_data.append([
                    str(b),
                    f"{stats['quadratic_variation']:.4f}",
                    f"{stats['total_variation']:.4f}",
                    f"{stats['roughness']:.3f}",
                    f"{stats['step_volatility']:.4f}",
                    f"{stats['max_one_step_move']:.4f}",
                    f"{stats['final_deviation_from_0.5']:.4f}",
                ])

            table = ax_table.table(
                cellText=table_data[1:],
                colLabels=table_data[0],
                loc="center",
                cellLoc="center",
            )
            table.auto_set_font_size(False)
            table.set_fontsize(9)
            table.scale(1.0, 1.4)

            pdf.savefig(fig, bbox_inches="tight")
            plt.close(fig)

        # Final summary page
        fig, ax = plt.subplots(figsize=(11, 8.5))
        ax.axis("off")
        ax.text(0.5, 0.85, "Key Observations", fontsize=18, ha="center", weight="bold")

        observations = [
            "• Lower b values cause much larger and faster price swings.",
            "• In rug-pull scenarios, low b makes the price run much higher before the dump.",
            "• High b markets are far more resilient to large single trades (less slippage).",
            "• In long gradual trends, low b can push prices close to 1.0, while high b stays moderate.",
            "• Rug pulls with fake volume (coordinated accounts) are more effective at low b.",
            "",
            "Recommendation for internal tools:",
            "  - Use moderate-to-high b (40–100) if you want stable prices and less manipulation risk.",
            "  - Use lower b (10–25) only when you want prices to be very responsive to new information.",
        ]

        y_pos = 0.75
        for line in observations:
            ax.text(0.1, y_pos, line, fontsize=11, transform=ax.transAxes)
            y_pos -= 0.055

        pdf.savefig(fig, bbox_inches="tight")
        plt.close(fig)

    print(f"\n✅ PDF report saved to: {output_path}")


def main():
    parser = argparse.ArgumentParser(description="Generate rug-pull / long-trend analysis PDF.")
    parser.add_argument(
        "--histories",
        nargs="+",
        default=[
            "examples/trade_histories/kelly_rug_pull.json",
            "examples/trade_histories/kelly_long_trend.json",
            "examples/trade_histories/kelly_high_activity.json",
            "examples/trade_histories/very_long_pump_and_rug.json",
            "examples/trade_histories/very_long_gradual_trend.json",
        ],
        help="List of trade history JSON files to analyze",
    )
    parser.add_argument(
        "--b",
        default="10,25,50,100",
        help="Comma-separated list of b values",
    )
    parser.add_argument(
        "--output",
        default="examples/reports/rug_pull_b_analysis.pdf",
        help="Output PDF path",
    )

    args = parser.parse_args()
    b_values = [float(x.strip()) for x in args.b.split(",")]

    generate_report(
        history_paths=args.histories,
        b_values=b_values,
        output_path=args.output,
    )


if __name__ == "__main__":
    main()