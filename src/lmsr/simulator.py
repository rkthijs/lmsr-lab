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

import json
import pickle
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np

from .market import BinaryLMSRMarket, BType
from .scoring import brier_score, log_score

# For strategy serialization in JSON
try:
    from .adaptive import BoundedB, LinearVolumeB
except Exception:  # pragma: no cover
    BoundedB = None  # type: ignore
    LinearVolumeB = None  # type: ignore

# Optional DB persistence (stdlib sqlite3, no new runtime dependency)
try:
    from .db import SQLiteStore, reconstruct_b
except Exception:  # pragma: no cover
    SQLiteStore = None  # type: ignore
    reconstruct_b = None  # type: ignore


def _serialize_strategy(b: Any) -> dict[str, Any]:
    """Serialize b (float or adaptive strategy) to a dict for JSON/DB."""
    if isinstance(b, (int, float)):
        return {"type": "fixed", "value": float(b)}
    if BoundedB is not None and isinstance(b, BoundedB):
        inner = b.strategy
        if LinearVolumeB is not None and isinstance(inner, LinearVolumeB):
            return {
                "type": "bounded_linear",
                "alpha": inner.alpha,
                "min_b": b.min_b,
                "max_b": b.max_b,
            }
        # fall back
        return {"type": "bounded_linear", "alpha": 0.05, "min_b": getattr(b, "min_b", 5.0), "max_b": getattr(b, "max_b", 300.0)}
    if LinearVolumeB is not None and isinstance(b, LinearVolumeB):
        return {"type": "linear", "alpha": b.alpha, "min_b": b.min_b}
    # default
    return {"type": "fixed", "value": 20.0}


@dataclass(frozen=True)
class Trade:
    """
    Immutable record of a single trade.

    This is the atomic unit of history. In a real system this would map
    directly to a row in the `trades` table (see DESIGN.md schema).
    Shares are always whole numbers (no fractional shares allowed).
    """
    id: str                     # stable identifier for linking scores, etc.
    market_id: str
    timestamp: datetime
    user_id: str
    shares_yes: int
    shares_no: int
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
    Stored calibration score for a specific forecast (trade).

    Per DESIGN.md:
    - A *stub* version (only forecast_prob + trade_id) is inserted at trade time.
    - It is filled with outcome + brier_score + log_score at resolution time,
      using the price_after_yes recorded on the corresponding Trade as the
      revealed belief ("forecast_prob").
    - This is the incentive-compatible choice (scored on the belief at the
      moment the trader acted).

    Mirrors the `scores` table design from DESIGN.md (composite PK on
    market_id + trade_id; outcome nullable until resolution).
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
    Includes the three values users care about most:
      - cash balance (the 'balance' field)
      - current mark-to-market value of open positions (position_value)
      - total account value = cash + position_value (total_value)
    """
    user_id: str
    balance: float                  # cash balance
    positions: dict[str, dict]      # market_id -> {"yes", "no", "total", "value"?, "p_yes"?, "p_no"?}
    realized_pnl: float
    total_payouts_received: float
    open_markets_count: int
    resolved_markets_count: int
    position_value: float = 0.0     # MTM value of current open share holdings at latest prices
    total_value: float = 0.0        # balance + position_value (total account equity)


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
    - Optional SQLite persistence (db_path) with:
        * Load by replaying immutable trade log (positions always derived)
        * Score *stubs* inserted at trade time (DESIGN.md), filled on resolve
        * Transactions around trade+balance+stub and full resolution
        * Accounting identity validation on resolve + on load for resolved markets

    Usage example:
        sim = LMSRMarketSimulator()
        m1 = sim.create_market("Will AI beat humans by 2030?", b=30)
        sim.place_trade(m1.id, "alice", 10, 0)
    """

    def __init__(self, db_path: str | Path | None = None):
        self.markets: dict[str, Market] = {}
        self._next_market_id = 1
        # Per-market position caches
        self._positions_cache: dict[str, dict[str, np.ndarray]] = {}
        # Improved user model (replaces flat balance dict)
        self.users: dict[str, User] = {}

        # Optional durable storage (replaces pickle for the main app/demo use case)
        self.db_path: str | None = str(db_path) if db_path else None
        self._db: Any = None
        if self.db_path and SQLiteStore is not None:
            self._db = SQLiteStore(self.db_path)
            self._load_from_db()

    def _load_from_db(self) -> None:
        """Hydrate the in-memory simulator from the DB.

        Per DESIGN.md: state is loaded by *replaying the immutable trade log*.
        Positions are always derived (never stored). User balances are the
        current snapshot from the users table. Score rows may be stubs
        (inserted at trade time, with only forecast_prob) or fully populated
        (after resolution).
        """
        if not self._db:
            return

        # Users (current balances)
        for u in self._db.list_users():
            self.users[u["id"]] = User(
                id=u["id"],
                balance=float(u["balance"]),
                display_name=u.get("display_name"),
            )

        # Markets + replay trades into their engines (positions derived)
        max_id = 0
        for mdata in self._db.list_markets():
            mid = mdata["id"]
            # reconstruct b (fixed or adaptive)
            b = reconstruct_b(mdata) if reconstruct_b else float(mdata["b"])

            market = Market(
                id=mid,
                title=mdata["title"],
                description=mdata.get("description", ""),
                resolution_criteria=mdata.get("resolution_criteria", ""),
                b=b,
                fee_rate=float(mdata.get("fee_rate", 0.02)),
                initial_subsidy=float(mdata.get("initial_subsidy", 0)),
                status=mdata.get("status", "open"),
            )
            # override timestamps if present
            if mdata.get("created_at"):
                try:
                    market.created_at = datetime.fromisoformat(mdata["created_at"])
                except Exception:
                    pass
            if mdata.get("close_at"):
                try:
                    market.close_at = datetime.fromisoformat(mdata["close_at"])
                except Exception:
                    pass
            if mdata.get("resolved_at"):
                try:
                    market.resolved_at = datetime.fromisoformat(mdata["resolved_at"])
                except Exception:
                    pass
            market.resolution_outcome = mdata.get("resolution_outcome")

            self.markets[mid] = market
            self._positions_cache[mid] = {}

            # replay trades (low-level engine.trade only - no balance side effects here)
            for tdata in self._db.get_trades(mid):
                trade = Trade(
                    id=tdata["id"],
                    market_id=mid,
                    timestamp=datetime.fromisoformat(tdata["created_at"]) if tdata.get("created_at") else datetime.now(timezone.utc),
                    user_id=tdata["user_id"],
                    shares_yes=int(tdata["shares_yes"]),
                    shares_no=int(tdata["shares_no"]),
                    raw_cost=float(tdata["raw_cost"]),
                    fee=float(tdata["fee"]),
                    effective_cost=float(tdata["effective_cost"]),
                    price_after_yes=float(tdata["price_after_yes"]),
                    price_after_no=float(tdata["price_after_no"]),
                    market_q_after=(float(tdata["q_after_yes"]), float(tdata["q_after_no"])),
                )
                market.trades.append(trade)
                # replay math into the engine (updates q + internal user_positions guard)
                market.engine.trade(trade.user_id, trade.shares_yes, trade.shares_no)

            # try to advance the id counter
            try:
                num = int(mid.lstrip("m"))
                if num > max_id:
                    max_id = num
            except Exception:
                pass

        if max_id >= self._next_market_id:
            self._next_market_id = max_id + 1

        # load payouts and scores into the market objects
        # (scores may be trade-time stubs or resolution-filled versions)
        for mid, market in self.markets.items():
            for pdata in self._db.get_payouts(market_id=mid):
                market.payouts.append(
                    Payout(
                        market_id=mid,
                        user_id=pdata["user_id"],
                        amount=float(pdata["amount"]),
                        outcome=pdata["outcome"],
                        timestamp=datetime.fromisoformat(pdata["created_at"]) if pdata.get("created_at") else datetime.now(timezone.utc),
                    )
                )
            for sdata in self._db.get_scores(market_id=mid):
                market.scores.append(
                    Score(
                        market_id=mid,
                        user_id=sdata["user_id"],
                        trade_id=sdata["trade_id"],
                        forecast_prob=float(sdata["forecast_prob"]),
                        outcome=float(sdata.get("outcome", 0)) if sdata.get("outcome") is not None else None,
                        brier_score=float(sdata.get("brier_score", 0)) if sdata.get("brier_score") is not None else None,
                        log_score=float(sdata.get("log_score", 0)) if sdata.get("log_score") is not None else None,
                        timestamp=datetime.fromisoformat(sdata["created_at"]) if sdata.get("created_at") else datetime.now(timezone.utc),
                    )
                )

        # Strengthen conformance to DESIGN.md: for any resolved markets loaded
        # from DB, re-validate the critical accounting identity (total_payouts
        # == winning q, remainder, etc.). We attach a private warning attr for
        # diagnostics rather than failing the load (this is a research tool).
        for mid, market in list(self.markets.items()):
            if getattr(market, "status", None) == "resolved":
                try:
                    acc = self.check_accounting_identity(mid)
                    if not acc.get("is_valid"):
                        market._accounting_warning = acc
                except Exception:
                    pass

    def db_summary(self) -> dict[str, Any]:
        """Return summary info from the DB (if configured) for inspection."""
        if self._db:
            return self._db.get_summary()
        return {"error": "no db configured (use db_path=...)"}

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

        if self._db:
            # persist metadata (strategy info is handled inside the store)
            self._db.save_market(
                id=market_id,
                title=title,
                description=description,
                resolution_criteria=resolution_criteria,
                b=b,
                fee_rate=fee_rate,
                initial_subsidy=initial_subsidy,
                status="open",
                created_at=market.created_at.isoformat(),
            )
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
        """Private helper extracted from resolve_market for clarity.

        Fills (or replaces) the stub Score rows that were inserted at trade time
        (see place_trade + DESIGN.md §5 Trade Flow step 7).
        The forecast_prob was captured at trade time from price_after_yes;
        here we add outcome + Brier/Log scores.
        """
        outcome_value = 1.0 if winning == "yes" else 0.0

        filled = []
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
            filled.append(score)

            if self._db:
                try:
                    self._db.save_score({
                        "market_id": market.id,
                        "user_id": trade.user_id,
                        "trade_id": trade.id,
                        "forecast_prob": forecast,
                        "outcome": outcome_value,
                        "brier_score": brier,
                        "log_score": log_s,
                        "created_at": timestamp.isoformat(),
                    }, commit=False)
                except Exception:
                    pass

        # Replace any prior stubs with the now-filled versions (avoids duplicates
        # and ensures in-memory list matches what was persisted).
        market.scores = filled

    def _get_user_aggregates(self, user_id: str) -> dict:
        """
        Internal helper that builds aggregated data for a user across all markets.
        Used by both get_user_portfolio() and get_leaderboard() to avoid duplication.

        Now also computes current position_value (MTM) for open positions.
        Per-market position entries for open markets are enriched with:
            "value": current MTM of that position, "p_yes", "p_no"
        """
        positions = {}
        realized_pnl = 0.0
        total_payouts = 0.0
        resolved_trades = 0
        open_count = 0
        resolved_count = 0
        position_value = 0.0

        for market in self.markets.values():
            pos = self.get_user_position(market.id, user_id)
            entry = {
                "yes": int(pos[0]),
                "no": int(pos[1]),
                "total": int(pos[0] + pos[1]),
            }

            if market.status == "resolved":
                resolved_count += 1
                entry["value"] = 0.0
                for p in market.payouts:
                    if p.user_id == user_id:
                        total_payouts += p.amount
                        realized_pnl += p.amount
                # Count resolved trades for this user
                resolved_trades += sum(1 for s in market.scores if s.user_id == user_id)
            else:
                open_count += 1
                prices = market.engine.price()
                p_yes, p_no = float(prices[0]), float(prices[1])
                mv = pos[0] * p_yes + pos[1] * p_no
                entry["value"] = float(mv)
                entry["p_yes"] = p_yes
                entry["p_no"] = p_no
                position_value += mv

            positions[market.id] = entry

        return {
            "positions": positions,
            "realized_pnl": realized_pnl,
            "total_payouts": total_payouts,
            "resolved_trades": resolved_trades,
            "open_count": open_count,
            "resolved_count": resolved_count,
            "position_value": position_value,
        }

    def get_user_portfolio(self, user_id: str) -> UserPortfolio:
        """
        Return a rich aggregated view of everything the user has.

        The returned UserPortfolio now always includes:
          - balance: current cash balance
          - position_value: sum of mark-to-market values of open positions
          - total_value: balance + position_value
        Per-market position dicts for open markets contain "value" (MTM) + current prices.
        """
        user = self.get_user(user_id)
        agg = self._get_user_aggregates(user_id)
        pv = agg.get("position_value", 0.0)

        return UserPortfolio(
            user_id=user_id,
            balance=user.balance,
            positions=agg["positions"],
            realized_pnl=agg["realized_pnl"],
            total_payouts_received=agg["total_payouts"],
            open_markets_count=agg["open_count"],
            resolved_markets_count=agg["resolved_count"],
            position_value=pv,
            total_value=user.balance + pv,
        )

    def get_user_position_value(self, user_id: str) -> float:
        """Return the current mark-to-market value of all this user's open positions."""
        agg = self._get_user_aggregates(user_id)
        return agg.get("position_value", 0.0)

    def get_user_total_value(self, user_id: str) -> float:
        """Return total account value = cash balance + current position MTM value."""
        return self.get_balance(user_id) + self.get_user_position_value(user_id)

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
    # JSON Serialization (new, complements pickle and DB)
    # ------------------------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable dict of the full simulator state."""
        users = [
            {"id": u.id, "balance": u.balance, "display_name": u.display_name}
            for u in self.users.values()
        ]

        markets = []
        for mid, m in self.markets.items():
            b_spec = _serialize_strategy(m.b)
            markets.append({
                "id": m.id,
                "title": m.title,
                "description": m.description,
                "resolution_criteria": m.resolution_criteria,
                "b_spec": b_spec,
                "fee_rate": m.fee_rate,
                "initial_subsidy": m.initial_subsidy,
                "status": m.status,
                "created_at": m.created_at.isoformat() if m.created_at else None,
                "close_at": m.close_at.isoformat() if m.close_at else None,
                "resolved_at": m.resolved_at.isoformat() if m.resolved_at else None,
                "resolution_outcome": m.resolution_outcome,
                "trades": [
                    {
                        "id": t.id,
                        "user_id": t.user_id,
                        "shares_yes": t.shares_yes,
                        "shares_no": t.shares_no,
                        "raw_cost": t.raw_cost,
                        "fee": t.fee,
                        "effective_cost": t.effective_cost,
                        "price_after_yes": t.price_after_yes,
                        "price_after_no": t.price_after_no,
                        "market_q_after": list(t.market_q_after),
                        "timestamp": t.timestamp.isoformat(),
                    }
                    for t in m.trades
                ],
                "payouts": [
                    {
                        "user_id": p.user_id,
                        "amount": p.amount,
                        "outcome": p.outcome,
                        "timestamp": p.timestamp.isoformat(),
                    }
                    for p in m.payouts
                ],
                "scores": [
                    {
                        "user_id": s.user_id,
                        "trade_id": s.trade_id,
                        "forecast_prob": s.forecast_prob,
                        "outcome": s.outcome,
                        "brier_score": s.brier_score,
                        "log_score": s.log_score,
                        "timestamp": s.timestamp.isoformat(),
                    }
                    for s in m.scores
                ],
            })

        return {
            "users": users,
            "markets": markets,
            "next_market_id": self._next_market_id,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any], db_path: str | Path | None = None) -> LMSRMarketSimulator:
        """Reconstruct a simulator from a dict produced by to_dict()."""
        sim = cls(db_path=db_path)  # this may load from DB if provided, but we will override

        # clear whatever was loaded
        sim.markets.clear()
        sim.users.clear()
        sim._positions_cache.clear()
        sim._next_market_id = data.get("next_market_id", 1)

        # users
        for ud in data.get("users", []):
            sim.users[ud["id"]] = User(
                id=ud["id"],
                balance=float(ud.get("balance", 1000.0)),
                display_name=ud.get("display_name"),
            )

        # markets + derived state
        for md in data.get("markets", []):
            mid = md["id"]
            b_spec = md.get("b_spec", {"type": "fixed", "value": 20.0})
            if b_spec["type"] == "fixed":
                b = b_spec["value"]
            elif b_spec["type"] == "linear":
                b = LinearVolumeB(alpha=b_spec.get("alpha", 0.05), min_b=b_spec.get("min_b", 5.0))
            elif b_spec["type"] == "bounded_linear":
                inner = LinearVolumeB(alpha=b_spec.get("alpha", 0.05), min_b=b_spec.get("min_b", 5.0))
                b = BoundedB(inner, min_b=b_spec.get("min_b", 5.0), max_b=b_spec.get("max_b", 300.0))
            else:
                b = 20.0

            market = Market(
                id=mid,
                title=md["title"],
                description=md.get("description", ""),
                resolution_criteria=md.get("resolution_criteria", ""),
                b=b,
                fee_rate=float(md.get("fee_rate", 0.02)),
                initial_subsidy=float(md.get("initial_subsidy", 0)),
                status=md.get("status", "open"),
            )

            # timestamps
            for ts_field in ("created_at", "close_at", "resolved_at"):
                if md.get(ts_field):
                    try:
                        setattr(market, ts_field, datetime.fromisoformat(md[ts_field]))
                    except Exception:
                        pass
            market.resolution_outcome = md.get("resolution_outcome")

            sim.markets[mid] = market
            sim._positions_cache[mid] = {}

            # replay trades (low level into engine)
            for td in md.get("trades", []):
                trade = Trade(
                    id=td["id"],
                    market_id=mid,
                    timestamp=datetime.fromisoformat(td["timestamp"]),
                    user_id=td["user_id"],
                    shares_yes=int(td["shares_yes"]),
                    shares_no=int(td["shares_no"]),
                    raw_cost=float(td["raw_cost"]),
                    fee=float(td["fee"]),
                    effective_cost=float(td["effective_cost"]),
                    price_after_yes=float(td["price_after_yes"]),
                    price_after_no=float(td["price_after_no"]),
                    market_q_after=tuple(td.get("market_q_after", (0.0, 0.0))),
                )
                market.trades.append(trade)
                market.engine.trade(trade.user_id, trade.shares_yes, trade.shares_no)

            # payouts
            for pd in md.get("payouts", []):
                market.payouts.append(Payout(
                    market_id=mid,
                    user_id=pd["user_id"],
                    amount=float(pd["amount"]),
                    outcome=pd["outcome"],
                    timestamp=datetime.fromisoformat(pd["timestamp"]),
                ))

            # scores (may be stubs with None outcome/brier/log, or filled)
            for sd in md.get("scores", []):
                market.scores.append(Score(
                    market_id=mid,
                    user_id=sd["user_id"],
                    trade_id=sd["trade_id"],
                    forecast_prob=float(sd["forecast_prob"]),
                    outcome=float(sd.get("outcome")) if sd.get("outcome") is not None else None,
                    brier_score=float(sd.get("brier_score")) if sd.get("brier_score") is not None else None,
                    log_score=float(sd.get("log_score")) if sd.get("log_score") is not None else None,
                    timestamp=datetime.fromisoformat(sd["timestamp"]),
                ))

        if db_path and sim._db:
            # Persist the loaded in-memory data to the target DB (so inspect etc see it)
            for uid, u in sim.users.items():
                sim._db.get_or_create_user(uid, u.display_name, u.balance, commit=False)
            for mid, mkt in sim.markets.items():
                sim._db.save_market(
                    id=mid,
                    title=mkt.title,
                    description=mkt.description,
                    resolution_criteria=mkt.resolution_criteria,
                    b=mkt.b,
                    fee_rate=mkt.fee_rate,
                    initial_subsidy=mkt.initial_subsidy,
                    status=mkt.status,
                    created_at=mkt.created_at.isoformat() if mkt.created_at else None,
                    close_at=mkt.close_at.isoformat() if mkt.close_at else None,
                    resolved_at=mkt.resolved_at.isoformat() if mkt.resolved_at else None,
                    resolution_outcome=mkt.resolution_outcome,
                    commit=False,
                )
                for t in mkt.trades:
                    sim._db.save_trade({
                        "id": t.id,
                        "market_id": mid,
                        "user_id": t.user_id,
                        "shares_yes": t.shares_yes,
                        "shares_no": t.shares_no,
                        "raw_cost": t.raw_cost,
                        "fee": t.fee,
                        "effective_cost": t.effective_cost,
                        "price_after_yes": t.price_after_yes,
                        "price_after_no": t.price_after_no,
                        "q_after_yes": t.market_q_after[0],
                        "q_after_no": t.market_q_after[1],
                        "created_at": t.timestamp.isoformat(),
                    }, commit=False)
                for p in mkt.payouts:
                    sim._db.save_payout({
                        "market_id": mid,
                        "user_id": p.user_id,
                        "amount": p.amount,
                        "outcome": p.outcome,
                        "created_at": p.timestamp.isoformat(),
                    }, commit=False)
                for s in mkt.scores:
                    sim._db.save_score({
                        "market_id": mid,
                        "user_id": s.user_id,
                        "trade_id": s.trade_id,
                        "forecast_prob": s.forecast_prob,
                        "outcome": s.outcome,
                        "brier_score": s.brier_score,
                        "log_score": s.log_score,
                        "created_at": s.timestamp.isoformat(),
                    }, commit=False)
            sim._db.conn.commit()

        return sim

    def save_json(self, filepath: str | Path) -> None:
        """Save full state as JSON (complements pickle and DB)."""
        path = Path(filepath)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, indent=2, ensure_ascii=False)

    @classmethod
    def load_json(cls, filepath: str | Path, db_path: str | Path | None = None) -> LMSRMarketSimulator:
        """Load from JSON file."""
        path = Path(filepath)
        if not path.exists():
            raise FileNotFoundError(f"No JSON state found at {path}")
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return cls.from_dict(data, db_path=db_path)

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

        Implements the trade flow from DESIGN.md §5 "Core Operations" / "Trade Flow (Atomic in a real DB)":
            1. (implicit lock via tx)
            2. Compute cost via engine.quote
            3. Balance + position checks (non-negative holdings)
            4. Execute via engine.trade (updates q + user_positions guard + revenue)
            5. Append immutable Trade (with denormalized price_after + q_after)
            6. Adjust user balance
            7. Insert stub Score row (forecast only; filled at resolution)

        The DB transaction (when db_path is set) covers trade + balance update + score stub
        for atomicity, matching the spec as closely as a SQLite prototype can.
        """
        market = self.get_market(market_id)

        if market.status != "open":
            return {
                "error": f"Cannot trade on a {market.status} market",
                "market_status": market.status,
            }

        # Enforce integer shares early (engine will also enforce, but nice error here)
        try:
            sy = int(shares_yes)
            sn = int(shares_no)
            if float(shares_yes) != sy or float(shares_no) != sn:
                return {
                    "error": "Fractional shares are not allowed. shares_yes and shares_no must be whole numbers.",
                }
        except (ValueError, TypeError):
            return {
                "error": "shares_yes and shares_no must be integers (no fractional shares).",
            }

        shares_yes, shares_no = sy, sn

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

        # Stub Score row at trade time (DESIGN.md §5 "Trade Flow" step 7):
        # "Insert stub `Score` row (scores filled at resolution)."
        # We record the forecast_prob = price_after_yes (the trader's revealed
        # belief at the moment of the trade). The outcome/brier/log are filled
        # later in _compute_and_store_scores during resolve_market.
        forecast = p_yes
        stub = Score(
            market_id=market_id,
            user_id=user_id,
            trade_id=trade_id,
            forecast_prob=forecast,
            outcome=None,
            brier_score=None,
            log_score=None,
            timestamp=trade.timestamp,
        )
        market.scores.append(stub)

        # Persist to DB (trade record + updated user balance + score stub)
        # inside a single transaction for atomicity (DESIGN.md trade flow).
        # Matches the "Atomic in a real DB" requirement as closely as SQLite allows.
        if self._db:
            conn = self._db.conn
            conn.execute("BEGIN IMMEDIATE")
            try:
                self._db.save_trade({
                    "id": trade_id,
                    "market_id": market_id,
                    "user_id": user_id,
                    "shares_yes": shares_yes,
                    "shares_no": shares_no,
                    "raw_cost": raw_cost,
                    "fee": result["fee"],
                    "effective_cost": effective_cost,
                    "price_after_yes": p_yes,
                    "price_after_no": p_no,
                    "q_after_yes": engine.q[0],
                    "q_after_no": engine.q[1],
                    "created_at": trade.timestamp.isoformat(),
                }, commit=False)
                # persist the balance change
                new_balance = self.get_balance(user_id)
                self._db.update_user_balance(user_id, new_balance, commit=False)
                # persist the score *stub* (forecast only; rest filled on resolve)
                self._db.save_score({
                    "market_id": market_id,
                    "user_id": user_id,
                    "trade_id": trade_id,
                    "forecast_prob": forecast,
                    "outcome": None,
                    "brier_score": None,
                    "log_score": None,
                    "created_at": trade.timestamp.isoformat(),
                }, commit=False)
                conn.commit()
            except Exception:
                conn.rollback()
                # DB write failure should not break the in-memory op in a research tool
                pass

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

        Implements DESIGN.md §5 "Resolution":
        - Payouts for winning-side holders + balance credits
        - Fill previously-inserted Score *stubs* (from trade time) with
          outcome + Brier/Log (using the historical forecast_prob from each Trade)
        - Automatic accounting identity check (the critical invariant from
          DESIGN.md: total_payouts_recorded == engine.q[winning], plus remainder)
        - Market status updated to resolved

        When a db_path is configured, the entire resolution (payouts +
        balance updates + score fills + status) runs inside one BEGIN
        IMMEDIATE transaction with rollback on any failure.
        """
        market = self.get_market(market_id)
        if market.status != "open":
            raise ValueError(f"Market {market_id} is already {market.status}")

        result = market.engine.resolve(outcome)
        winning = outcome.lower()
        idx = 0 if winning == "yes" else 1
        timestamp = datetime.now(timezone.utc)

        # Delegate the heavy lifting, with DB tx if present
        if self._db:
            conn = self._db.conn
            conn.execute("BEGIN IMMEDIATE")
            try:
                self._create_payouts_and_credit_balances(market, winning, idx, timestamp)
                self._compute_and_store_scores(market, winning, timestamp)
                self._finalize_resolution(market, winning, timestamp, result)
                conn.commit()
            except Exception:
                conn.rollback()
                raise
        else:
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

                if self._db:
                    try:
                        self._db.save_payout({
                            "market_id": market.id,
                            "user_id": user,
                            "amount": amount,
                            "outcome": winning,
                            "created_at": timestamp.isoformat(),
                        }, commit=False)
                        new_bal = self.get_balance(user)
                        self._db.update_user_balance(user, new_bal, commit=False)
                    except Exception:
                        pass

    def _finalize_resolution(
        self, market: Market, winning: str, timestamp: datetime, result: dict
    ) -> None:
        """Set final state on the market and attach accounting information to the result."""
        market.status = "resolved"
        market.resolution_outcome = winning
        market.resolved_at = timestamp

        if self._db:
            try:
                self._db.update_market_status(
                    market.id,
                    "resolved",
                    resolution_outcome=winning,
                    resolved_at=timestamp.isoformat(),
                    commit=False,
                )
            except Exception:
                pass

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
        self.users.clear()

        if self._db:
            try:
                self._db.clear_all()
            except Exception:
                pass

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
