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

import pickle
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np

from .market import BinaryLMSRMarket, BType
from .scoring import brier_score, log_score


@dataclass(frozen=True)
class Trade:
    """
    Immutable record of a single trade.

    This is the atomic unit of history. In a real system this would map
    directly to a row in the `trades` table (see DESIGN.md schema).
    """
    id: str                     # stable identifier for linking scores, etc.
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


@dataclass(frozen=True)
class Payout:
    """
    Immutable record of a payout made on market resolution.

    One record per user per resolved market (as described in DESIGN.md).
    """
    market_id: str
    user_id: str
    amount: float
    outcome: str          # "yes" or "no"
    timestamp: datetime


@dataclass(frozen=True)
class Score:
    """
    Stored calibration score for a specific forecast (trade) after resolution.

    Mirrors the `scores` table design from DESIGN.md.
    """
    market_id: str
    user_id: str
    trade_id: str
    forecast_prob: float      # p_yes at the time the trade was made
    outcome: float            # 1.0 for Yes, 0.0 for No
    brier_score: float
    log_score: float
    timestamp: datetime


@dataclass
class User:
    """
    Represents a user in the prediction market system.

    This is the improved user model (as discussed from DESIGN.md).
    It holds identity + balance, and enables richer portfolio views.
    """
    id: str
    balance: float = 1000.0
    display_name: str | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class UserPortfolio:
    """
    Aggregated view of everything a user has across all markets.

    This is the main deliverable of the "better user model".
    """
    user_id: str
    balance: float
    positions: dict[str, dict[str, float]]   # market_id -> {"yes": x, "no": y, "total": x+y}
    realized_pnl: float
    total_payouts_received: float
    open_markets_count: int
    resolved_markets_count: int


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
    b: BType = 20.0
    fee_rate: float = 0.02
    initial_subsidy: float = 0.0  # Market maker's initial capital/subsidy for this market
    status: str = "open"          # "open", "closed", "resolved"
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    close_at: datetime | None = None
    resolved_at: datetime | None = None
    resolution_outcome: str | None = None

    # Internal state
    engine: BinaryLMSRMarket = field(init=False, repr=False)
    trades: list[Trade] = field(default_factory=list, repr=False)
    payouts: list[Payout] = field(default_factory=list, repr=False)
    scores: list[Score] = field(default_factory=list, repr=False)

    def __post_init__(self):
        self.engine = BinaryLMSRMarket(b=self.b, fee_rate=self.fee_rate)

    @property
    def current_b(self) -> float:
        """Current effective liquidity (evaluates the adaptive strategy if present)."""
        return self.engine.b

    @property
    def is_adaptive_b(self) -> bool:
        """Whether this market uses a dynamic/adaptive b strategy."""
        return self.engine.is_adaptive_b


class LMSRMarketSimulator:
    """
    Multi-market simulator for LMSR prediction markets.

    This is the main application-layer prototype matching the architecture
    in DESIGN.md. It supports:

    - Multiple independent markets
    - Per-market immutable trade logs + payout records
    - Positions derived from trade history (per market)
    - Improved User model with balances and cross-market Portfolio views
    - Global leaderboard based on calibration (Brier/Log) and realized P/L
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
        # Improved user model (replaces flat balance dict)
        self.users: dict[str, User] = {}

    # ------------------------------------------------------------------
    # Market Management
    # ------------------------------------------------------------------

    def create_market(
        self,
        title: str,
        description: str = "",
        resolution_criteria: str = "",
        b: BType = 20.0,
        fee_rate: float = 0.02,
        initial_subsidy: float = 0.0,
        close_at: datetime | None = None,
    ) -> Market:
        """
        Create a new prediction market.

        The `b` parameter can be either a fixed float (classic LMSR) or a
        callable that returns dynamic liquidity based on current shares
        (adaptive / liquidity-sensitive LMSR).

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
            initial_subsidy=initial_subsidy,
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

    def close_market(self, market_id: str) -> dict[str, Any]:
        """
        Close a market to new trading (but not yet resolved).

        Once closed, no new trades are allowed. This is a common step before
        official resolution in real prediction market systems.
        """
        market = self.get_market(market_id)

        if market.status != "open":
            return {
                "error": f"Cannot close a market that is {market.status}",
                "market_status": market.status,
            }

        market.status = "closed"
        return {"success": True, "market_id": market_id, "status": "closed"}

    # ------------------------------------------------------------------
    # User Management (improved model per DESIGN.md)
    # ------------------------------------------------------------------

    def get_or_create_user(self, user_id: str, display_name: str | None = None) -> User:
        """Get existing user or create a new one with default balance."""
        if user_id not in self.users:
            self.users[user_id] = User(
                id=user_id,
                display_name=display_name or user_id,
            )
        return self.users[user_id]

    def get_user(self, user_id: str) -> User:
        """Get a user (creates with default balance if missing)."""
        return self.get_or_create_user(user_id)

    def get_balance(self, user_id: str) -> float:
        """Return current balance for a user."""
        return self.get_user(user_id).balance

    def _adjust_balance(self, user_id: str, amount: float) -> None:
        """Internal: credit or debit a user's balance."""
        user = self.get_user(user_id)
        user.balance += amount

    def get_payouts(self, market_id: str) -> list[Payout]:
        """Return all payout records for a given market."""
        market = self.get_market(market_id)
        return list(market.payouts)

    def get_user_payouts(self, user_id: str) -> list[Payout]:
        """Return all payouts ever made to a specific user across markets."""
        payouts = []
        for market in self.markets.values():
            for p in market.payouts:
                if p.user_id == user_id:
                    payouts.append(p)
        return payouts

    def get_scores(self, market_id: str) -> list[Score]:
        """Return all stored calibration scores for a given market."""
        market = self.get_market(market_id)
        return list(market.scores)

    def get_user_scores(self, user_id: str) -> list[Score]:
        """Return all calibration scores for a specific user across all markets."""
        scores = []
        for market in self.markets.values():
            for s in market.scores:
                if s.user_id == user_id:
                    scores.append(s)
        return scores

    # ------------------------------------------------------------------
    # Global Leaderboard (based on scores + realized P/L)
    # ------------------------------------------------------------------

    def get_leaderboard(
        self,
        metric: str = "brier",
        min_resolved_trades: int = 1,
    ) -> list[dict]:
        """
        Compute a global leaderboard across all resolved markets.

        Supported metrics:
            - "brier"   : lower is better (best calibration)
            - "log"     : higher is better (better log score)
            - "pnl"     : higher is better (realized profit/loss from resolutions)

        Only users with at least `min_resolved_trades` resolved trades are included.
        """
        # Build per-user aggregates for all users who have scores
        user_data: dict[str, dict] = {}

        for market in self.markets.values():
            if market.status != "resolved":
                continue

            for score in market.scores:
                uid = score.user_id
                if uid not in user_data:
                    user_data[uid] = {
                        "brier_scores": [],
                        "log_scores": [],
                        "resolved_trades": 0,
                        "pnl": 0.0,
                    }
                user_data[uid]["brier_scores"].append(score.brier_score)
                user_data[uid]["log_scores"].append(score.log_score)
                user_data[uid]["resolved_trades"] += 1

            for payout in market.payouts:
                uid = payout.user_id
                if uid not in user_data:
                    user_data[uid] = {
                        "brier_scores": [],
                        "log_scores": [],
                        "resolved_trades": 0,
                        "pnl": 0.0,
                    }
                user_data[uid]["pnl"] += payout.amount

        # Filter and build leaderboard entries
        leaderboard = []
        for uid, data in user_data.items():
            if data["resolved_trades"] < min_resolved_trades:
                continue

            avg_brier = sum(data["brier_scores"]) / len(data["brier_scores"])
            avg_log = sum(data["log_scores"]) / len(data["log_scores"])

            entry = {
                "user_id": uid,
                "resolved_trades": data["resolved_trades"],
                "avg_brier": round(avg_brier, 4),
                "avg_log_score": round(avg_log, 4),
                "total_pnl": round(data["pnl"], 2),
            }
            leaderboard.append(entry)

        # Sort according to metric
        if metric == "brier":
            leaderboard.sort(key=lambda x: (x["avg_brier"], -x["total_pnl"]))
        elif metric == "log":
            leaderboard.sort(key=lambda x: (-x["avg_log_score"], -x["total_pnl"]))
        elif metric == "pnl":
            leaderboard.sort(key=lambda x: (-x["total_pnl"], x["avg_brier"]))
        else:
            raise ValueError(f"Unsupported leaderboard metric: {metric}")

        return leaderboard

    def _compute_and_store_scores(self, market: Market, winning: str, timestamp: datetime) -> None:
        """Private helper extracted from resolve_market for clarity."""
        outcome_value = 1.0 if winning == "yes" else 0.0

        for trade in market.trades:
            forecast = trade.price_after_yes
            brier = float(brier_score([forecast], [outcome_value])[0])
            log_s = float(log_score([forecast], [outcome_value])[0])

            score = Score(
                market_id=market.id,
                user_id=trade.user_id,
                trade_id=trade.id,
                forecast_prob=forecast,
                outcome=outcome_value,
                brier_score=brier,
                log_score=log_s,
                timestamp=timestamp,
            )
            market.scores.append(score)

    def _get_user_aggregates(self, user_id: str) -> dict:
        """
        Internal helper that builds aggregated data for a user across all markets.
        Used by both get_user_portfolio() and get_leaderboard() to avoid duplication.
        """
        positions = {}
        realized_pnl = 0.0
        total_payouts = 0.0
        resolved_trades = 0
        open_count = 0
        resolved_count = 0

        for market in self.markets.values():
            pos = self.get_user_position(market.id, user_id)
            positions[market.id] = {
                "yes": float(pos[0]),
                "no": float(pos[1]),
                "total": float(pos[0] + pos[1]),
            }

            if market.status == "resolved":
                resolved_count += 1
                for p in market.payouts:
                    if p.user_id == user_id:
                        total_payouts += p.amount
                        realized_pnl += p.amount
                # Count resolved trades for this user
                resolved_trades += sum(1 for s in market.scores if s.user_id == user_id)
            else:
                open_count += 1

        return {
            "positions": positions,
            "realized_pnl": realized_pnl,
            "total_payouts": total_payouts,
            "resolved_trades": resolved_trades,
            "open_count": open_count,
            "resolved_count": resolved_count,
        }

    def get_user_portfolio(self, user_id: str) -> UserPortfolio:
        """
        Return a rich aggregated view of everything the user has.
        """
        user = self.get_user(user_id)
        agg = self._get_user_aggregates(user_id)

        return UserPortfolio(
            user_id=user_id,
            balance=user.balance,
            positions=agg["positions"],
            realized_pnl=agg["realized_pnl"],
            total_payouts_received=agg["total_payouts"],
            open_markets_count=agg["open_count"],
            resolved_markets_count=agg["resolved_count"],
        )

    # ------------------------------------------------------------------
    # Accounting Identity (critical invariant from DESIGN.md)
    # ------------------------------------------------------------------

    def check_accounting_identity(self, market_id: str) -> dict:
        """
        Perform accounting and consistency checks after resolution.

        Implements the critical invariant from DESIGN.md (the market_accounting
        view):

            remainder = subsidy + total_revenue_from_trades - total_payouts

        Verifies:
        - Recorded payouts exactly match the winning shares outstanding in the
          engine (q[winning]). This is the primary correctness check: it proves
          the payout records and balance credits are faithful to what was sold.
        - For backward compatibility, also checks that two ways of computing
          the market maker P/L agree (they will when the above holds).

        The `remainder` (and `initial_subsidy`) are always returned so callers
        can audit the house P/L on the market. Per LMSR math, remainder is
        *not* required to be zero — it is the realized profit/loss for the
        market operator after fees and resolution. It will be small only in
        the limit of well-calibrated traders + no subsidy.

        See DESIGN.md "The Critical Invariant: Accounting".
        """
        market = self.get_market(market_id)

        if market.status != "resolved":
            return {"market_id": market_id, "error": "Market not resolved yet"}

        winning = market.resolution_outcome
        idx = 0 if winning == "yes" else 1

        winning_shares_engine = float(market.engine.q[idx])
        total_payouts = float(sum(p.amount for p in market.payouts))

        engine_pl = float(market.engine.total_revenue - winning_shares_engine)
        calculated_pl = float(market.engine.total_revenue - total_payouts)

        subsidy = float(market.initial_subsidy)
        remainder = float(subsidy + market.engine.total_revenue - total_payouts)

        tolerance = 1e-6
        payout_match = bool(abs(total_payouts - winning_shares_engine) <= tolerance)
        pl_match = bool(abs(engine_pl - calculated_pl) <= tolerance)

        return {
            "market_id": market_id,
            "winning_outcome": winning,
            "winning_shares_engine": winning_shares_engine,
            "total_payouts_recorded": total_payouts,
            "payouts_match_engine": payout_match,
            "engine_pl": engine_pl,
            "calculated_pl_from_payouts": calculated_pl,
            "pl_match": pl_match,
            "initial_subsidy": subsidy,
            "remainder": remainder,
            "is_valid": bool(payout_match and pl_match),
            "tolerance": float(tolerance),
        }

    # ------------------------------------------------------------------
    # Persistence (save / load simulator state)
    # ------------------------------------------------------------------

    def save(self, filepath: str | Path) -> None:
        """
        Persist the entire simulator state to disk using pickle.

        Saves markets (with engines, trades, payouts), user balances,
        and internal counters.

        Caches are cleared before saving (they will be lazily rebuilt).
        """
        path = Path(filepath)
        path.parent.mkdir(parents=True, exist_ok=True)

        # Clear derived caches before saving
        self._positions_cache.clear()

        with open(path, "wb") as f:
            pickle.dump(self, f)

    @classmethod
    def load(cls, filepath: str | Path) -> LMSRMarketSimulator:
        """
        Load a previously saved simulator from disk.
        """
        path = Path(filepath)
        if not path.exists():
            raise FileNotFoundError(f"No simulator state found at {path}")

        with open(path, "rb") as f:
            sim: LMSRMarketSimulator = pickle.load(f)

        # Make sure caches exist and are clean after loading
        if not hasattr(sim, "_positions_cache"):
            sim._positions_cache = {}
        sim._positions_cache.clear()

        return sim

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

        Handles balance checks and updates (as specified in DESIGN.md).
        """
        market = self.get_market(market_id)

        if market.status != "open":
            return {
                "error": f"Cannot trade on a {market.status} market",
                "market_status": market.status,
            }

        # Prevent no-op trades
        if shares_yes == 0 and shares_no == 0:
            return {
                "error": "Trade must have a non-zero number of shares on at least one side (Yes or No).",
            }

        engine = market.engine

        effective_cost, raw_cost = engine.quote(shares_yes, shares_no)

        # Balance check (only for positive cost trades)
        if effective_cost > 0:
            balance = self.get_balance(user_id)
            if balance < effective_cost:
                return {
                    "error": "Insufficient balance",
                    "current_balance": balance,
                    "required": effective_cost,
                }

        result = engine.trade(user_id, shares_yes, shares_no)

        if "error" in result:
            return result

        # Deduct / credit balance
        self._adjust_balance(user_id, -effective_cost)

        p_yes, p_no = result["new_prices"]

        # Generate a stable trade id
        trade_id = f"{market_id}-t{len(market.trades)}"

        trade = Trade(
            id=trade_id,
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
            market_q_after=tuple(float(x) for x in engine.q),
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

        Delegates the main responsibilities to focused private methods:
        - Creating payouts + crediting balances
        - Computing and storing calibration scores
        - Running accounting identity checks

        This keeps resolve_market as a clear orchestrator.
        """
        market = self.get_market(market_id)
        if market.status != "open":
            raise ValueError(f"Market {market_id} is already {market.status}")

        result = market.engine.resolve(outcome)
        winning = outcome.lower()
        idx = 0 if winning == "yes" else 1
        timestamp = datetime.now(timezone.utc)

        # Delegate the heavy lifting
        self._create_payouts_and_credit_balances(market, winning, idx, timestamp)
        self._compute_and_store_scores(market, winning, timestamp)

        self._finalize_resolution(market, winning, timestamp, result)

        return result

    def _create_payouts_and_credit_balances(
        self, market: Market, winning: str, idx: int, timestamp: datetime
    ) -> None:
        """Create Payout records and credit user balances for the winning side."""
        users = set(t.user_id for t in market.trades)

        for user in users:
            pos = self.get_user_position(market.id, user)
            amount = float(pos[idx])

            if amount > 0:
                payout = Payout(
                    market_id=market.id,
                    user_id=user,
                    amount=amount,
                    outcome=winning,
                    timestamp=timestamp,
                )
                market.payouts.append(payout)
                self._adjust_balance(user, amount)

    def _finalize_resolution(
        self, market: Market, winning: str, timestamp: datetime, result: dict
    ) -> None:
        """Set final state on the market and attach accounting information to the result."""
        market.status = "resolved"
        market.resolution_outcome = winning
        market.resolved_at = timestamp

        accounting = self.check_accounting_identity(market.id)
        result["accounting_identity"] = accounting

        if not accounting["is_valid"]:
            result["accounting_warning"] = (
                f"Accounting identity violated! payout mismatch detected. "
                f"remainder={accounting['remainder']:.8f}"
            )

    # ------------------------------------------------------------------
    # Utilities
    # ------------------------------------------------------------------

    def reset_market(self, market_id: str) -> None:
        """Reset a single market (engine + trades + payouts + scores)."""
        market = self.get_market(market_id)
        market.engine = BinaryLMSRMarket(b=market.b, fee_rate=market.fee_rate)
        market.trades.clear()
        market.payouts.clear()
        market.scores.clear()
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
                "total_fees_earned": market.engine.total_fees_earned,
            }
        else:
            return {
                "num_markets": len(self.markets),
                "markets": [
                    {"id": m.id, "title": m.title, "status": m.status}
                    for m in self.markets.values()
                ],
            }
