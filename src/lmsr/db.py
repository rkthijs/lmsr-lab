"""
SQLite-backed persistence for the LMSR simulator.

This replaces the pickle save/load for durable storage while keeping
the in-memory simulator logic intact (great for tests, experiments,
and replay).

Schema is derived from DESIGN.md with small adaptations:
- TEXT ids (for compatibility with current "m1"/"alice" style ids)
- REAL for numeric values (NUMERIC(20,8) semantics approximated in Python float)
- Extra columns on markets for persisting adaptive b strategies

The simulator (when given a db_path) will:
- Load historical state on init by replaying trades (positions derived)
- Persist new markets, trades, user balances, payouts, and scores on mutation
- Support :memory: for tests or a file path for the demo/API

Atomicity for critical operations (trade + balance update) is done
with DB transactions where possible.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from .adaptive import BoundedB, LinearVolumeB


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class SQLiteStore:
    """
    Thin wrapper around sqlite3 for the LMSR domain.
    All monetary values are stored as REAL (Python float on read).
    """

    def __init__(self, db_path: str | Path = ":memory:"):
        self.db_path = ":memory:" if str(db_path) == ":memory:" else str(Path(db_path))
        self.conn = sqlite3.connect(
            self.db_path,
            check_same_thread=False,  # demo / single-process TestClient usage is fine
        )
        self.conn.row_factory = sqlite3.Row
        self.init_schema()

    def init_schema(self) -> None:
        cur = self.conn.cursor()

        # users
        cur.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id           TEXT PRIMARY KEY,
                display_name TEXT,
                balance      REAL NOT NULL DEFAULT 1000.0,
                created_at   TEXT NOT NULL
            )
        """)

        # markets (extended for adaptive b persistence)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS markets (
                id                  TEXT PRIMARY KEY,
                title               TEXT NOT NULL,
                description         TEXT,
                resolution_criteria TEXT,
                b                   REAL NOT NULL,
                fee_rate            REAL NOT NULL DEFAULT 0.02,
                initial_subsidy     REAL NOT NULL DEFAULT 0,
                status              TEXT NOT NULL DEFAULT 'open',
                created_at          TEXT NOT NULL,
                close_at            TEXT,
                resolved_at         TEXT,
                resolution_outcome  TEXT,
                -- strategy persistence (for adaptive b)
                strategy_type       TEXT DEFAULT 'fixed',
                alpha               REAL,
                min_b               REAL,
                max_b               REAL
            )
        """)

        # trades - append only
        cur.execute("""
            CREATE TABLE IF NOT EXISTS trades (
                id                TEXT PRIMARY KEY,
                market_id         TEXT NOT NULL REFERENCES markets(id),
                user_id           TEXT NOT NULL REFERENCES users(id),
                shares_yes        REAL NOT NULL,
                shares_no         REAL NOT NULL,
                raw_cost          REAL NOT NULL,
                fee               REAL NOT NULL,
                effective_cost    REAL NOT NULL,
                price_after_yes   REAL NOT NULL,
                price_after_no    REAL NOT NULL,
                q_after_yes       REAL NOT NULL,
                q_after_no        REAL NOT NULL,
                created_at        TEXT NOT NULL
            )
        """)

        # payouts
        cur.execute("""
            CREATE TABLE IF NOT EXISTS payouts (
                market_id   TEXT NOT NULL REFERENCES markets(id),
                user_id     TEXT NOT NULL REFERENCES users(id),
                amount      REAL NOT NULL,
                outcome     TEXT NOT NULL,
                created_at  TEXT NOT NULL,
                PRIMARY KEY (market_id, user_id)
            )
        """)

        # scores
        cur.execute("""
            CREATE TABLE IF NOT EXISTS scores (
                market_id     TEXT NOT NULL REFERENCES markets(id),
                user_id       TEXT NOT NULL REFERENCES users(id),
                trade_id      TEXT NOT NULL REFERENCES trades(id),
                forecast_prob REAL NOT NULL,
                outcome       REAL,
                brier_score   REAL,
                log_score     REAL,
                created_at    TEXT NOT NULL,
                PRIMARY KEY (market_id, trade_id)
            )
        """)

        self.conn.commit()

    # ---------------- users ----------------

    def get_or_create_user(self, user_id: str, display_name: str | None = None, balance: float = 1000.0) -> dict[str, Any]:
        cur = self.conn.cursor()
        cur.execute("SELECT * FROM users WHERE id = ?", (user_id,))
        row = cur.fetchone()
        if row:
            return dict(row)

        now = _now_iso()
        cur.execute(
            "INSERT INTO users (id, display_name, balance, created_at) VALUES (?, ?, ?, ?)",
            (user_id, display_name or user_id, float(balance), now),
        )
        self.conn.commit()
        return {"id": user_id, "display_name": display_name or user_id, "balance": float(balance), "created_at": now}

    def get_user(self, user_id: str) -> Optional[dict[str, Any]]:
        cur = self.conn.cursor()
        cur.execute("SELECT * FROM users WHERE id = ?", (user_id,))
        row = cur.fetchone()
        return dict(row) if row else None

    def update_user_balance(self, user_id: str, balance: float) -> None:
        cur = self.conn.cursor()
        cur.execute(
            "UPDATE users SET balance = ? WHERE id = ?",
            (float(balance), user_id),
        )
        self.conn.commit()

    def list_users(self) -> list[dict[str, Any]]:
        cur = self.conn.cursor()
        cur.execute("SELECT * FROM users")
        return [dict(r) for r in cur.fetchall()]

    # ---------------- markets ----------------

    def save_market(
        self,
        id: str,
        title: str,
        description: str = "",
        resolution_criteria: str = "",
        b: float | Any = 20.0,
        fee_rate: float = 0.02,
        initial_subsidy: float = 0.0,
        status: str = "open",
        created_at: str | None = None,
        close_at: str | None = None,
        resolved_at: str | None = None,
        resolution_outcome: str | None = None,
        # adaptive strategy info
        strategy_type: str = "fixed",
        alpha: float | None = None,
        min_b: float | None = None,
        max_b: float | None = None,
    ) -> None:
        now = created_at or _now_iso()

        # Detect adaptive strategy if a complex b was passed
        if not isinstance(b, (int, float)):
            # b is a strategy object (BoundedB wraps another)
            if isinstance(b, BoundedB):
                strategy_type = "bounded_linear"
                inner = b.strategy  # type: ignore[attr-defined]
                alpha = getattr(inner, "alpha", alpha)
                min_b = b.min_b
                max_b = b.max_b
                b_val = 20.0  # placeholder; engine will compute live value on load
            elif isinstance(b, LinearVolumeB):
                strategy_type = "linear"
                alpha = getattr(b, "alpha", alpha)
                min_b = getattr(b, "min_b", min_b)
                b_val = 20.0
            else:
                strategy_type = "fixed"
                b_val = float(b) if isinstance(b, (int, float)) else 20.0
        else:
            b_val = float(b)

        cur = self.conn.cursor()
        cur.execute(
            """
            INSERT OR REPLACE INTO markets
            (id, title, description, resolution_criteria, b, fee_rate, initial_subsidy,
             status, created_at, close_at, resolved_at, resolution_outcome,
             strategy_type, alpha, min_b, max_b)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                id, title, description, resolution_criteria, b_val, float(fee_rate), float(initial_subsidy),
                status, now, close_at, resolved_at, resolution_outcome,
                strategy_type, alpha, min_b, max_b,
            ),
        )
        self.conn.commit()

    def get_market(self, market_id: str) -> Optional[dict[str, Any]]:
        cur = self.conn.cursor()
        cur.execute("SELECT * FROM markets WHERE id = ?", (market_id,))
        row = cur.fetchone()
        return dict(row) if row else None

    def list_markets(self, status: str | None = None) -> list[dict[str, Any]]:
        cur = self.conn.cursor()
        if status:
            cur.execute("SELECT * FROM markets WHERE status = ? ORDER BY created_at", (status,))
        else:
            cur.execute("SELECT * FROM markets ORDER BY created_at")
        return [dict(r) for r in cur.fetchall()]

    def update_market_status(self, market_id: str, status: str, resolution_outcome: str | None = None,
                             resolved_at: str | None = None) -> None:
        cur = self.conn.cursor()
        cur.execute(
            "UPDATE markets SET status = ?, resolution_outcome = ?, resolved_at = ? WHERE id = ?",
            (status, resolution_outcome, resolved_at, market_id),
        )
        self.conn.commit()

    # ---------------- trades ----------------

    def save_trade(self, trade: dict[str, Any]) -> None:
        cur = self.conn.cursor()
        cur.execute(
            """
            INSERT OR REPLACE INTO trades
            (id, market_id, user_id, shares_yes, shares_no, raw_cost, fee, effective_cost,
             price_after_yes, price_after_no, q_after_yes, q_after_no, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                trade["id"],
                trade["market_id"],
                trade["user_id"],
                float(trade["shares_yes"]),
                float(trade["shares_no"]),
                float(trade["raw_cost"]),
                float(trade["fee"]),
                float(trade["effective_cost"]),
                float(trade["price_after_yes"]),
                float(trade["price_after_no"]),
                float(trade.get("q_after_yes", trade.get("market_q_after", (0, 0))[0])),
                float(trade.get("q_after_no", trade.get("market_q_after", (0, 0))[1])),
                trade.get("created_at") or trade.get("timestamp") or _now_iso(),
            ),
        )
        self.conn.commit()

    def get_trades(self, market_id: str) -> list[dict[str, Any]]:
        cur = self.conn.cursor()
        cur.execute("SELECT * FROM trades WHERE market_id = ? ORDER BY created_at", (market_id,))
        return [dict(r) for r in cur.fetchall()]

    # ---------------- payouts & scores ----------------

    def save_payout(self, payout: dict[str, Any]) -> None:
        cur = self.conn.cursor()
        cur.execute(
            """
            INSERT OR REPLACE INTO payouts
            (market_id, user_id, amount, outcome, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                payout["market_id"],
                payout["user_id"],
                float(payout["amount"]),
                payout["outcome"],
                payout.get("created_at") or payout.get("timestamp") or _now_iso(),
            ),
        )
        self.conn.commit()

    def get_payouts(self, market_id: str | None = None, user_id: str | None = None) -> list[dict[str, Any]]:
        cur = self.conn.cursor()
        if market_id and user_id:
            cur.execute("SELECT * FROM payouts WHERE market_id = ? AND user_id = ?", (market_id, user_id))
        elif market_id:
            cur.execute("SELECT * FROM payouts WHERE market_id = ?", (market_id,))
        elif user_id:
            cur.execute("SELECT * FROM payouts WHERE user_id = ?", (user_id,))
        else:
            cur.execute("SELECT * FROM payouts")
        return [dict(r) for r in cur.fetchall()]

    def save_score(self, score: dict[str, Any]) -> None:
        cur = self.conn.cursor()
        cur.execute(
            """
            INSERT OR REPLACE INTO scores
            (market_id, user_id, trade_id, forecast_prob, outcome, brier_score, log_score, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                score["market_id"],
                score["user_id"],
                score["trade_id"],
                float(score["forecast_prob"]),
                float(score.get("outcome", 0)),
                float(score.get("brier_score", 0)),
                float(score.get("log_score", 0)),
                score.get("created_at") or _now_iso(),
            ),
        )
        self.conn.commit()

    def get_scores(self, market_id: str | None = None, user_id: str | None = None) -> list[dict[str, Any]]:
        cur = self.conn.cursor()
        if market_id and user_id:
            cur.execute("SELECT * FROM scores WHERE market_id = ? AND user_id = ?", (market_id, user_id))
        elif market_id:
            cur.execute("SELECT * FROM scores WHERE market_id = ?", (market_id,))
        elif user_id:
            cur.execute("SELECT * FROM scores WHERE user_id = ?", (user_id,))
        else:
            cur.execute("SELECT * FROM scores")
        return [dict(r) for r in cur.fetchall()]

    def clear_all(self) -> None:
        """Dangerous: used by demo reset."""
        cur = self.conn.cursor()
        for table in ("scores", "payouts", "trades", "markets", "users"):
            cur.execute(f"DELETE FROM {table}")
        self.conn.commit()

    def close(self) -> None:
        self.conn.close()


# Convenience for reconstructing adaptive strategies from DB row
def reconstruct_b(row: dict[str, Any]) -> float | Any:
    stype = row.get("strategy_type") or "fixed"
    if stype == "fixed":
        return float(row["b"])
    if stype == "linear":
        return LinearVolumeB(
            alpha=row["alpha"] or 0.05,
            min_b=row["min_b"] or 5.0,
        )
    if stype == "bounded_linear":
        inner = LinearVolumeB(
            alpha=row["alpha"] or 0.05,
            min_b=row["min_b"] or 5.0,
        )
        return BoundedB(
            inner,
            min_b=row["min_b"] or 5.0,
            max_b=row["max_b"] or 300.0,
        )
    return float(row["b"])
