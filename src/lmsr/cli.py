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

# Core simulator + DB (always available, no extra deps)
try:
    from src.lmsr import LMSRMarketSimulator
    from src.lmsr.db import SQLiteStore
except Exception:
    LMSRMarketSimulator = None  # type: ignore
    SQLiteStore = None  # type: ignore

# Experiments (optional, in examples/)
try:
    from examples.experiments import (
        compare_fixed_vs_adaptive,
        print_comparison_table,
        run_fixed_b_sweep,
    )
except ImportError:
    run_fixed_b_sweep = None
    compare_fixed_vs_adaptive = None
    print_comparison_table = None


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


def cmd_serve(args: argparse.Namespace) -> None:
    """Launch the FastAPI server."""
    try:
        from .api import run
    except ImportError as e:
        print("FastAPI support not installed. Run: pip install -e '.[api]'")
        raise SystemExit(1) from e
    run(host=args.host, port=args.port, reload=args.reload)


# --- DB subcommand (new, for SQLite persistence) ---

def _require_sim_or_store(db_path: str):
    if LMSRMarketSimulator is None or SQLiteStore is None:
        print("Core simulator/DB not available.")
        raise SystemExit(1)
    return LMSRMarketSimulator(db_path=db_path), SQLiteStore(db_path)


def cmd_db_inspect(args: argparse.Namespace) -> None:
    sim, _ = _require_sim_or_store(args.db)
    summary = sim.db_summary()
    print(f"DB: {args.db}")
    print(f"  Markets: {summary.get('num_markets', '?')}")
    print(f"  Users:   {summary.get('num_users', '?')}")
    print(f"  Trades:  {summary.get('num_trades', '?')}")
    for m in summary.get("sample_markets", []):
        print(f"  - {m['id']}: {m['title']} [{m['status']}]")


def cmd_db_list(args: argparse.Namespace) -> None:
    sim, _ = _require_sim_or_store(args.db)
    markets = sim.list_markets()
    if not markets:
        print("No markets in DB.")
        return
    print(f"{'ID':<6} {'Title':<40} {'Status':<10} {'Trades':>6}")
    print("-" * 65)
    for m in markets:
        n_trades = len(m.trades) if hasattr(m, "trades") else "?"
        print(f"{m.id:<6} {m.title[:40]:<40} {m.status:<10} {n_trades:>6}")


def cmd_db_reset(args: argparse.Namespace) -> None:
    if not args.yes:
        ans = input(f"Really clear ALL data in {args.db}? [y/N] ")
        if ans.lower() != "y":
            print("Aborted.")
            return
    sim, store = _require_sim_or_store(args.db)
    sim.reset()  # clears in-mem + calls clear_all on DB
    # also explicitly clear if needed
    try:
        store.clear_all()
    except Exception:
        pass
    print(f"DB {args.db} has been reset (all tables cleared).")


# --- State / JSON subcommand (new) ---

def cmd_state_save(args: argparse.Namespace) -> None:
    if LMSRMarketSimulator is None:
        print("Simulator not available.")
        raise SystemExit(1)
    if args.db:
        sim = LMSRMarketSimulator(db_path=args.db)
    else:
        sim = LMSRMarketSimulator()
    sim.save_json(args.json)
    print(f"Saved state to {args.json}")


def cmd_state_load(args: argparse.Namespace) -> None:
    if LMSRMarketSimulator is None:
        print("Simulator not available.")
        raise SystemExit(1)
    db_path = args.db or None
    sim = LMSRMarketSimulator.load_json(args.json, db_path=db_path)
    print(f"Loaded {args.json} into simulator (db={db_path or 'in-memory'})")
    print(f"  Markets loaded: {len(sim.list_markets())}")


# --- Experiment command (fleshed out) ---

def cmd_experiment(args: argparse.Namespace) -> None:
    if run_fixed_b_sweep is None or compare_fixed_vs_adaptive is None:
        print("experiments module not available (see examples/experiments.py).")
        raise SystemExit(1)

    name = (args.name or "sweep").lower()
    true_p = getattr(args, "true_p", 0.7)
    num_traders = getattr(args, "num_traders", 25)
    b_str = getattr(args, "b", None)
    output = getattr(args, "output", None)
    db_path = getattr(args, "db", None)

    if name in ("sweep", "fixed-sweep"):
        b_values = parse_b_values(b_str) if b_str else [10.0, 25.0, 50.0, 100.0]
        results = run_fixed_b_sweep(true_p=true_p, b_values=b_values, num_traders=num_traders)
        print(f"Fixed-b sweep (true_p={true_p}, n_traders={num_traders}):")
        for b, s in sorted(results.items()):
            print(f"  b={b:>6.1f}  brier={s['mean_brier']:.4f}  log={s['mean_log_score']:.4f}")
        if output:
            with open(output, "w") as f:
                import json
                json.dump({str(k): v for k, v in results.items()}, f, indent=2)
            print(f"  Saved to {output}")
    elif name in ("compare", "fixed-vs-adaptive"):
        comp = compare_fixed_vs_adaptive(true_p=true_p, num_traders=num_traders)
        print_comparison_table(comp)
        if output:
            with open(output, "w") as f:
                import json
                json.dump(comp, f, indent=2)
            print(f"  Saved to {output}")
    else:
        print(f"Unknown experiment '{name}'. Try 'sweep' or 'compare'.")
        print("See: python examples/experiments.py --help (or source)")

    if db_path:
        print(f"(Note: --db {db_path} was provided; persistence support in experiments is experimental.)")


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

    # Experiment runner (now functional)
    exp_p = subparsers.add_parser(
        "experiment",
        help="Run calibration experiments (sweep, compare fixed vs adaptive). See examples/experiments.py.",
    )
    exp_p.add_argument("name", nargs="?", default="sweep", help="sweep | compare")
    exp_p.add_argument("--true-p", type=float, default=0.7, help="True probability for belief simulation")
    exp_p.add_argument("--num-traders", type=int, default=25)
    exp_p.add_argument("--b", default=None, help="For sweep: comma list of b values")
    exp_p.add_argument("--output", default=None, help="Write results to JSON file")
    exp_p.add_argument("--db", default=None, help="(experimental) db_path for persistence during run")
    exp_p.set_defaults(func=cmd_experiment)

    # Serve the FastAPI backend (requires the [api] extra)
    serve_p = subparsers.add_parser(
        "serve",
        help="Run the FastAPI server (lmsr.api). Requires `pip install -e '.[api]'`.",
    )
    serve_p.add_argument("--host", default="0.0.0.0", help="Host to bind to")
    serve_p.add_argument("--port", type=int, default=8000, help="Port to listen on")
    serve_p.add_argument("--reload", action="store_true", help="Enable auto-reload (dev)")
    serve_p.set_defaults(func=cmd_serve)

    # DB management (new - for the SQLite persistence backend)
    db_p = subparsers.add_parser(
        "db",
        help="Inspect and manage .db files created with LMSRMarketSimulator(db_path=...).",
    )
    db_sub = db_p.add_subparsers(dest="db_cmd", required=True)

    insp = db_sub.add_parser("inspect", help="Print summary (markets, trades, users) of a DB file.")
    insp.add_argument("db", help="Path to SQLite DB (e.g. lmsr_demo.db)")
    insp.set_defaults(func=cmd_db_inspect)

    lst = db_sub.add_parser("list", help="List markets in the DB (id, title, status, #trades).")
    lst.add_argument("db")
    lst.set_defaults(func=cmd_db_list)

    rst = db_sub.add_parser("reset", help="DANGEROUS: clear all data in the given DB.")
    rst.add_argument("db")
    rst.add_argument("--yes", action="store_true", help="Do not ask for confirmation")
    rst.set_defaults(func=cmd_db_reset)

    # State / JSON (new - complements pickle and DB)
    st_p = subparsers.add_parser(
        "state",
        help="Save or load full simulator state as JSON (works with or without --db).",
    )
    st_sub = st_p.add_subparsers(dest="state_cmd", required=True)

    sv = st_sub.add_parser("save", help="Save simulator state (from a DB or fresh) to a JSON file.")
    sv.add_argument("json", help="Output .json path")
    sv.add_argument("--db", default=None, help="Read state from this DB file instead of empty sim")
    sv.set_defaults(func=cmd_state_save)

    ld = st_sub.add_parser("load", help="Load a JSON state file (optionally into a target DB).")
    ld.add_argument("json", help="Input .json path")
    ld.add_argument("--db", default=None, help="Target DB to load into (creates if needed)")
    ld.set_defaults(func=cmd_state_load)

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
