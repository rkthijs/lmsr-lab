"""
Collection of the simplest trading bot archetypes for LMSR prediction markets.

This file implements clean, minimal versions of the basic bot types that can be
used with TradingAgent:

1. Random / Noise Trader
2. Threshold / Band Trader
3. Trend Follower (Momentum)
4. Mean Reversion / Contrarian
5. Belief-based / Fundamental (Kelly-style)
6. Probe / Inventory Bot
7. Simple Liquidity Provider (fee/spread earner)

All bots are written as single-step functions so they can be easily interleaved
on the same market.

Run:
    python examples/simple_bots.py

The main() at the bottom shows all of them trading together on one adaptive market.
"""

from __future__ import annotations

import random
import sys
from collections.abc import Callable
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.lmsr import LMSRMarketSimulator, TradingAgent
from src.lmsr.adaptive import BoundedB, LinearVolumeB


# =============================================================================
# 1. Random / Noise Trader
# =============================================================================
def random_trader(agent: TradingAgent, market_id: str, prob: float = 0.35, max_size: int = 5) -> None:
    """Trades completely at random. Great baseline and liquidity generator."""
    if random.random() > prob:
        return

    # Random side and direction
    side = random.choice(["yes", "no"])
    direction = random.choice([+1, -1])  # +1 = buy, -1 = sell
    size = random.randint(1, max_size)

    if side == "yes":
        res = agent.buy_yes(market_id, size) if direction > 0 else agent.sell_yes(market_id, size)
    else:
        res = agent.buy_no(market_id, size) if direction > 0 else agent.sell_no(market_id, size)

    if "error" not in res and res.get("cost", 0) != 0:
        action = "bought" if direction > 0 else "sold"
        print(f"    {agent.user_id} (random) {action} {size} {side} @ {res['cost']:.2f}")


# =============================================================================
# 2. Threshold / Band Trader
# =============================================================================
def threshold_trader(agent: TradingAgent, market_id: str, buy_below: float = 0.40, sell_above: float = 0.60, size: int = 4) -> None:
    """Buys when price is cheap, sells when expensive. Classic band trader."""
    p_yes = agent.get_prices(market_id)[0]
    pos = agent.get_position(market_id)
    held_yes = pos[0]

    if p_yes > sell_above and held_yes > 0:
        sell_size = min(size, held_yes)
        res = agent.sell_yes(market_id, sell_size)
        print(f"    {agent.user_id} (threshold) sold {sell_size} Yes @ {res['cost']:.2f}")
    elif p_yes < buy_below:
        res = agent.buy_yes(market_id, size)
        print(f"    {agent.user_id} (threshold) bought {size} Yes @ {res['cost']:.2f}")


# =============================================================================
# 3. Trend Follower (Momentum) — single step version
# =============================================================================
def trend_follower(agent: TradingAgent, market_id: str, buy_above: float = 0.55, sell_below: float = 0.45, size: int = 4) -> None:
    """Buys when price is high / rising, sells when low. Momentum style."""
    p_yes = agent.get_prices(market_id)[0]
    pos = [int(x) for x in agent.get_position(market_id)]
    cash = agent.get_cash_balance()
    pv = agent.get_position_value(market_id)
    total = agent.get_total_value()

    print(f"    {agent.user_id} (trend) Before: pos={pos}, pos_value={pv:.2f}, cash={cash:.2f}, total={total:.2f}")

    if p_yes > buy_above:
        res = agent.buy_yes(market_id, size)
        if "error" not in res:
            print(f"    {agent.user_id} (trend) bought {size} Yes @ cost {res['cost']:.2f} (fee {res.get('fee',0):.2f})")
        else:
            print(f"    {agent.user_id} (trend) failed to buy: {res.get('error')}")
    elif p_yes < sell_below and pos[0] > 0:
        sell_size = min(size, pos[0])
        res = agent.sell_yes(market_id, sell_size)
        if "error" not in res:
            print(f"    {agent.user_id} (trend) sold {sell_size} Yes @ cost {res['cost']:.2f} (fee {res.get('fee',0):.2f})")
        else:
            print(f"    {agent.user_id} (trend) failed to sell: {res.get('error')}")
    else:
        # Small probe when neutral (helps start positions)
        if pos[0] < 3:
            res = agent.buy_yes(market_id, 2)
            if "error" not in res:
                print(f"    {agent.user_id} (trend) probed +2 Yes @ cost {res['cost']:.2f} (fee {res.get('fee',0):.2f})")
            else:
                print(f"    {agent.user_id} (trend) failed probe: {res.get('error')}")
        else:
            print(f"    {agent.user_id} (trend) held (neutral)")

    # After state
    pos = [int(x) for x in agent.get_position(market_id)]
    cash = agent.get_cash_balance()
    pv = agent.get_position_value(market_id)
    total = agent.get_total_value()
    print(f"    {agent.user_id} (trend) After : pos={pos}, pos_value={pv:.2f}, cash={cash:.2f}, total={total:.2f}")


# =============================================================================
# 4. Mean Reversion / Contrarian — single step version
# =============================================================================
def mean_reversion(agent: TradingAgent, market_id: str, sell_above: float = 0.58, buy_below: float = 0.42, size: int = 5) -> None:
    """Sells when price is high, buys when low. Assumes reversion to ~0.5."""
    p_yes = agent.get_prices(market_id)[0]
    pos = [int(x) for x in agent.get_position(market_id)]
    cash = agent.get_cash_balance()
    pv = agent.get_position_value(market_id)
    total = agent.get_total_value()

    print(f"    {agent.user_id} (mean-rev) Before: pos={pos}, pos_value={pv:.2f}, cash={cash:.2f}, total={total:.2f}")

    if p_yes > sell_above and pos[0] > 0:
        sell_size = min(size, pos[0])
        res = agent.sell_yes(market_id, sell_size)
        if "error" not in res:
            print(f"    {agent.user_id} (mean-rev) sold {sell_size} Yes @ cost {res['cost']:.2f} (fee {res.get('fee',0):.2f})")
        else:
            print(f"    {agent.user_id} (mean-rev) failed to sell: {res.get('error')}")
    elif p_yes < buy_below:
        res = agent.buy_yes(market_id, size)
        if "error" not in res:
            print(f"    {agent.user_id} (mean-rev) bought {size} Yes @ cost {res['cost']:.2f} (fee {res.get('fee',0):.2f})")
        else:
            print(f"    {agent.user_id} (mean-rev) failed to buy: {res.get('error')}")
    else:
        print(f"    {agent.user_id} (mean-rev) waiting (price near mean)")

    pos = [int(x) for x in agent.get_position(market_id)]
    cash = agent.get_cash_balance()
    pv = agent.get_position_value(market_id)
    total = agent.get_total_value()
    print(f"    {agent.user_id} (mean-rev) After : pos={pos}, pos_value={pv:.2f}, cash={cash:.2f}, total={total:.2f}")


# =============================================================================
# 5. Belief-based / Fundamental Trader (simple Kelly-style)
# =============================================================================
def belief_trader(agent: TradingAgent, market_id: str, true_p: float, size: int = 5, min_edge: float = 0.08) -> None:
    """
    Trades according to an internal belief (true_p).

    Buys Yes if true_p is significantly higher than market price.
    Sells Yes if true_p is significantly lower.
    """
    p_yes = agent.get_prices(market_id)[0]
    pos = [int(x) for x in agent.get_position(market_id)]
    cash = agent.get_cash_balance()
    pv = agent.get_position_value(market_id)
    total = agent.get_total_value()
    edge = true_p - p_yes

    print(f"    {agent.user_id} (belief {true_p:.2f}) Before: pos={pos}, pos_value={pv:.2f}, cash={cash:.2f}, total={total:.2f}")

    if edge > min_edge:
        res = agent.buy_yes(market_id, size)
        if "error" not in res:
            print(f"    {agent.user_id} (belief {true_p:.2f}) bought {size} Yes (edge {edge:+.3f}) @ cost {res['cost']:.2f}")
        else:
            print(f"    {agent.user_id} (belief {true_p:.2f}) failed to buy: {res.get('error')}")
    elif edge < -min_edge:
        # Market price is much higher than our low belief → we think Yes is overpriced.
        # If we hold Yes, sell them. Otherwise, buy No (the cheap side) to bet against.
        if pos[0] > 0:
            sell_size = min(size, pos[0])
            res = agent.sell_yes(market_id, sell_size)
            if "error" not in res:
                print(f"    {agent.user_id} (belief {true_p:.2f}) sold {sell_size} Yes (edge {edge:+.3f}) @ cost {res['cost']:.2f}")
            else:
                print(f"    {agent.user_id} (belief {true_p:.2f}) failed to sell: {res.get('error')}")
        else:
            res = agent.buy_no(market_id, size)
            if "error" not in res:
                print(f"    {agent.user_id} (belief {true_p:.2f}) bought {size} No (edge {edge:+.3f}) @ cost {res['cost']:.2f}")
            else:
                print(f"    {agent.user_id} (belief {true_p:.2f}) failed to buy No: {res.get('error')}")
    else:
        print(f"    {agent.user_id} (belief {true_p:.2f}) waiting (no sufficient edge)")

    pos = [int(x) for x in agent.get_position(market_id)]
    cash = agent.get_cash_balance()
    pv = agent.get_position_value(market_id)
    total = agent.get_total_value()
    print(f"    {agent.user_id} (belief {true_p:.2f}) After : pos={pos}, pos_value={pv:.2f}, cash={cash:.2f}, total={total:.2f}")


# =============================================================================
# 6. Probe / Inventory Bot
# =============================================================================
def probe_inventory(agent: TradingAgent, market_id: str, target: int = 6, step_size: int = 3) -> None:
    """
    Tries to maintain a target inventory (long bias by default).
    Buys when below target, sells when above target.
    """
    pos = agent.get_position(market_id)
    held_yes = pos[0]

    if held_yes < target:
        size = min(step_size, target - held_yes)
        res = agent.buy_yes(market_id, size)
        print(f"    {agent.user_id} (inventory) bought {size} to reach target @ {res['cost']:.2f}")
    elif held_yes > target + 2:  # small buffer
        size = min(step_size, held_yes - target)
        res = agent.sell_yes(market_id, size)
        print(f"    {agent.user_id} (inventory) sold {size} to reach target @ {res['cost']:.2f}")


# =============================================================================
# 7. Simple Liquidity Provider (fee earner)
# =============================================================================
def liquidity_provider(agent: TradingAgent, market_id: str, size: int = 2) -> None:
    """
    Simple fee/spread earner.
    Buys a little of the cheaper side (Yes or No) to provide liquidity
    and earn the fee on both directions over time.
    """
    p_yes, p_no = agent.get_prices(market_id)

    if p_yes < p_no:
        # Yes is cheaper
        res = agent.buy_yes(market_id, size)
        if "error" not in res:
            print(f"    {agent.user_id} (LP) bought cheap Yes @ {res['cost']:.2f}")
    else:
        # No is cheaper
        res = agent.buy_no(market_id, size)
        if "error" not in res:
            print(f"    {agent.user_id} (LP) bought cheap No @ {res['cost']:.2f}")


# =============================================================================
# Helper to run many bots interleaved on one market
# =============================================================================
def run_interleaved_bots(
    sim: LMSRMarketSimulator,
    market_id: str,
    bots: list[tuple[TradingAgent, Callable[[TradingAgent, str], None]]],
    steps: int = 12,
) -> None:
    """Run all bots in interleaved fashion (each gets a turn every round)."""
    print(f"\n=== Running {len(bots)} bots interleaved for {steps} rounds ===\n")

    for step in range(1, steps + 1):
        print(f"--- Round {step} ---")
        p = bots[0][0].get_prices(market_id)
        print(f"Price: Yes={p[0]:.4f}  No={p[1]:.4f}")

        for agent, strategy in bots:
            strategy(agent, market_id)

        # Show current market state after all bots have had their turn this round.
        # (Not the "market total" — just the latest price and b for visibility.)
        p = bots[0][0].get_prices(market_id)
        current_b = bots[0][0].get_current_b(market_id)
        print(f"Round {step} complete. Price: Yes={p[0]:.4f}  b={current_b:.1f}\n")


def main() -> None:
    print("=== Simple Bots Demo ===\n")

    sim = LMSRMarketSimulator()

    # Create an adaptive market with *higher starting liquidity* so that the informed
    # bull (who knows the true probability is ~0.8) can gradually push the price from
    # the initial 0.5 towards 0.8 over many rounds without huge jumps per trade.
    adaptive = BoundedB(
        LinearVolumeB(alpha=0.08, min_b=40),
        min_b=40,
        max_b=400,
    )
    market = sim.create_market(
        title="Will the new feature launch on time? (true p_yes = 0.8, starts at 0.5)",
        b=adaptive,
        initial_subsidy=500.0,
        fee_rate=0.02,
    )

    # Create agents and pair them with strategies.
    # The "bull" knows the true probability that Yes wins is ~0.8 (market starts mispriced at 0.5).
    # The "bear" is badly miscalibrated.
    bots = [
        (TradingAgent(sim, "random1", "Random Noise"), lambda a, m: random_trader(a, m, prob=0.2, max_size=2)),
        (TradingAgent(sim, "threshold", "Threshold Band"), threshold_trader),
        (TradingAgent(sim, "trend", "Trend Follower"), lambda a, m: trend_follower(a, m, buy_above=0.70, size=2)),
        (TradingAgent(sim, "meanr", "Mean Reversion"), mean_reversion),
        (TradingAgent(sim, "bull", "Belief Bull (p=0.82)"), lambda a, m: belief_trader(a, m, true_p=0.82, size=8, min_edge=0.05)),
        (TradingAgent(sim, "bear", "Belief Bear (p=0.35)"), lambda a, m: belief_trader(a, m, true_p=0.35)),
        (TradingAgent(sim, "inventory", "Probe/Inventory"), probe_inventory),
        (TradingAgent(sim, "lp", "Liquidity Provider"), liquidity_provider),
    ]

    # Run them all interleaved
    run_interleaved_bots(sim, market.id, bots, steps=10)

    # Resolve the market to "yes" so that the true probability of 0.8 is realized
    # (the informed bull should profit, others may lose).
    print("\nResolving market to 'yes' (true underlying probability = 0.8)...")
    result = sim.resolve_market(market.id, "yes")

    # Show the market maker's actual P/L on this market.
    # In this setup the informed bull (plus some momentum/random buying of Yes)
    # bought shares while the price was still well below the true 0.8.
    # When it resolves to Yes, the house pays out more than it collected → it loses on this market.
    accounting = result.get("accounting_identity", {})
    print(f"Market maker net P/L on this market (remainder): {accounting.get('remainder', 'n/a'):.2f}")
    print("(This is subsidy + total_revenue - total_payouts. Negative means the house lost money.)")

    # Final summary with the three values we care about (after resolution payouts)
    print("\n=== Final State (all bots, after resolution) ===")
    for agent, _ in bots:
        cash = agent.get_cash_balance()
        pv = agent.get_position_value(market.id)
        total = agent.get_total_value()
        port = agent.get_portfolio()
        print(f"{agent.user_id:12}  cash={cash:8.2f}  pos_value={pv:7.2f}  total={total:8.2f}  "
              f"trades={len(sim.get_market(market.id).trades)}")

    engine = sim.get_market(market.id).engine
    print(f"\nMarket maker total_fees_earned (spread on all trades): {engine.total_fees_earned:.2f}")
    print("Note: fees are positive, but the net P/L after paying out the winning side can still be negative.")

    print("\n=== Done ===")
    print("You can now easily mix and match any of the bot functions above in your own experiments.")


if __name__ == "__main__":
    main()
