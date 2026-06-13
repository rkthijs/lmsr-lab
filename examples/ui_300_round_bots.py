"""
UI Demo: 300 rounds of interleaved simple bots on one unresolved adaptive market.

This script creates a rich, live-looking unresolved market suitable for the
Streamlit UI (app.py). It runs a mix of simple bot strategies for 300 rounds
so that:
- Price starts at ~0.5
- An informed "bull" bot (true_p ≈ 0.82) gradually pushes the price toward the
  true value of 0.8
- Other bots (trend, mean-reversion, random, inventory, LP) add realistic
  activity, noise, and position building
- Adaptive b grows naturally with volume
- Fees accumulate
- Many open positions exist for users to see in the Portfolio tab

The market is deliberately left **unresolved** at the end.

Run:
    python examples/ui_300_round_bots.py

It will print progress every 50 rounds and a nice final summary.
You can then import the resulting state into the UI or run the app with
a pre-populated simulator.

Recommended for the UI:
- Higher starting liquidity (min_b) so price moves smoothly rather than in
  huge jumps.
- Mix of directional and non-directional bots.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# Import the clean single-step bot implementations
from examples.simple_bots import (
    belief_trader,
    liquidity_provider,
    mean_reversion,
    probe_inventory,
    random_trader,
    threshold_trader,
    trend_follower,
)
from src.lmsr import LMSRMarketSimulator, TradingAgent
from src.lmsr.adaptive import BoundedB, LinearVolumeB

# (old duplicate definition removed for cleanliness; the real implementation is below)


def seed_long_bot_demo(sim: LMSRMarketSimulator) -> str:
    """Create and populate a rich unresolved market using 300 rounds of
    interleaved simple bots (trend, mean-reversion, informed belief bull
    knowing true p≈0.8, random, inventory, LP, etc.).

    Starts at p=0.5, price drifts toward the true value as the informed
    bull trades. Adaptive b grows. Leaves the market open (unresolved)
    with lots of history and open interest — ideal for the Streamlit demo.

    Returns the market id.
    """
    # Higher starting liquidity for smooth price discovery from 0.5 → ~0.8
    adaptive = BoundedB(
        LinearVolumeB(alpha=0.07, min_b=60),
        min_b=60,
        max_b=500,
    )

    market = sim.create_market(
        title="Long Bot Activity Demo (300 rounds, true p≈0.8, Open)",
        b=adaptive,
        initial_subsidy=800.0,
        fee_rate=0.015,
    )

    # Defensive: ensure the market is registered in the simulator (in case of
    # internal state issues after reset in the pro UI load_scenario path).
    # This mirrors the hack in load_history_into_simulator and prevents
    # spurious "Market 'mX' does not exist" during the 300 rounds of bot trades.
    if market.id not in sim.markets:
        sim.markets[market.id] = market
        sim._positions_cache[market.id] = {}

    bots = [
        # Boost random to do more (higher probability and size for visible activity)
        # User names chosen to overlap with those appearing in the Kelly-based
        # histories (whale, punter_N, expert_N) used by Full Teaching Demo etc.
        # This makes cross-market user switcher views much richer when different
        # demo scenarios are loaded.
        (TradingAgent(sim, "punter_1", "Random Punter (boosted)"),
         lambda a, m: random_trader(a, m, prob=0.45, max_size=5)),
        (TradingAgent(sim, "punter_4", "Threshold Punter"), threshold_trader),
        # Trend heavily nerfed so it doesn't dominate (high threshold, tiny size).
        # We want the informed bull + contrarian/mean-reversion to be the stars.
        (TradingAgent(sim, "expert_1", "Trend Expert (light)"),
         lambda a, m: trend_follower(a, m, buy_above=0.92, size=1)),
        # Contrarian / Mean Reversion — seeded with initial long so it can
        # actively sell when the bull pushes price toward 0.8.
        (TradingAgent(sim, "punter_5", "Contrarian / Mean Reversion"), mean_reversion),
        (TradingAgent(sim, "whale", "Belief Bull (true≈0.82)"),
         lambda a, m: belief_trader(a, m, true_p=0.82, size=5, min_edge=0.05)),
        (TradingAgent(sim, "punter_30", "Belief Bear (true≈0.30, buys No when p high)"),
         lambda a, m: belief_trader(a, m, true_p=0.30, size=4, min_edge=0.05)),
        (TradingAgent(sim, "inv_1", "Inventory/Probe"), probe_inventory),
        (TradingAgent(sim, "lp_1", "Liquidity Provider"), liquidity_provider),
    ]

    # Seed initial long for the contrarian (mean-reversion) bot.
    # This is crucial so it has something to sell when price rises due to bull.
    # Without the seed it mostly sits at zero and "does nothing".
    contrarian_agent = bots[3][0]
    contrarian_agent.buy_yes(market.id, 15)

    # Run 300 interleaved rounds (quiet — no per-round prints for UI seeding)
    for step in range(1, 301):
        for agent, strategy in bots:
            strategy(agent, market.id)

    return market.id


def main() -> None:
    print("=== UI 300-Round Bot Demo (unresolved market) ===\n")

    # Use the same DB as the demo server so the populated state is visible
    # when running `lmsr serve` or the professional frontend.
    sim = LMSRMarketSimulator(db_path="lmsr_demo.db")

    mid = seed_long_bot_demo(sim)
    market = sim.get_market(mid)

    print(f"Created market: {market.title}")
    print(f"  id={market.id}")
    print(f"  Starting price ≈ 0.500, b starts at {market.current_b:.1f}")
    print("  Adaptive with alpha=0.07, min_b=60 (price drifts toward ~0.8)\n")

    # For standalone runs we still want to see progress
    # (the seed function above is the quiet version for UI)
    # Re-run a visible pass? For simplicity in standalone we just call the seed
    # and then print the final state using the simulator we already have.

    print("\n=== 300 rounds complete — market left UNRESOLVED ===")

    p_final = market.engine.price()
    b_final = market.current_b
    fees_final = market.engine.total_fees_earned

    print("\nFinal market state:")
    print(f"  Price: Yes={p_final[0]:.4f}  No={p_final[1]:.4f}")
    print(f"  Current b = {b_final:.1f}")
    print(f"  Total fees earned by MM = {fees_final:.2f}")

    print("\n=== Final positions & totals for all bots ===")
    # Re-create the same bot list just to report (they are already in the sim)
    # Simpler: just report the known user ids that were used
    for uid in ["punter_1", "punter_4", "expert_1", "punter_5", "whale", "punter_30", "inv_1", "lp_1"]:
        try:
            agent = TradingAgent(sim, uid)  # re-attaches to existing user
            cash = agent.get_cash_balance()
            pv = agent.get_position_value(mid)
            total = agent.get_total_value()
            pos = [int(x) for x in agent.get_position(mid)]
            print(f"{uid:12}  pos=[{pos[0]:5.0f},{pos[1]:5.0f}]  "
                  f"cash={cash:8.2f}  pos_value={pv:7.2f}  total={total:8.2f}")
        except Exception:
            pass

    print("\nMarket is ready to be used in the UI (unresolved, lots of open interest).")
    print(f"Market id = {market.id}")
    print("Users created (chosen to overlap with Kelly histories / Full Teaching Demo): punter_1, punter_4, expert_1, punter_5, whale, punter_30, inv_1, lp_1")
    print("Run the professional frontend (see start-professional-ui.sh) to switch between them and see what each sees across markets.")


if __name__ == "__main__":
    main()
