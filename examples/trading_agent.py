"""
Example: Using TradingAgent for bots and automated traders.

See also:
- examples/interleaved_bots.py for a focused, clean demonstration of two
  opposing strategies (trend + mean-reversion) running in a single interleaved loop.
"""

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
            trade_size = 8
            res = agent.buy_yes(market_id, trade_size)
            print(f"    {agent.user_id} bought {trade_size} Yes @ cost {res['cost']:.2f}")
        elif p_yes < 0.45 and held_yes > 0:
            # Trend down — sell some Yes
            sell_size = min(5, int(held_yes))
            res = agent.sell_yes(market_id, sell_size)
            print(f"    {agent.user_id} sold {sell_size} Yes, received { -res['cost']:.2f}")
        else:
            # Probe or hold
            if held_yes < 2:
                res = agent.buy_yes(market_id, 2)
                print(f"    {agent.user_id} probed +2 Yes @ cost {res['cost']:.2f}")

    final_pos = agent.get_position(market_id)
    print(f"  Final position for {agent.user_id}: yes={int(final_pos[0])}, no={int(final_pos[1])}")


def main() -> None:
    print("=== TradingAgent Example ===\n")

    sim = LMSRMarketSimulator()

    # === Single agent with fixed b ===
    print("1. Single agent — fixed liquidity")
    fixed_agent = TradingAgent(sim, "fixed_bot", display_name="Fixed-B Bot")

    # 1a. Exact round-trip first (own market, completely clean zero-position cycle)
    # b=25 chosen deliberately low (via the b-recommendation tool logic in app.py)
    # so that individual trades visibly move the price — essential for the pedagogical
    # round-trip / slippage / impact demo.
    # Using recommender formula with small typical_size=20, desired_move=10%, low activity:
    # b_conv ≈ (20*0.25)/0.10 * 0.7 ≈ 35; we use 25 for even stronger demo effect.
    print("\n   1a. Exact round-trip trade (buy X then sell *exactly* the same X back)")
    rt_m = fixed_agent.create_market(
        title="Exact round-trip demo (fixed b=25)",
        b=25.0,
        fee_rate=0.025,
    )
    rt_size = 15

    print(f"   Market: {rt_m.title} (id={rt_m.id})")
    p = fixed_agent.get_prices(rt_m.id)
    pos = [int(x) for x in fixed_agent.get_position(rt_m.id)]
    pos_val = fixed_agent.get_position_value(rt_m.id)
    cash = fixed_agent.get_cash_balance()
    total = fixed_agent.get_total_value()
    p_str = f"({p[0]:.4f}, {p[1]:.4f})"
    print(f"   Initial: price={p_str}, pos={pos}, pos_value={pos_val:.2f}, cash={cash:.2f}, total={total:.2f}")
    print("     (pos_value = mark-to-market value of shares at current prices;")
    print("      cash = cash balance; total = cash + pos_value across all markets.)")

    print("\n   Step: Buy 15 Yes")
    p = fixed_agent.get_prices(rt_m.id)
    pos = [int(x) for x in fixed_agent.get_position(rt_m.id)]
    pos_val = fixed_agent.get_position_value(rt_m.id)
    cash = fixed_agent.get_cash_balance()
    print(f"     Before: pos={pos}, pos_value={pos_val:.2f}, cash={cash:.2f}")
    buy_rt = fixed_agent.buy_yes(rt_m.id, shares=rt_size)
    p = fixed_agent.get_prices(rt_m.id)
    pos = [int(x) for x in fixed_agent.get_position(rt_m.id)]
    pos_val = fixed_agent.get_position_value(rt_m.id)
    cash = fixed_agent.get_cash_balance()
    print(
        f"     Trade : cost={buy_rt['cost']:.2f}, "
        f"raw={buy_rt['raw_cost']:.2f}, fee={buy_rt['fee']:.2f}"
    )
    print(f"     After : pos={pos}, pos_value={pos_val:.2f}, cash={cash:.2f}")

    print("\n   Step: Sell exactly 15 Yes (perfect round trip back to zero)")
    p = fixed_agent.get_prices(rt_m.id)
    pos = [int(x) for x in fixed_agent.get_position(rt_m.id)]
    pos_val = fixed_agent.get_position_value(rt_m.id)
    cash = fixed_agent.get_cash_balance()
    print(f"     Before: pos={pos}, pos_value={pos_val:.2f}, cash={cash:.2f}")
    sell_rt = fixed_agent.sell_yes(rt_m.id, shares=rt_size)
    p = fixed_agent.get_prices(rt_m.id)
    pos = [int(x) for x in fixed_agent.get_position(rt_m.id)]
    pos_val = fixed_agent.get_position_value(rt_m.id)
    cash = fixed_agent.get_cash_balance()
    print(
        f"     Trade : cost={sell_rt['cost']:.2f}, "
        f"raw={sell_rt['raw_cost']:.2f}, fee={sell_rt['fee']:.2f}"
    )
    print(f"     After : pos={pos}, pos_value={pos_val:.2f}, cash={cash:.2f}")
    net_cash = buy_rt['cost'] + sell_rt['cost']
    print(f"     Net round-trip cost: {net_cash:.2f} (= buy fee + sell fee earned by MM)")
    print(f"     Position on this market: {pos} (exactly [0, 0])")

    # 1b. Partial unwind after price move (on a second market)
    # Same low b=25 rationale as above (recommender with small bet size / high desired impact).
    print("\n   1b. Partial round-trip after price move (buy 30, sell only 12)")
    m_fixed = fixed_agent.create_market(
        title="Will the product launch on time? (fixed b=25)",
        b=25.0,
        fee_rate=0.025,
    )

    print(f"   Market: {m_fixed.title} (id={m_fixed.id})")
    p = fixed_agent.get_prices(m_fixed.id)
    pos = [int(x) for x in fixed_agent.get_position(m_fixed.id)]
    pos_val = fixed_agent.get_position_value(m_fixed.id)
    cash = fixed_agent.get_cash_balance()
    total = fixed_agent.get_total_value()
    p_str = f"({p[0]:.4f}, {p[1]:.4f})"
    print(f"   Initial: price={p_str}, pos={pos}, pos_value={pos_val:.2f}, cash={cash:.2f}, total={total:.2f}")

    print("\n   Step: Buy 30 Yes")
    p = fixed_agent.get_prices(m_fixed.id)
    pos = [int(x) for x in fixed_agent.get_position(m_fixed.id)]
    pos_val = fixed_agent.get_position_value(m_fixed.id)
    cash = fixed_agent.get_cash_balance()
    print(f"     Before: pos={pos}, pos_value={pos_val:.2f}, cash={cash:.2f}")
    res = fixed_agent.buy_yes(m_fixed.id, shares=30)
    p = fixed_agent.get_prices(m_fixed.id)
    pos = [int(x) for x in fixed_agent.get_position(m_fixed.id)]
    pos_val = fixed_agent.get_position_value(m_fixed.id)
    cash = fixed_agent.get_cash_balance()
    print(f"     Trade : cost={res['cost']:.2f}, raw={res['raw_cost']:.2f}, fee={res['fee']:.2f}")
    print(f"     After : pos={pos}, pos_value={pos_val:.2f}, cash={cash:.2f}")

    print("\n   Step: Observe (current state, no trade)")
    obs = fixed_agent.observe(m_fixed.id)
    p_str = f"({obs['prices'][0]:.4f}, {obs['prices'][1]:.4f})"
    pos_d = obs['position']
    pos_display = {"yes": int(pos_d.get("yes", 0)), "no": int(pos_d.get("no", 0)), "total": int(pos_d.get("total", 0))}
    print(
        f"     Observe: prices={p_str}, pos={pos_display}, "
        f"pos_value={obs['position_value']:.2f}, cash={obs['cash_balance']:.2f}, "
        f"total={obs['total_value']:.2f}"
    )

    print("\n   Step: Quote sell 12 Yes (preview, no state change)")
    quote = fixed_agent.quote(m_fixed.id, shares_yes=-12)
    print(
        f"     effective_cost={quote['effective_cost']:.2f}, "
        f"raw_cost={quote['raw_cost']:.2f}, fee={quote['fee']:.2f}"
    )

    print("\n   Step: Sell 12 Yes (only partial close)")
    p = fixed_agent.get_prices(m_fixed.id)
    pos = [int(x) for x in fixed_agent.get_position(m_fixed.id)]
    pos_val = fixed_agent.get_position_value(m_fixed.id)
    cash = fixed_agent.get_cash_balance()
    print(f"     Before: pos={pos}, pos_value={pos_val:.2f}, cash={cash:.2f}")
    res = fixed_agent.sell_yes(m_fixed.id, shares=12)
    p = fixed_agent.get_prices(m_fixed.id)
    pos = [int(x) for x in fixed_agent.get_position(m_fixed.id)]
    pos_val = fixed_agent.get_position_value(m_fixed.id)
    cash = fixed_agent.get_cash_balance()
    print(f"     Trade : cost={res['cost']:.2f}, raw={res['raw_cost']:.2f}, fee={res['fee']:.2f}")
    print(f"     After : pos={pos}, pos_value={pos_val:.2f}, cash={cash:.2f}")

    # === Multi-agent simulation with adaptive b ===
    print("\n2. Multi-agent simulation — adaptive liquidity")

    # Adaptive liquidity using the recommender guidance from app.py b-explorer.
    # For a market with "current_total" volume proxy ~1000- few k and rec_b ~200-300,
    # the tool suggests alpha ≈ rec_b / total ≈ 0.2–0.3. We use a conservative 0.10 here
    # (slower growth) + Bounded wrapper for safety in the multi-agent demo.
    # min_b kept low so early trades still have visible impact.
    adaptive = BoundedB(
        LinearVolumeB(alpha=0.10, min_b=8),
        min_b=8,
        max_b=300,
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

    # Give the mean-reversion bot a small initial long position while the price
    # is still near fair value (~0.5). This lets it demonstrate selling when the
    # trend follower later pushes the price up (classic mean-reversion behavior).
    # Without an initial position the mean bot would only print "tried to sell
    # but had no position" and appear to do nothing.
    seed = mean_agent.buy_yes(m_adaptive.id, 8)
    print(f"    {mean_agent.user_id} seeded small long position near fair value @ cost {seed['cost']:.2f}")

    # Run simple strategies for both agents.
    # Trend follower runs first and pushes price up; mean-reversion then sells
    # into the move (now that it has inventory).
    simple_trend_bot(trend_agent, m_adaptive.id, steps=6)

    # Mean-reversion style for the second agent
    print(f"\n--- {mean_agent.user_id} running mean-reversion style ---")
    for step in range(1, 5):
        p_yes = mean_agent.get_prices(m_adaptive.id)[0]
        pos = mean_agent.get_position(m_adaptive.id)
        held_yes = pos[0]
        print(f"  Step {step}: p_yes={p_yes:.3f}, held_yes={held_yes:.0f}, b={mean_agent.get_current_b(m_adaptive.id):.1f}")

        if p_yes > 0.62 and held_yes > 0:
            sell_size = min(6, held_yes)
            res = mean_agent.sell_yes(m_adaptive.id, sell_size)
            print(f"    {mean_agent.user_id} sold {sell_size} Yes on high price, received {-res['cost']:.2f}")
        elif p_yes < 0.48:
            res = mean_agent.buy_yes(m_adaptive.id, 6)
            print(f"    {mean_agent.user_id} bought on low price @ cost {res['cost']:.2f}")
        else:
            print(f"    {mean_agent.user_id} waiting (price near mean)")

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
