#!/usr/bin/env python3
"""
Generate realistic trade histories using Kelly bettors on an LMSR market
with initial_subsidy ≈ 1000.

Each user has:
- Their own bankroll
- A subjective probability p (belief)
- They bet a fraction of their current wealth using (approximate) Kelly criterion
  based on the current market price.

This produces much more principled position sizes than the previous fixed-share histories.
"""

from __future__ import annotations

import json
import random
import sys
from pathlib import Path
from typing import List, Dict, Any

# Allow running directly
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.lmsr.simulator import LMSRMarketSimulator


def kelly_fraction(p: float, q: float) -> float:
    """
    Approximate Kelly fraction for a binary event when the market price is q
    and your belief is p.

    For small bets (low impact), if you believe p > q for Yes,
    the Kelly fraction of your bankroll to risk is roughly (p - q) / (1 - q).
    This is the standard Kelly for betting on an event that pays 1:1 net if you win.

    We clamp it to reasonable values.
    """
    if p <= q:
        return 0.0
    f = (p - q) / (1 - q)
    return max(0.0, min(f, 0.95))  # never bet more than 95% of wealth


def generate_kelly_history(
    name: str,
    description: str,
    num_users: int = 12,
    num_steps: int = 25,
    true_p: float = 0.65,
    belief_noise: float = 0.12,
    initial_bankroll: float = 1000.0,
    market_b: float = 40.0,
    initial_subsidy: float = 1000.0,
    seed: int = 42,
) -> Dict[str, Any]:
    """
    Simulate a sequence of trades from Kelly bettors.

    Returns a dict ready to be saved as a trade history JSON.
    """
    random.seed(seed)

    sim = LMSRMarketSimulator()
    market = sim.create_market(
        title=name,
        b=market_b,
        fee_rate=0.02,
        initial_subsidy=initial_subsidy,
    )

    # Create users with noisy beliefs around the true probability
    users = {}
    for i in range(num_users):
        uid = f"user_{i+1}"
        p = max(0.05, min(0.95, random.gauss(true_p, belief_noise)))
        users[uid] = {
            "belief": p,
            "bankroll": initial_bankroll * random.uniform(0.6, 1.6),
        }

    trades: List[Dict[str, Any]] = []

    for step in range(num_steps):
        # Pick a random user to trade this step
        uid = random.choice(list(users.keys()))
        u = users[uid]

        q_yes, q_no = market.engine.price()
        p = u["belief"]

        # Decide side
        if p > q_yes + 0.03:          # small threshold to avoid tiny bets
            side = "yes"
            q = q_yes
        elif (1 - p) > q_no + 0.03:
            side = "no"
            q = q_no
        else:
            continue  # no edge, skip

        # Kelly sizing (fraction of current bankroll)
        f = kelly_fraction(p if side == "yes" else (1-p), q)
        risk_amount = f * u["bankroll"]

        if risk_amount < 5.0:   # minimum meaningful bet with 1000 bankroll
            continue

        # Convert desired risk into whole shares
        approx_shares = risk_amount / max(q, 0.01)

        # Try rounding to nearest integer (no fractional shares)
        shares = max(1, int(round(approx_shares)))

        # Check actual cost for this integer amount
        if side == "yes":
            cost, _ = market.engine.quote(shares, 0)
        else:
            cost, _ = market.engine.quote(0, shares)

        # If the actual cost is higher than risk_amount due to slippage, reduce shares
        while cost > risk_amount and shares > 1:
            shares -= 1
            if side == "yes":
                cost, _ = market.engine.quote(shares, 0)
            else:
                cost, _ = market.engine.quote(0, shares)

        # Final sanity: at least 1 share if they decided to bet
        if side == "yes":
            trades.append({"user": uid, "yes": shares, "no": 0.0})
            sim.place_trade(market.id, uid, shares, 0)
            u["bankroll"] -= cost
        else:
            trades.append({"user": uid, "yes": 0.0, "no": shares})
            sim.place_trade(market.id, uid, 0, shares)
            u["bankroll"] -= cost

    return {
        "name": name,
        "description": description,
        "market_params": {
            "b": market_b,
            "initial_subsidy": initial_subsidy,
            "fee_rate": 0.02,
        },
        "trades": trades,
    }


def save_history(history: dict, filename: str) -> None:
    path = Path(filename)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(history, f, indent=2)
    print(f"Saved {len(history['trades'])} trades → {filename}")


if __name__ == "__main__":
    import json

    # === Generate several interesting histories with ~1000 subsidy ===

    # 1. Classic slow pump then rug (Kelly sized)
    h1 = generate_kelly_history(
        name="Kelly Classic Rug Pull",
        description="Whale with strong belief slowly accumulates using Kelly sizing, retail with noisier beliefs pile in, then whale dumps hard.",
        num_users=15,
        num_steps=32,
        true_p=0.72,
        belief_noise=0.18,
        initial_bankroll=1000.0,
        market_b=45.0,
        initial_subsidy=1000.0,
        seed=123,
    )
    save_history(h1, "examples/trade_histories/kelly_rug_pull.json")

    # 2. Very long gradual trend with Kelly bettors
    h2 = generate_kelly_history(
        name="Kelly Long Gradual Trend",
        description="Many Kelly bettors with moderately bullish beliefs slowly push the price over a long period (40 trades).",
        num_users=18,
        num_steps=40,
        true_p=0.68,
        belief_noise=0.15,
        initial_bankroll=1000.0,
        market_b=50.0,
        initial_subsidy=1000.0,
        seed=456,
    )
    save_history(h2, "examples/trade_histories/kelly_long_trend.json")

    # 3. Noisy market with Kelly sizing (more realistic)
    h3 = generate_kelly_history(
        name="Kelly High-Activity Noisy Market",
        description="Many users with different beliefs trade frequently using Kelly. More realistic volume pattern.",
        num_users=22,
        num_steps=45,
        true_p=0.55,
        belief_noise=0.22,
        initial_bankroll=1000.0,
        market_b=35.0,
        initial_subsidy=1000.0,
        seed=789,
    )
    save_history(h3, "examples/trade_histories/kelly_high_activity.json")

    print("\nAll Kelly-based histories generated with initial_subsidy ≈ 1000.")