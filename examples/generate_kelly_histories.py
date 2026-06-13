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
from typing import Any

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
    num_steps: int = 25,
    true_p: float = 0.65,
    # --- New heterogeneous population support (experts vs punters) ---
    num_experts: int = 0,
    expert_noise: float = 0.04,
    num_punters: int = 12,
    punter_noise: float = 0.18,
    punter_mean: float | None = None,   # if None, use true_p
    belief_noise: float = 0.12,         # legacy uniform mode (used when num_experts==0)
    initial_bankroll: float = 1000.0,
    market_b: float = 40.0,
    initial_subsidy: float = 1000.0,
    min_edge: float = 0.025,
    seed: int = 42,
) -> dict[str, Any]:
    """
    Simulate a sequence of trades from Kelly bettors.

    Supports two modes:
    - Legacy: all users have beliefs ~ N(true_p, belief_noise)
    - Heterogeneous (recommended for realistic "experts vs punters"):
        num_experts + num_punters populations with different noise levels.

    The liquidity parameter `market_b` can now comfortably go up to 1000+.
    """
    random.seed(seed)

    if punter_mean is None:
        punter_mean = true_p

    sim = LMSRMarketSimulator()
    market = sim.create_market(
        title=name,
        b=market_b,
        fee_rate=0.02,
        initial_subsidy=initial_subsidy,
    )

    # Create users — support both legacy uniform noise and heterogeneous experts/punters
    users = {}
    user_id = 1

    # Experts (well calibrated, low noise)
    for _ in range(num_experts):
        uid = f"expert_{user_id}"
        p = max(0.05, min(0.95, random.gauss(true_p, expert_noise)))
        users[uid] = {
            "belief": p,
            "bankroll": initial_bankroll * random.uniform(0.7, 1.8),
            "type": "expert",
        }
        user_id += 1

    # Punters (noisier or biased beliefs)
    for _ in range(num_punters):
        uid = f"punter_{user_id}"
        p = max(0.05, min(0.95, random.gauss(punter_mean, punter_noise)))
        users[uid] = {
            "belief": p,
            "bankroll": initial_bankroll * random.uniform(0.4, 1.4),
            "type": "punter",
        }
        user_id += 1

    # Legacy fallback (when no experts/punters specified)
    if num_experts == 0 and num_punters == 0:
        for i in range(12):  # default
            uid = f"user_{i+1}"
            p = max(0.05, min(0.95, random.gauss(true_p, belief_noise)))
            users[uid] = {
                "belief": p,
                "bankroll": initial_bankroll * random.uniform(0.6, 1.6),
            }

    trades: list[dict[str, Any]] = []

    for step in range(num_steps):
        # Pick a random user to trade this step
        uid = random.choice(list(users.keys()))
        u = users[uid]

        q_yes, q_no = market.engine.price()
        p = u["belief"]

        did_trade = False

        # --- BUY LOGIC (positive edge) ---
        if p > q_yes + min_edge:
            side = "yes"
            q = q_yes
            f = kelly_fraction(p, q)
            risk_amount = f * u["bankroll"]
            if risk_amount >= 5.0:
                approx_shares = risk_amount / max(q, 0.01)
                shares = max(1, int(round(approx_shares)))
                if side == "yes":
                    cost, _ = market.engine.quote(shares, 0)
                else:
                    cost, _ = market.engine.quote(0, shares)
                while cost > risk_amount and shares > 1:
                    shares -= 1
                    if side == "yes":
                        cost, _ = market.engine.quote(shares, 0)
                    else:
                        cost, _ = market.engine.quote(0, shares)
                if shares >= 1:
                    trades.append({"user": uid, "yes": shares, "no": 0.0})
                    sim.place_trade(market.id, uid, shares, 0)
                    u["bankroll"] -= cost
                    did_trade = True

        elif (1 - p) > q_no + min_edge and not did_trade:
            side = "no"
            q = q_no
            f = kelly_fraction(1-p, q)
            risk_amount = f * u["bankroll"]
            if risk_amount >= 5.0:
                approx_shares = risk_amount / max(q, 0.01)
                shares = max(1, int(round(approx_shares)))
                cost, _ = market.engine.quote(0, shares)
                while cost > risk_amount and shares > 1:
                    shares -= 1
                    cost, _ = market.engine.quote(0, shares)
                if shares >= 1:
                    trades.append({"user": uid, "yes": 0.0, "no": shares})
                    sim.place_trade(market.id, uid, 0, shares)
                    u["bankroll"] -= cost
                    did_trade = True

        # --- SELL LOGIC (negative edge on existing position, with SELL ALL) ---
        if not did_trade:
            pos = sim.get_user_position(market.id, uid)
            sold = False

            # Sell Yes if we hold and belief is now too low
            if pos[0] > 0 and p < q_yes - min_edge:
                if random.random() < 0.6:
                    shares = int(pos[0])          # SELL ALL
                else:
                    shares = max(1, int(pos[0] * random.uniform(0.4, 0.85)))
                trades.append({"user": uid, "yes": -shares, "no": 0.0})
                sim.place_trade(market.id, uid, -shares, 0)
                cost, _ = market.engine.quote(-shares, 0)
                u["bankroll"] -= cost
                sold = True
                did_trade = True

            # Sell No if we hold and belief is now too high for No
            if not sold and pos[1] > 0 and (1 - p) < q_no - min_edge:
                if random.random() < 0.6:
                    shares = int(pos[1])          # SELL ALL
                else:
                    shares = max(1, int(pos[1] * random.uniform(0.4, 0.85)))
                trades.append({"user": uid, "yes": 0.0, "no": -shares})
                sim.place_trade(market.id, uid, 0, -shares)
                cost, _ = market.engine.quote(0, -shares)
                u["bankroll"] -= cost
                did_trade = True

        # If nothing happened this step, just continue (rare with many users)

    return {
        "name": name,
        "description": description,
        "market_params": {
            "b": market_b,
            "initial_subsidy": initial_subsidy,
            "fee_rate": 0.02,
            "true_p": true_p,
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

    # 1. Classic slow pump then rug (Kelly sized, now with sells + longer)
    h1 = generate_kelly_history(
        name="Kelly Classic Rug Pull",
        description="Whale with strong belief slowly accumulates using Kelly sizing, retail with noisier beliefs pile in, then whale dumps hard. Includes sells.",
        num_punters=30,
        num_steps=120,
        true_p=0.72,
        punter_noise=0.18,
        min_edge=0.015,
        initial_bankroll=1000.0,
        # market_b chosen via the b-recommendation tool (app.py b-explorer):
        # subsidy=1000, typical_size≈70 (kelly bettors), desired_move≈6-7%, medium activity
        # → b_from_conviction ≈ (70*0.25)/0.065 ≈ 270; capped by subsidy logic in this scale gives ~45-60.
        # We use 45 here for the rug-pull so individual large trades still have dramatic effect.
        market_b=45.0,
        initial_subsidy=1000.0,
        seed=123,
    )
    save_history(h1, "examples/trade_histories/kelly_rug_pull.json")

    # 2. Very long gradual trend with Kelly bettors (now with sells)
    h2 = generate_kelly_history(
        name="Kelly Long Gradual Trend",
        description="Many Kelly bettors with moderately bullish beliefs slowly push the price over a long period. Includes sells for realism.",
        num_punters=35,
        num_steps=120,
        true_p=0.68,
        punter_noise=0.15,
        min_edge=0.012,
        initial_bankroll=1000.0,
        # market_b=50 via recommender (subsidy=1000, typical ~60-80, desired_move~5-6% for gradual trend).
        market_b=50.0,
        initial_subsidy=1000.0,
        seed=456,
    )
    save_history(h2, "examples/trade_histories/kelly_long_trend.json")

    # 3. Noisy market with Kelly sizing (more realistic, with sells)
    h3 = generate_kelly_history(
        name="Kelly High-Activity Noisy Market",
        description="Many users with different beliefs trade frequently using Kelly. More realistic volume pattern with buys and sells.",
        num_punters=40,
        num_steps=120,
        true_p=0.55,
        punter_noise=0.22,
        min_edge=0.01,
        initial_bankroll=1000.0,
        # Lower b=35 (recommender with higher desired per-trade impact + noisier punters).
        market_b=35.0,
        initial_subsidy=1000.0,
        seed=789,
    )
    save_history(h3, "examples/trade_histories/kelly_high_activity.json")

    # ------------------------------------------------------------------
    # 6. Experts vs Punters — the requested long-horizon example
    #    True probability = 0.85. Small number of experts + large population of punters.
    #    Several thousand high-quality trades. Excellent for high-b (up to 1000) exploration.
    # ------------------------------------------------------------------
    print("\nGenerating the big Experts vs Punters example (10k trades, true_p=0.85)...")
    h6 = generate_kelly_history(
        name="Experts vs Punters (p=0.85, long horizon)",
        description=(
            "True probability of the event is 0.85. A small number of experts have accurate beliefs "
            "near the truth. A large crowd of punters have noisy/biased beliefs. The market sees thousands "
            "of trades as information slowly aggregates. Excellent for exploring very high liquidity "
            "(b = 200–1000) over long time scales."
        ),
        num_experts=8,
        expert_noise=0.03,
        num_punters=220,
        punter_noise=0.20,
        punter_mean=0.68,
        num_steps=10000,
        true_p=0.85,
        initial_bankroll=1000.0,
        # High b=280 chosen with the recommendation tool for this massive long-horizon market
        # (220+ punters + experts, 10k steps, high total volume). The tool with large "current_total"
        # volume proxy and tolerance for big subsidy easily recommends 200–500+.
        # This keeps prices relatively stable while still allowing information to aggregate over thousands of trades.
        market_b=280.0,
        initial_subsidy=1000.0,
        min_edge=0.012,            # lower threshold so we actually reach many thousands of trades
        seed=2026,
    )
    save_history(h6, "examples/trade_histories/experts_vs_punters_10000.json")

    print("\nAll Kelly-based histories generated (including the new 10k-trade experts vs punters example).")