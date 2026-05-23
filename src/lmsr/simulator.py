"""
In-memory simulation of the larger prediction market architecture
described in DESIGN.md.

This module prototypes the next layer above the pure LMSR math engine
(`BinaryLMSRMarket`). It demonstrates the key architectural patterns from
the design conversation:

- Immutable trade records (append-only log)
- Positions as *derived* state (can be recomputed by replaying trades)
- Clear separation between the mathematical engine and the application model
- Preparation for future database-backed implementation (the transaction
  pattern, scoring integration, etc.)

This is intentionally lightweight and suitable for experiments, backtesting,
and early UI work.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

import numpy as np

from .market import BinaryLMSRMarket
from .scoring import brier_score  # available for future wiring


@dataclass(frozen=True)
class Trade:
    """
    Immutable record of a single trade.

    This is the atomic unit of history. In a real system this would map
    directly to a row in the `trades` table (see DESIGN.md schema).
    """
    market_id: str
    timestamp: datetime
    user_id: str
    shares_yes: float
    shares_no: float
    raw_cost: float
    fee: float
    effective_cost: float
    price_after_yes: float
    price_after_no: float
    market_q_after: tuple[float, float]


@dataclass
class Market:
    """
    Represents one prediction market in the system.

    Each market has its own LMSR engine, its own trade history,
    and its own lifecycle (open → resolved).

    This closely follows the `markets` table design from DESIGN.md.
    """
    id: str
    title: str
    description: str = ""
    resolution_criteria: str = ""
    b: float = 20.0
    fee_rate: float = 0.02
    status: str = "open"          # "open", "closed", "resolved"
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    close_at: datetime | None = None
    resolved_at: datetime | None = None
    resolution_outcome: str | None = None

    # Internal state
    engine: BinaryLMSRMarket = field(init=False, repr=False)
    trades: list[Trade] = field(default_factory=list, repr=False)

    def __post_init__(self):
        self.engine = BinaryLMSRMarket(b=self.b, fee_rate=self.fee_rate)


class LMSRMarketSimulator:
    """
    Multi-market simulator for LMSR prediction markets.

    This is the main application-layer prototype matching the architecture
    in DESIGN.md. It supports:

    - Multiple independent markets
    - Per-market immutable trade logs
    - Positions derived from trade history (per market)
    - Clean separation between market metadata and the mathematical engine

    Usage example:
        sim = LMSRMarketSimulator()
        m1 = sim.create_market("Will AI beat humans by 2030?", b=30)
        sim.place_trade(m1.id, "alice", 10, 0)
    """

    def __init__(self):
        self.markets: dict[str, Market] = {}
        self._next_market_id = 1
        # Per-market position caches
        self._positions_cache: dict[str, dict[str, np.ndarray]] = {}

    # ------------------------------------------------------------------
    # Market Management
    # ------------------------------------------------------------------

    def create_market(
        self,
        title: str,
        description: str = "",
        resolution_criteria: str = "",
        b: float = 20.0,
        fee_rate: float = 0.02,
        close_at: datetime | None = None,
    ) -> Market:
        """
        Create a new prediction market.

        Returns the created Market object (which contains its own engine).
        """
        market_id = f"m{self._next_market_id}"
        self._next_market_id += 1

        market = Market(
            id=market_id,
            title=title,
            description=description,
            resolution_criteria=resolution_criteria,
            b=b,
            fee_rate=fee_rate,
            close_at=close_at,
        )
        self.markets[market_id] = market
        self._positions_cache[market_id] = {}
        return market

    def get_market(self, market_id: str) -> Market:
        """Retrieve a market by id. Raises KeyError if not found."""
        if market_id not in self.markets:
            raise KeyError(f"Market '{market_id}' does not exist")
        return self.markets[market_id]

    def list_markets(self, status: str | None = None) -> list[Market]:
        """List all markets, optionally filtered by status."""
        if status is None:
            return list(self.markets.values())
        return [m for m in self.markets.values() if m.status == status]

    # ------------------------------------------------------------------
    # Trading
    # ------------------------------------------------------------------

    def place_trade(
        self,
        market_id: str,
        user_id: str,
        shares_yes: float = 0.0,
        shares_no: float = 0.0,
    ) -> dict[str, Any]:
        """
        Place a trade in a specific market.

        Records an immutable Trade and updates the market's engine.
        """
        market = self.get_market(market_id)
        engine = market.engine

        effective_cost, raw_cost = engine.quote(shares_yes, shares_no)

        result = engine.trade(user_id, shares_yes, shares_no)

        if "error" in result:
            return result

        p_yes, p_no = result["new_prices"]

        trade = Trade(
            market_id=market_id,
            timestamp=datetime.now(timezone.utc),
            user_id=user_id,
            shares_yes=shares_yes,
            shares_no=shares_no,
            raw_cost=raw_cost,
            fee=result["fee"],
            effective_cost=effective_cost,
            price_after_yes=p_yes,
            price_after_no=p_no,
            market_q_after=tuple(engine.q),
        )
        market.trades.append(trade)

        # Invalidate cache for this market
        if market_id in self._positions_cache:
            self._positions_cache[market_id] = {}

        return result

    # ------------------------------------------------------------------
    # Positions (derived from trade log per market)
    # ------------------------------------------------------------------

    def get_user_position(self, market_id: str, user_id: str) -> np.ndarray:
        """
        Get a user's position in a specific market.

        Positions are always derived from that market's trade history.
        """
        market = self.get_market(market_id)

        cache = self._positions_cache.get(market_id, {})
        if not cache:
            cache = self._recompute_positions(market_id)
            self._positions_cache[market_id] = cache

        return cache.get(user_id, np.array([0.0, 0.0])).copy()

    def _recompute_positions(self, market_id: str) -> dict[str, np.ndarray]:
        """Recompute all user positions for a market from its trade log."""
        market = self.get_market(market_id)
        positions: dict[str, np.ndarray] = {}

        for t in market.trades:
            if t.user_id not in positions:
                positions[t.user_id] = np.array([0.0, 0.0])
            positions[t.user_id] += np.array([t.shares_yes, t.shares_no])

        return positions

    # ------------------------------------------------------------------
    # Replay & Auditing
    # ------------------------------------------------------------------

    def replay_market(self, market_id: str) -> BinaryLMSRMarket:
        """
        Replay all trades for a market into a fresh engine.

        Useful for verification and proving that state is fully determined
        by the trade log (as emphasized in DESIGN.md).
        """
        market = self.get_market(market_id)
        fresh = BinaryLMSRMarket(b=market.b, fee_rate=market.fee_rate)

        for t in market.trades:
            fresh.trade(t.user_id, t.shares_yes, t.shares_no)

        return fresh

    # ------------------------------------------------------------------
    # Resolution
    # ------------------------------------------------------------------

    def resolve_market(self, market_id: str, outcome: str) -> dict:
        """
        Resolve a market to 'yes' or 'no'.

        Updates the market status and records the outcome.
        In a more complete version this would also compute scores.
        """
        market = self.get_market(market_id)
        if market.status != "open":
            raise ValueError(f"Market {market_id} is already {market.status}")

        result = market.engine.resolve(outcome)

        market.status = "resolved"
        market.resolution_outcome = outcome.lower()
        market.resolved_at = datetime.now(timezone.utc)

        return result

    # ------------------------------------------------------------------
    # Utilities
    # ------------------------------------------------------------------

    def reset_market(self, market_id: str) -> None:
        """Reset a single market (engine + trades)."""
        market = self.get_market(market_id)
        market.engine = BinaryLMSRMarket(b=market.b, fee_rate=market.fee_rate)
        market.trades.clear()
        market.status = "open"
        market.resolution_outcome = None
        market.resolved_at = None
        self._positions_cache[market_id] = {}

    def reset(self) -> None:
        """Reset the entire simulator (all markets)."""
        self.markets.clear()
        self._positions_cache.clear()
        self._next_market_id = 1

    def summary(self, market_id: str | None = None) -> dict[str, Any]:
        """Return summary information, optionally for a specific market."""
        if market_id:
            market = self.get_market(market_id)
            return {
                "market_id": market.id,
                "title": market.title,
                "status": market.status,
                "current_prices": market.engine.price(),
                "total_trades": len(market.trades),
                "total_revenue": market.engine.total_revenue,
            }
        else:
            return {
                "num_markets": len(self.markets),
                "markets": [
                    {"id": m.id, "title": m.title, "status": m.status}
                    for m in self.markets.values()
                ],
            }
