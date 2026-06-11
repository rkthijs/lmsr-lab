"""
Example: Using TradingAgent for bots and automated traders.

This script demonstrates the high-level `TradingAgent` API (see `src/lmsr/agent.py`),
which is the recommended ergonomic interface for:

- Reinforcement learning agents
- Kelly-criterion or other scripted bots
- Market-making or arbitrage bots
- Multi-agent simulations

It shows:
- Creating agents (each tied to a stable user_id)
- Creating markets with both fixed and adaptive `b`
- Ergonomic trading (buy_yes / sell_yes etc.)
- Observing state (prices, current b for adaptive markets, positions, portfolio)
- Using `quote()` to evaluate hypothetical trades
- Running a tiny multi-agent simulation with simple strategies
- Inspecting fees/spread earned by the market maker

Run directly:
    python examples/trading_agent.py

Or import and reuse pieces in your own bot code.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Allow running this script directly (e.g. `python examples/trading_agent.py`)
# by adding the project root to the Python path.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.lmsr import LMSRMarketSimulator, TradingAgent
from src.lmsr.adaptive import BoundedB, LinearVolumeB


def simple_trend_bot(agent: TradingAgent, market_id: str, steps: int = 5) -> None:
    """
    A tiny example "bot" that follows a naive trend.

    - If current p_yes > 0.55 → buy Yes
    - If current p_yes < 0.45 → sell Yes (if holding)
    - Otherwise do nothing or a small probe trade

    This is deliberately simple for illustration — real bots would use
    better signals, position sizing (e.g. Kelly), and risk management.
    """
    print(f"\n--- {agent.user_id} running simple trend strategy ---")
    for step in range(1, steps + 1):
        prices = agent.get_prices(market_id)
        p_yes = prices[0]
        pos = agent.get_position(market_id)
        held_yes = pos[0]

        print(f"  Step {step}: p_yes={p_yes:.3f}, held_yes={held_yes:.1f}, "
              f"b={agent.get_current_b(market_id):.1f}")

        if p_yes > 0.55:
            # Trend up — buy more Yes
            trade_size = 8.0
            res = agent.buy_yes(market_id, trade_size)
            print(f"    {agent.user_id} bought {trade_size} Yes @ cost {res['cost']:.2f}")
        elif p_yes < 0.45 and held_yes > 0:
            # Trend down — sell some Yes
            sell_size = min(5.0, held_yes)
            res = agent.sell_yes(market_id, sell_size)
            print(f"    {agent.user_id} sold {sell_size} Yes, received { -res['cost']:.2f}")
        else:
            # Probe or hold
            if held_yes < 2.0:
                res = agent.buy_yes(market_id, 2.0)
                print(f"    {agent.user_id} probed +2 Yes @ cost {res['cost']:.2f}")

    final_pos = agent.get_position(market_id)
    print(f"  Final position for {agent.user_id}: yes={final_pos[0]:.1f}, no={final_pos[1]:.1f}")


def main() -> None:
    print("=== TradingAgent Example ===\n")

    sim = LMSRMarketSimulator()

    # === Single agent with fixed b ===
    print("1. Single agent — fixed liquidity")
    fixed_agent = TradingAgent(sim, "fixed_bot", display_name="Fixed-B Bot")

    m_fixed = fixed_agent.create_market(
        title="Will the product launch on time? (fixed b=25)",
        b=25.0,
        fee_rate=0.02,
    )

    print(f"   Created market: {m_fixed.title} (id={m_fixed.id})")
    print(f"   Initial prices: {fixed_agent.get_prices(m_fixed.id)}")

    # Use the ergonomic API
    fixed_agent.buy_yes(m_fixed.id, shares=30)
    print(f"   After buying 30 Yes: position={fixed_agent.get_position(m_fixed.id)}")

    # RL / bot friendly observation
    obs = fixed_agent.observe(m_fixed.id)
    print(f"   Observe: prices={obs['prices']}, b={obs['current_b']:.1f}, "
          f"pos={obs['position']}, balance={obs['balance']:.2f}")

    # Evaluate a sell without executing
    quote = fixed_agent.quote(m_fixed.id, shares_yes=-10)
    print(f"   Quote for selling 10 Yes: effective_cost={quote['effective_cost']:.2f}, "
          f"fee={quote['fee']:.2f}")

    fixed_agent.sell_yes(m_fixed.id, shares=12)
    print(f"   After selling 12 Yes: position={fixed_agent.get_position(m_fixed.id)}")
    print(f"   Balance: {fixed_agent.get_balance():.2f}")

    # === Multi-agent simulation with adaptive b ===
    print("\n2. Multi-agent simulation — adaptive liquidity")

    adaptive = BoundedB(
        LinearVolumeB(alpha=0.07, min_b=8),
        min_b=8,
        max_b=250,
    )

    trend_agent = TradingAgent(sim, "trend_bot", display_name="Trend Follower")
    mean_agent = TradingAgent(sim, "mean_bot", display_name="Mean Reversion Bot")

    m_adaptive = trend_agent.create_market(
        title="Will revenue beat Q3 target? (adaptive b)",
        b=adaptive,
        initial_subsidy=500.0,
    )
    # Both agents see the same market
    assert mean_agent.get_market(m_adaptive.id).id == m_adaptive.id

    print(f"   Created adaptive market (id={m_adaptive.id})")
    print(f"   Starting b = {trend_agent.get_current_b(m_adaptive.id):.1f} "
          f"(is_adaptive={trend_agent.is_adaptive_b(m_adaptive.id)})")

    # Run simple strategies for both agents
    simple_trend_bot(trend_agent, m_adaptive.id, steps=6)

    # Mean-reversion style for the second agent
    print(f"\n--- {mean_agent.user_id} running mean-reversion style ---")
    for step in range(1, 5):
        p_yes = mean_agent.get_prices(m_adaptive.id)[0]
        print(f"  Step {step}: p_yes={p_yes:.3f}, b={mean_agent.get_current_b(m_adaptive.id):.1f}")

        if p_yes > 0.62:
            res = mean_agent.sell_yes(m_adaptive.id, 6)
            if "error" in res:
                print(f"    {mean_agent.user_id} tried to sell but had no position yet")
            else:
                print(f"    {mean_agent.user_id} sold on high price, received {-res['cost']:.2f}")
        elif p_yes < 0.48:
            res = mean_agent.buy_yes(m_adaptive.id, 6)
            print(f"    {mean_agent.user_id} bought on low price @ cost {res['cost']:.2f}")

    # Final state for both agents
    print("\n=== Final state ===")
    for agent in (fixed_agent, trend_agent, mean_agent):
        port = agent.get_portfolio()
        print(f"{agent.user_id}: balance={agent.get_balance():.2f}, "
              f"open_markets={port.open_markets_count}, "
              f"resolved={port.resolved_markets_count}")

    # Show that the market maker earned spread on both buys and sells
    engine = trend_agent.get_market(m_adaptive.id).engine
    print(f"\nMarket maker total_fees_earned on adaptive market: "
          f"{engine.total_fees_earned:.2f}")

    print("\n=== Example complete ===")
    print("Try modifying the strategies or adding more agents!")


if __name__ == "__main__":
    main()
