"""
Focused example: Two bots with *interleaved* strategies on the same adaptive market.

This is a minimal, self-contained demo whose only job is to show two
different automated strategies (trend-following vs mean-reversion) taking
turns on the *exact same market* every single round.

Key teaching points:
- True interleaving (both bots decide and trade in every round)
- How a strong trend can overwhelm mean-reversion (and how the mean-reversion
  bot still gets to act by selling into the move once it has a position)
- Clean per-round visibility of the three values every user cares about:
  cash balance, position value (MTM), and total account value
- Use of the high-level TradingAgent API on an adaptive-b market

For a broader tour (fixed-b single agent, sequential multi-agent, etc.)
see the main trading_agent.py example.

Run directly:
    python examples/interleaved_bots.py
"""

from __future__ import annotations

import sys
from pathlib import Path

# Allow running this script directly
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.lmsr import LMSRMarketSimulator, TradingAgent
from src.lmsr.adaptive import BoundedB, LinearVolumeB


def main() -> None:
    print("=== Interleaved Bots Example (Trend vs Mean-Reversion) ===\n")

    sim = LMSRMarketSimulator()

    trend = TradingAgent(sim, "trend_bot", display_name="Trend Follower")
    meanr = TradingAgent(sim, "mean_bot", display_name="Mean Reversion Bot")

    # Sensible adaptive liquidity (informed by the b-recommendation tool in app.py).
    # For a market that will see a few thousand shares of volume, alpha ~0.10
    # produces gradual but visible b growth while keeping early trades impactful.
    adaptive = BoundedB(
        LinearVolumeB(alpha=0.10, min_b=8),
        min_b=8,
        max_b=300,
    )

    m = trend.create_market(
        title="Will Q3 revenue beat expectations? (adaptive b)",
        b=adaptive,
        initial_subsidy=400.0,
        fee_rate=0.025,
    )
    # meanr automatically sees the same market

    print(f"Market: {m.title} (id={m.id})")
    print(f"Starting b = {trend.get_current_b(m.id):.1f} (is_adaptive=True)\n")

    # Give the mean-reversion bot a tiny initial long position while the price
    # is still near fair value. This lets it demonstrate mean-reversion (selling
    # into the trend-follower's push) within a short demo while still keeping
    # the example focused on interleaving.
    seed = meanr.buy_yes(m.id, 6)
    print(f"mean_bot seeded small initial long position near fair value @ cost {seed['cost']:.2f}\n")

    # ------------------------------------------------------------------
    # Interleaved execution: both bots decide and trade every round.
    # This is the key pedagogical difference from the main trading_agent.py
    # example (where one bot runs to completion before the other starts).
    # ------------------------------------------------------------------
    for step in range(1, 9):
        print(f"=== Round {step} ===")
        p = trend.get_prices(m.id)
        print(f"Market price: Yes={p[0]:.4f}  No={p[1]:.4f}   b={trend.get_current_b(m.id):.1f}")

        # --- Trend follower acts first this round ---
        print("  [Trend Follower]")
        t_pos = [int(x) for x in trend.get_position(m.id)]
        t_cash = trend.get_cash_balance()
        t_pv = trend.get_position_value(m.id)
        t_total = trend.get_total_value()
        print(f"    Before: pos={t_pos}, pos_value={t_pv:.2f}, cash={t_cash:.2f}, total={t_total:.2f}")

        t_p_yes = p[0]
        if t_p_yes > 0.55:
            size = 4
            res = trend.buy_yes(m.id, size)
            print(f"    Action: bought {size} Yes @ cost {res['cost']:.2f} (fee {res['fee']:.2f})")
        elif t_p_yes < 0.45 and t_pos[0] > 0:
            size = min(3, t_pos[0])
            res = trend.sell_yes(m.id, size)
            print(f"    Action: sold {size} Yes @ cost {res['cost']:.2f} (fee {res['fee']:.2f})")
        else:
            if t_pos[0] < 4:
                size = 2
                res = trend.buy_yes(m.id, size)
                print(f"    Action: probed +{size} Yes @ cost {res['cost']:.2f} (fee {res['fee']:.2f})")
            else:
                res = {"cost": 0.0, "fee": 0.0}
                print("    Action: held (neutral)")

        # Re-observe after the trade
        p = trend.get_prices(m.id)
        t_pos = [int(x) for x in trend.get_position(m.id)]
        t_cash = trend.get_cash_balance()
        t_pv = trend.get_position_value(m.id)
        t_total = trend.get_total_value()
        print(f"    After : pos={t_pos}, pos_value={t_pv:.2f}, cash={t_cash:.2f}, total={t_total:.2f}")

        # --- Mean-reversion bot acts second (sees the price move from the trend bot) ---
        print("  [Mean Reversion]")
        m_pos = [int(x) for x in meanr.get_position(m.id)]
        m_cash = meanr.get_cash_balance()
        m_pv = meanr.get_position_value(m.id)
        m_total = meanr.get_total_value()
        print(f"    Before: pos={m_pos}, pos_value={m_pv:.2f}, cash={m_cash:.2f}, total={m_total:.2f}")

        m_p_yes = p[0]
        if m_p_yes > 0.60 and m_pos[0] > 0:
            size = min(5, m_pos[0])
            res = meanr.sell_yes(m.id, size)
            print(f"    Action: sold {size} Yes (reverting) @ cost {res['cost']:.2f} (fee {res['fee']:.2f})")
        elif m_p_yes < 0.40:
            size = 5
            res = meanr.buy_yes(m.id, size)
            print(f"    Action: bought {size} Yes (reverting) @ cost {res['cost']:.2f} (fee {res['fee']:.2f})")
        else:
            res = {"cost": 0.0, "fee": 0.0}
            print("    Action: waiting (price near mean)")

        # Re-observe after the trade
        p = meanr.get_prices(m.id)
        m_pos = [int(x) for x in meanr.get_position(m.id)]
        m_cash = meanr.get_cash_balance()
        m_pv = meanr.get_position_value(m.id)
        m_total = meanr.get_total_value()
        print(f"    After : pos={m_pos}, pos_value={m_pv:.2f}, cash={m_cash:.2f}, total={m_total:.2f}")

        print()

    # ------------------------------------------------------------------
    # Final summary
    # ------------------------------------------------------------------
    print("=== Final state ===")
    for agent in (trend, meanr):
        cash = agent.get_cash_balance()
        pv = agent.get_position_value()
        total = agent.get_total_value()
        port = agent.get_portfolio()
        print(f"{agent.user_id:12}: cash={cash:8.2f}  pos_value={pv:7.2f}  total={total:8.2f}  "
              f"open_markets={port.open_markets_count}")

    engine = trend.get_market(m.id).engine
    print(f"\nMarket maker total_fees_earned on this market: {engine.total_fees_earned:.2f}")

    print("\n=== Example complete ===")
    print("This file shows pure interleaving. See trading_agent.py for a broader tour.")


if __name__ == "__main__":
    main()
