"""
lmsr — A numerically stable LMSR prediction market simulator.

This package implements Robin Hanson's Logarithmic Market Scoring Rule (LMSR)
for binary prediction markets, following the design in DESIGN.md.

Main components:
- `BinaryLMSRMarket`: The core numerically stable LMSR engine.
  Supports both **fixed** `b` and **dynamic/adaptive** `b` (see `adaptive.py`).
- `LMSRMarketSimulator`: Multi-market system with users, payouts, scoring,
  portfolio tracking, and accounting verification.
- Scoring utilities (Brier score, Log score, Murphy decomposition).
- Adaptive liquidity strategies (`LinearVolumeB`, `LogVolumeB`, `BoundedB`, etc.).

Example
-------
>>> from src.lmsr import LMSRMarketSimulator, LinearVolumeB, BoundedB
>>> sim = LMSRMarketSimulator()
>>> m = sim.create_market("Will revenue beat target?", b=40.0)
>>> sim.place_trade(m.id, "alice", 12, 0)
>>> sim.resolve_market(m.id, "yes")

# Using adaptive liquidity
>>> adaptive = BoundedB(LinearVolumeB(alpha=0.05), min_b=10, max_b=300)
>>> m2 = sim.create_market("Adaptive Market", b=adaptive)
"""

from .adaptive import (
    AdaptiveBStrategy,
    BoundedB,
    ConstantB,
    FixedB,
    LinearVolumeB,
    LogVolumeB,
    SqrtVolumeB,
    TradeCountB,
)
from .market import BinaryLMSRMarket
from .scoring import (
    ForecasterScores,
    brier_decomposition,
    brier_score,
    log_score,
    mean_brier_score,
    mean_log_score,
)
from .simulator import (
    LMSRMarketSimulator,
    Market,
    Payout,
    Score,
    Trade,
    User,
    UserPortfolio,
)

__all__ = [  # noqa: RUF022 -- logical grouping (core, dataclasses, scoring, adaptive, version) preferred over pure alpha
    "__version__",
    "AdaptiveBStrategy",
    "BinaryLMSRMarket",
    "BoundedB",
    "ConstantB",
    "FixedB",
    "ForecasterScores",
    "LinearVolumeB",
    "LogVolumeB",
    "LMSRMarketSimulator",
    "Market",
    "Payout",
    "Score",
    "SqrtVolumeB",
    "Trade",
    "TradeCountB",
    "User",
    "UserPortfolio",
    "brier_decomposition",
    "brier_score",
    "log_score",
    "mean_brier_score",
    "mean_log_score",
]


# Version (populated from package metadata when installed; falls back for editable/dev)
try:
    from importlib.metadata import PackageNotFoundError, version
except ImportError:  # pragma: no cover (Python >= 3.10 guaranteed)
    def _version_fallback(_dist: str) -> str:
        return "0.1.0"

    version = _version_fallback  # type: ignore[assignment]
    PackageNotFoundError = Exception  # type: ignore[assignment]

try:
    __version__ = version("lmsr-lab")
except PackageNotFoundError:  # pragma: no cover
    __version__ = "0.1.0"
