"""
Helper functions to load trade histories and replay them with different liquidity (b) values.

This is useful for exploring how the liquidity parameter `b` affects price paths
in a binary LMSR market.

Example usage (from project root):

    from examples.replay_history import load_history, compare_b_values, print_price_paths

    history = load_history("examples/trade_histories/balanced_trades.json")
    results = compare_b_values(history, b_values=[10, 25, 50, 100], print_table=False)
    print_price_paths(results)
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

# Allow running this script directly (e.g. `python examples/replay_history.py`)
# by adding the project root to the Python path.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.lmsr.simulator import LMSRMarketSimulator

# matplotlib is optional (only needed for plot_price_paths)
try:
    import matplotlib.pyplot as plt
    HAS_MATPLOTLIB = True
except ImportError:
    HAS_MATPLOTLIB = False
    plt = None


def load_history(path: str | Path) -> dict[str, Any]:
    """Load a trade history from a JSON file."""
    path = Path(path)
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def replay_history(history: dict[str, Any], b: float = 25.0) -> list[dict[str, Any]]:
    """
    Replay a trade history using a fresh simulator with the given liquidity `b`.

    Returns a list of snapshots after each trade:
        {
            "step": 0,
            "user": "...",
            "yes_shares": 0.0,
            "no_shares": 0.0,
            "price_yes": 0.5,
            "price_no": 0.5,
            "cost": 0.0,
        }
    """
    sim = LMSRMarketSimulator()
    market = sim.create_market(
        title=history.get("name", "Replay Market"),
        b=b,
        fee_rate=0.0,  # Turn fees off for cleaner price path analysis
    )

    snapshots = []

    for i, trade in enumerate(history["trades"], start=1):
        user = trade["user"]
        yes = trade.get("yes", 0.0)
        no = trade.get("no", 0.0)

        cost, _ = market.engine.quote(yes, no)
        sim.place_trade(market.id, user, yes, no)

        p_yes, p_no = market.engine.price()

        snapshots.append({
            "step": i,
            "user": user,
            "yes_shares": yes,
            "no_shares": no,
            "price_yes": round(p_yes, 4),
            "price_no": round(p_no, 4),
            "cost": round(cost, 4),
        })

    return snapshots


def compare_b_values(
    history: dict[str, Any],
    b_values: list[float] | None = None,
    print_table: bool = True,
) -> dict[float, list[dict]]:
    """
    Replay the same trade history with multiple values of `b` and compare price paths.

    Returns a dict mapping each b value to its list of price snapshots.
    """
    if b_values is None:
        b_values = [10.0, 25.0, 50.0, 100.0]

    results = {}

    for b in b_values:
        snapshots = replay_history(history, b=b)
        results[b] = snapshots

        if print_table:
            print(f"\n=== b = {b} ===")
            print(f"{'Step':<5} {'User':<10} {'Yes':>6} {'No':>6} {'P(Yes)':>8} {'P(No)':>8} {'Cost':>8}")
            print("-" * 55)
            for s in snapshots:
                print(
                    f"{s['step']:<5} "
                    f"{s['user']:<10} "
                    f"{s['yes_shares']:>6.1f} "
                    f"{s['no_shares']:>6.1f} "
                    f"{s['price_yes']:>8.4f} "
                    f"{s['price_no']:>8.4f} "
                    f"{s['cost']:>8.4f}"
                )

    return results


def print_price_paths(results: dict[float, list[dict]]) -> None:
    """Pretty-print how the Yes price evolves for each b value."""
    print("\nPrice path comparison (P(Yes) after each trade):")
    print(f"{'Step':<5}", end="")
    for b in results:
        print(f"b={b:<6}", end="")
    print()

    n_steps = len(next(iter(results.values())))
    for i in range(n_steps):
        print(f"{i+1:<5}", end="")
        for b in results:
            price = results[b][i]["price_yes"]
            print(f"{price:<8.4f}", end="")
        print()


def plot_price_paths(
    results: dict[float, list[dict]],
    title: str = "Price Path Comparison (P(Yes))",
    show: bool = True,
    save_path: str | None = None,
) -> None:
    """
    Plot the Yes-price evolution for different b values.

    Requires matplotlib. Install with: pip install matplotlib
    """
    if not HAS_MATPLOTLIB:
        print("matplotlib is not installed. Run: pip install matplotlib")
        return

    plt.figure(figsize=(10, 6))

    for b, snapshots in results.items():
        steps = [s["step"] for s in snapshots]
        prices = [s["price_yes"] for s in snapshots]
        plt.plot(steps, prices, marker="o", markersize=3, label=f"b = {b}")

    plt.xlabel("Trade Step")
    plt.ylabel("Price of Yes")
    plt.title(title)
    plt.legend()
    plt.grid(True, alpha=0.3)
    plt.ylim(0, 1.05)

    if save_path:
        plt.savefig(save_path, dpi=150, bbox_inches="tight")
        print(f"Plot saved to {save_path}")

    if show:
        plt.show()


def plot_price_with_volume(
    history: dict[str, Any],
    results: dict[float, list[dict]],
    title: str = "Price Path + Volume",
    save_path: str | None = None,
    show: bool = True,
    close_fig: bool = True,
    figsize: tuple = (12, 8),
) -> plt.Figure | None:
    """
    Plot price paths for different b values on top,
    and Yes/No volume bars at the bottom for each trade step.

    This gives a clear view of buying pressure vs price reaction.
    """
    if not HAS_MATPLOTLIB:
        print("matplotlib is not installed. Run: pip install matplotlib")
        return

    trades = history["trades"]
    n_steps = len(trades)

    yes_vol = [float(t.get("yes", 0)) for t in trades]
    no_vol  = [float(t.get("no", 0)) for t in trades]
    steps = list(range(1, n_steps + 1))

    fig, (ax1, ax2) = plt.subplots(
        2, 1,
        figsize=figsize,
        gridspec_kw={'height_ratios': [3, 1]},
        sharex=True
    )

    # Top: Price paths
    for b, snapshots in results.items():
        prices = [s["price_yes"] for s in snapshots]
        ax1.plot(steps, prices, marker='o', markersize=2.5, linewidth=1.3, label=f"b = {b}")

    ax1.set_ylabel("Price of Yes")
    ax1.set_title(title)
    ax1.legend(loc="upper left", fontsize=9)
    ax1.grid(True, alpha=0.3)
    ax1.set_ylim(0, 1.05)

    # Bottom: Volume bars
    width = 0.35
    ax2.bar([s - width/2 for s in steps], yes_vol, width=width, label="Yes Volume", color="#2ecc71", alpha=0.85)
    ax2.bar([s + width/2 for s in steps], no_vol,  width=width, label="No Volume",  color="#e74c3c", alpha=0.85)

    ax2.set_xlabel("Trade Step")
    ax2.set_ylabel("Shares Traded")
    ax2.legend(loc="upper right", fontsize=9)
    ax2.grid(True, axis='y', alpha=0.3)

    plt.tight_layout()

    if save_path:
        plt.savefig(save_path, dpi=150, bbox_inches="tight")
        print(f"Plot saved to {save_path}")

    if show:
        plt.show()
    elif close_fig:
        plt.close(fig)

    return fig if not close_fig else None


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Replay trade histories with different b values.")
    parser.add_argument(
        "--history",
        default="examples/trade_histories/balanced_trades.json",
        help="Path to trade history JSON file",
    )
    parser.add_argument(
        "--b",
        default="10,25,50,100",
        help="Comma-separated list of b values to compare",
    )
    parser.add_argument(
        "--plot",
        action="store_true",
        help="Generate a matplotlib plot of the price paths",
    )
    parser.add_argument(
        "--save-plot",
        default=None,
        help="Path to save the plot image (e.g. plot.png)",
    )

    args = parser.parse_args()

    b_values = [float(x.strip()) for x in args.b.split(",")]
    history = load_history(args.history)

    print(f"Loaded: {history.get('name', args.history)}")
    print(f"Number of trades: {len(history['trades'])}")

    results = compare_b_values(history, b_values=b_values, print_table=True)
    print_price_paths(results)

    if args.plot or args.save_plot:
        plot_price_paths(
            results,
            title=f"Price Path: {history.get('name', Path(args.history).stem)}",
            show=args.plot,
            save_path=args.save_plot,
        )