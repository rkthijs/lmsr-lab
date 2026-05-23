#!/usr/bin/env python3
"""
Extend the short illustrative (non-Kelly) histories to >=100 trades.

Rules enforced:
- Each trade record touches only ONE side (yes or no, never both).
- When selling, we often do "SELL ALL" of the user's current holding on that side.
- No simultaneous buy + sell in one record.

This makes all the short "story" examples long enough to be useful in the b-explorer
while preserving their original character.
"""

import json
import random
from pathlib import Path
from typing import Dict, List, Any

from src.lmsr.simulator import LMSRMarketSimulator


SHORT_FILES = [
    "balanced_trades.json",
    "late_buyers.json",
    "long_gradual_trend.json",
    "long_rug_with_fake_volume.json",
    "mixed_high_activity.json",
    "oscillating_trades.json",
    "pump_and_dump_with_fomo.json",
    "rug_pull_classic.json",
    "slow_build_then_surge.json",
    "strong_early_conviction.json",
    "very_long_gradual_trend.json",
    "very_long_pump_and_rug.json",
    "whale_then_correction.json",
]

TARGET_MIN = 100


def extend_history(path: Path, extra_steps: int = 85) -> int:
    """Load a short history, replay it, append more trades, save back."""
    with open(path) as f:
        data = json.load(f)

    original_len = len(data["trades"])
    if original_len >= TARGET_MIN:
        print(f"{path.name:30} already has {original_len} trades — skipping")
        return original_len

    sim = LMSRMarketSimulator()
    market = sim.create_market(
        title=data.get("name", path.stem),
        b=data.get("market_params", {}).get("b", 25.0),
        fee_rate=data.get("market_params", {}).get("fee_rate", 0.02),
        initial_subsidy=data.get("market_params", {}).get("initial_subsidy", 0.0),
    )

    # Replay original trades to restore final state + positions
    for t in data["trades"]:
        sim.place_trade(market.id, t["user"], t.get("yes", 0), t.get("no", 0))

    trades = data["trades"]

    # Get the set of users that appeared
    users = sorted({t["user"] for t in trades})

    for _ in range(extra_steps):
        uid = random.choice(users)
        pos = sim.get_user_position(market.id, uid)

        # 35% chance to sell all of something they hold
        if random.random() < 0.35:
            if pos[0] > 0 and random.random() < 0.5:
                shares = int(pos[0])          # SELL ALL Yes
                trades.append({"user": uid, "yes": -shares, "no": 0})
                sim.place_trade(market.id, uid, -shares, 0)
                continue
            if pos[1] > 0:
                shares = int(pos[1])          # SELL ALL No
                trades.append({"user": uid, "yes": 0, "no": -shares})
                sim.place_trade(market.id, uid, 0, -shares)
                continue

        # Otherwise do a small buy on one side (preserve original "flavor")
        side = random.choice(["yes", "no"])
        size = random.randint(3, 12)
        if side == "yes":
            trades.append({"user": uid, "yes": size, "no": 0})
            sim.place_trade(market.id, uid, size, 0)
        else:
            trades.append({"user": uid, "yes": 0, "no": size})
            sim.place_trade(market.id, uid, 0, size)

    # Update metadata
    data["trades"] = trades
    data["description"] = data.get("description", "") + " (extended to >100 trades with sells)"

    with open(path, "w") as f:
        json.dump(data, f, indent=2)

    new_len = len(trades)
    print(f"{path.name:30}  {original_len:3d} → {new_len:3d} trades")
    return new_len


if __name__ == "__main__":
    print("Extending short illustrative histories to >=100 trades (one side only, with SELL ALL)...\n")
    for fname in SHORT_FILES:
        p = Path("examples/trade_histories") / fname
        if p.exists():
            extend_history(p)
    print("\nDone. All short histories now have enough trades for good b-exploration.")