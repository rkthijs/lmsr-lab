"""
lmsr — A numerically stable LMSR prediction market simulator.

This package implements Robin Hanson's Logarithmic Market Scoring Rule (LMSR)
for binary prediction markets, following the design in DESIGN.md.

Main components:
- BinaryLMSRMarket: The core numerically stable LMSR engine.
- LMSRMarketSimulator: Multi-market system with users, payouts, scoring, and portfolio tracking.
- Scoring utilities (Brier score, Log score, Murphy decomposition).

Example
-------
>>> from src.lmsr import LMSRMarketSimulator
>>> sim = LMSRMarketSimulator()
>>> m = sim.create_market("Will revenue beat target?", b=40.0)
>>> sim.place_trade(m.id, "alice", 12, 0)
>>> sim.resolve_market(m.id, "yes")
"""

from .market import BinaryLMSRMarket
from .simulator import (
    LMSRMarketSimulator,
    Market,
    Trade,
    Payout,
    Score,
    User,
    UserPortfolio,
)
from .scoring import (
    brier_score,
    log_score,
    brier_decomposition,
    mean_brier_score,
    mean_log_score,
    ForecasterScores,
)

__all__ = [
    "BinaryLMSRMarket",
    "LMSRMarketSimulator",
    "Market",
    "Trade",
    "Payout",
    "Score",
    "User",
    "UserPortfolio",
    "brier_score",
    "log_score",
    "brier_decomposition",
    "mean_brier_score",
    "mean_log_score",
    "ForecasterScores",
]