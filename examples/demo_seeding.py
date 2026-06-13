"""
Demo Seeding Helpers for the Streamlit LMSR App

These functions let you quickly populate a live LMSRMarketSimulator with
interesting, realistic states using the pre-generated trade histories.

This solves the "I always start from zero" problem in the demo.

Usage in app.py or notebooks:

    from examples.demo_seeding import (
        load_history_into_simulator,
        seed_rug_pull_demo,
        seed_kelly_high_activity,
        seed_full_teaching_demo,
    )

    sim = LMSRMarketSimulator()
    market_id = seed_rug_pull_demo(sim)
    # Now the sim has real trades, users, positions, etc.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from examples.ui_300_round_bots import seed_long_bot_demo
from src.lmsr.simulator import LMSRMarketSimulator

# ---------------------------------------------------------------------------
# Core reusable function
# ---------------------------------------------------------------------------

def load_history_into_simulator(
    sim: LMSRMarketSimulator,
    history_path: str | Path,
    b: float | None = None,
    fee_rate: float | None = None,
    initial_subsidy: float | None = None,
    market_title: str | None = None,
    resolve_to: str | None = None,
) -> str:
    """
    Replay a trade history JSON into an *existing* simulator.

    This creates a real Market + immutable Trade records + user balances
    inside the simulator, so Portfolio, Leaderboard, Scoring, and resolution
    all work afterward.

    Parameters
    ----------
    sim : LMSRMarketSimulator
        The live simulator you want to populate.
    history_path : str or Path
        Path to a file in examples/trade_histories/*.json
    b, fee_rate, initial_subsidy, market_title
        Override values from the history's "market_params" (if present).
    resolve_to : {"yes", "no", None}
        If set, automatically resolve the market after replaying trades.

    Returns
    -------
    market_id : str
        The ID of the newly created market inside the simulator.
    """
    path = Path(history_path)
    with open(path, encoding="utf-8") as f:
        history: dict[str, Any] = json.load(f)

    # Prefer values from the history file when available
    params = history.get("market_params", {})
    # default 25 only as fallback for old histories; new ones (and calls above) use
    # values chosen via the b-recommendation tool for plausibility.
    effective_b = b if b is not None else params.get("b", 25.0)
    effective_fee = fee_rate if fee_rate is not None else params.get("fee_rate", 0.025)
    effective_subsidy = (
        initial_subsidy if initial_subsidy is not None else params.get("initial_subsidy", 0.0)
    )

    title = market_title or history.get("name", path.stem.replace("_", " ").title())

    market = sim.create_market(
        title=title,
        description=history.get("description", ""),
        b=float(effective_b),
        fee_rate=float(effective_fee),
        initial_subsidy=float(effective_subsidy),
    )

    # Defensive: ensure the market is registered in the simulator (in case of
    # internal state issues after reset in the pro UI). This prevents
    # spurious "Market 'mX' does not exist" during replay.
    if market.id not in sim.markets:
        sim.markets[market.id] = market
        sim._positions_cache[market.id] = {}

    # Replay every trade from the history using the real simulator API
    for trade in history.get("trades", []):
        user = trade.get("user", "unknown")
        yes = float(trade.get("yes", 0.0))
        no = float(trade.get("no", 0.0))

        # This creates proper Trade records, updates balances, positions, etc.
        sim.place_trade(market.id, user, yes, no)

    # Optionally resolve (very useful for demoing scores + leaderboard + payouts)
    if resolve_to in ("yes", "no"):
        sim.resolve_market(market.id, resolve_to)

    return market.id


# ---------------------------------------------------------------------------
# Curated high-quality demo scenarios
# ---------------------------------------------------------------------------

def seed_balanced_demo(sim: LMSRMarketSimulator) -> str:
    """Simple balanced trading on both sides. Good for exploring price impact."""
    # b=25 (low) for this demo: using b-recommendation tool (small typical bet size + high desired
    # impact per trade) produces values in the 20-40 range. Low b makes individual trades move
    # prices visibly — good for teaching price impact and the recommender itself.
    return load_history_into_simulator(
        sim,
        "examples/trade_histories/balanced_trades.json",
        b=25.0,
        market_title="Balanced Trading Demo",
    )


def seed_rug_pull_demo(sim: LMSRMarketSimulator, resolved: bool = True) -> str:
    """
    Classic rug-pull style scenario (Kelly-sized whale + retail).
    Excellent for showing large price moves, then sudden reversal.
    """
    mid = load_history_into_simulator(
        sim,
        "examples/trade_histories/kelly_rug_pull.json",
        market_title="Kelly Rug Pull (Whale vs Retail)",
    )
    if resolved:
        # Resolve in the direction the whale was pushing (Yes in most of these)
        sim.resolve_market(mid, "yes")
    return mid


def seed_kelly_high_activity(sim: LMSRMarketSimulator) -> str:
    """Noisy, high-volume market with many users using Kelly-style sizing."""
    return load_history_into_simulator(
        sim,
        "examples/trade_histories/kelly_high_activity.json",
        market_title="High-Activity Kelly Market (Noisy)",
    )


def seed_long_trend_demo(sim: LMSRMarketSimulator) -> str:
    """Long gradual trend — good for seeing slow price discovery with higher b."""
    # b=60 chosen as a moderate "plausible" value via the recommendation tool
    # (typical_size ~50-70, desired_move ~6-8%, medium-high activity, subsidy 1000
    # → rec_b in 50-120 range; 60 is a nice sweet spot for a long slow trend demo).
    return load_history_into_simulator(
        sim,
        "examples/trade_histories/very_long_gradual_trend.json",
        b=60.0,
        market_title="Very Long Gradual Trend",
    )


def seed_experts_vs_punters(sim: LMSRMarketSimulator) -> str:
    """
    Long-horizon market with true probability 0.85.
    Small number of well-calibrated experts + large crowd of noisy punters.
    Excellent for exploring very high b (200-1000).
    """
    # Very high b=500 (or 280 when generating) is the plausible recommendation for this
    # large-scale, long-horizon, high-volume "Experts vs Punters" market.
    # Recommender with large effective volume / high subsidy tolerance easily suggests
    # 200–1000+ (see the b-explorer tool + the comment in generate_kelly_histories.py).
    return load_history_into_simulator(
        sim,
        "examples/trade_histories/experts_vs_punters_10000.json",
        b=500.0,  # High liquidity default to showcase the example's purpose (user can still slide 1-1000)
        market_title="Experts vs Punters (p=0.85)",
    )


def seed_full_teaching_demo(sim: LMSRMarketSimulator) -> list[str]:
    """
    Creates a rich multi-market state that shows off almost every feature:

    - One resolved rug-pull market (with stored scores + payouts)
    - One open high-activity market
    - One resolved long-trend market
    - Multiple users with different outcomes

    Returns the list of created market IDs.
    """
    mids = []

    # 1. Resolved rug pull (shows scores, payouts, leaderboard)
    mid1 = seed_rug_pull_demo(sim, resolved=True)
    mids.append(mid1)

    # 2. Open noisy high-activity market (live trading + portfolio view)
    mid2 = seed_kelly_high_activity(sim)
    mids.append(mid2)

    # 3. Another resolved market with different character
    mid3 = load_history_into_simulator(
        sim,
        "examples/trade_histories/kelly_long_trend.json",
        market_title="Long Trend Market (Resolved)",
    )
    sim.resolve_market(mid3, "yes")
    mids.append(mid3)

    return mids


# ---------------------------------------------------------------------------
# Convenience for the UI
# ---------------------------------------------------------------------------

SCENARIO_REGISTRY = {
    "Balanced Trading (Open)": seed_balanced_demo,
    "Kelly Rug Pull (Resolved)": seed_rug_pull_demo,
    "Kelly High-Activity (Open)": seed_kelly_high_activity,
    "Very Long Gradual Trend (Open)": seed_long_trend_demo,
    "Full Teaching Demo (Multi-Market)": seed_full_teaching_demo,
    "Experts vs Punters (p=0.85, long horizon)": seed_experts_vs_punters,
    "Long Bot Activity Demo (300 rounds, Open)": seed_long_bot_demo,
}


def get_available_scenarios() -> list[str]:
    """Return the list of friendly scenario names for UI dropdowns/buttons."""
    return list(SCENARIO_REGISTRY.keys())


def run_scenario(sim: LMSRMarketSimulator, name: str) -> str | list[str]:
    """
    Run a named scenario by its friendly name.

    Returns the market_id (or list of ids for multi-market scenarios).
    """
    if name not in SCENARIO_REGISTRY:
        raise ValueError(f"Unknown scenario: {name}. Available: {get_available_scenarios()}")
    return SCENARIO_REGISTRY[name](sim)
