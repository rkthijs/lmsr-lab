"""
lmsr — Command-line interface for common LMSR experiment tasks.

This provides a small, stdlib-only entry point (argparse) for the most
frequently used experiment workflows mentioned in the project roadmap:

- Replaying trade histories with one or more values of `b`
- Comparing price paths across different liquidity levels
- (Future) batch scoring, experiment runners, etc.

The goal is to make it trivial to run things like:

    lmsr replay examples/trade_histories/kelly_rug_pull.json --b 10,25,50
    lmsr compare examples/trade_histories/balanced_trades.json --b 15,30,60 --plot

Without having to remember the full python path or example module names.

Usage after installation (or `pip install -e .`):

    lmsr --help
    lmsr replay --help

For development you can also run:

    python -m lmsr.cli --help
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Ensure we can import from the src layout and examples when running
# directly or via the installed script.
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    from examples.replay_history import (
        compare_b_values,
        load_history,
        plot_price_paths,
        print_price_paths,
    )
except ImportError as e:
    print("Error: Could not import replay tools. Make sure you're running from the project root or the package is installed.")
    print(f"Details: {e}")
    sys.exit(1)


def parse_b_values(b_str: str | None) -> list[float]:
    """Parse comma-separated b values, with sensible defaults."""
    if not b_str:
        return [10.0, 25.0, 50.0, 100.0]
    try:
        vals = [float(x.strip()) for x in b_str.split(",") if x.strip()]
        if not vals:
            raise ValueError
        return vals
    except Exception:
        raise argparse.ArgumentTypeError(
            f"Invalid --b value: {b_str}. Use comma-separated numbers, e.g. 10,25,50"
        ) from None


def cmd_replay(args: argparse.Namespace) -> None:
    """Replay a single history (or multiple b values) and optionally plot."""
    history_path = args.history
    b_values = parse_b_values(args.b)
    history = load_history(history_path)

    print(f"Replaying: {history.get('name', history_path)}")
    print(f"b values: {b_values}")

    results = compare_b_values(history, b_values=b_values, print_table=True)

    if args.plot or args.save_plot:
        title = f"Price Paths - {Path(history_path).stem}"
        plot_price_paths(
            results,
            title=title,
            show=args.plot,
            save_path=args.save_plot,
        )

    if args.print_paths:
        print_price_paths(results)


def cmd_compare(args: argparse.Namespace) -> None:
    """Alias for replay with multiple b values (more discoverable name)."""
    cmd_replay(args)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="lmsr",
        description="LMSR experiment CLI — small entry point for common tasks (replay, compare b, etc.).",
    )
    parser.add_argument(
        "--version", action="version", version="%(prog)s 0.1 (lmsr-lab)"
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    # replay
    replay_p = subparsers.add_parser(
        "replay",
        help="Replay a trade history with one or more b values.",
        description="Replay a JSON trade history using the simulator at different liquidity levels.",
    )
    replay_p.add_argument("history", help="Path to a trade history JSON file (e.g. examples/trade_histories/kelly_rug_pull.json)")
    replay_p.add_argument(
        "--b",
        default=None,
        help="Comma-separated b values, e.g. '10,25,50'. Defaults to 10,25,50,100.",
    )
    replay_p.add_argument(
        "--plot",
        action="store_true",
        help="Show a matplotlib plot of the price paths (requires matplotlib).",
    )
    replay_p.add_argument(
        "--save-plot",
        metavar="PATH",
        default=None,
        help="Save the price path plot to a file (e.g. plot.png).",
    )
    replay_p.add_argument(
        "--print-paths",
        action="store_true",
        help="Print a compact price-path table (P(Yes) per step per b).",
    )
    replay_p.set_defaults(func=cmd_replay)

    # compare (convenience alias with slightly different help)
    compare_p = subparsers.add_parser(
        "compare",
        help="Compare price paths across different b values for a history.",
    )
    compare_p.add_argument("history", help="Path to trade history JSON")
    compare_p.add_argument(
        "--b",
        default=None,
        help="Comma-separated b values (default: 10,25,50,100)",
    )
    compare_p.add_argument("--plot", action="store_true", help="Show plot")
    compare_p.add_argument("--save-plot", metavar="PATH", help="Save plot to file")
    compare_p.add_argument("--print-paths", action="store_true")
    compare_p.set_defaults(func=cmd_compare)

    # Future placeholder for batch scoring / experiments
    exp_p = subparsers.add_parser(
        "experiment",
        help="(placeholder) Run parameter sweeps or batch scoring (to be expanded).",
    )
    exp_p.add_argument("name", nargs="?", default="list", help="Experiment name or 'list'")
    exp_p.set_defaults(func=lambda a: print("Experiment runner not yet implemented. See examples/ for now."))

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        args.func(args)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
