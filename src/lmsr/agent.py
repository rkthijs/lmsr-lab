"""
Ergonomic Bot / Agent API for the LMSR simulator.

This module provides a higher-level, bot-friendly wrapper around
`LMSRMarketSimulator`. It is the recommended interface for:

- Reinforcement learning agents
- Scripted / Kelly-based trading bots
- Market-making bots
- Large-scale multi-agent simulations

The goal (per the project plan in .hermes/plans/ and AGENTS.md) is:
- Clear separation between the core simulator and the bot-facing API
- Trivial integration: a bot only needs to manage its own `TradingAgent` instance
- Full support for both fixed `b` and adaptive/dynamic `b` strategies

Example usage (single bot):

    from src.lmsr import LMSRMarketSimulator
    from src.lmsr.agent import TradingAgent
    from src.lmsr.adaptive import LinearVolumeB, BoundedB

    sim = LMSRMarketSimulator()
    agent = TradingAgent(sim, user_id="my_rl_bot")

    # Create or join markets
    m = agent.create_market(
        "Will revenue beat target?",
        b=BoundedB(LinearVolumeB(alpha=0.05), min_b=10, max_b=300)
    )

    # Ergonomic trading
    result = agent.buy_yes(m.id, shares=25)
    obs = agent.observe(m.id)               # RL-friendly state dict
    print("Prices:", obs["prices"])
    print("Current b:", obs["current_b"])
    print("My position:", obs["position"])
    print("Cash:", obs["cash_balance"], "Pos value:", obs["position_value"], "Total:", obs["total_value"])

    # Hypothetical cost (no execution)
    quote = agent.quote(m.id, shares_yes=10)

    # For testing / controlled simulations
    agent.resolve(m.id, "yes")

The core `LMSRMarketSimulator` remains the single source of truth.
`TradingAgent` is a thin, convenient client for one user_id.
"""

from __future__ import annotations

from typing import Any

from .market import BType
from .simulator import LMSRMarketSimulator, Market, UserPortfolio


class TradingAgent:
    """
    High-level ergonomic wrapper representing one bot/agent/user in the simulator.

    Designed to make it trivial for automated agents to participate in markets
    without constantly threading `user_id` and `market_id` strings.

    All trading, querying, and market creation is scoped to `self.user_id`.

    Parameters
    ----------
    simulator : LMSRMarketSimulator
        The underlying multi-market simulator (single source of truth).
    user_id : str
        Stable identifier for this agent/bot (used across all markets).
    display_name : str, optional
        Human-friendly name (defaults to user_id).

    Attributes
    ----------
    simulator : LMSRMarketSimulator
    user_id : str
    """

    def __init__(
        self,
        simulator: LMSRMarketSimulator,
        user_id: str,
        display_name: str | None = None,
    ):
        self.simulator = simulator
        self.user_id = user_id
        simulator.get_or_create_user(user_id, display_name)

    # ------------------------------------------------------------------
    # Market discovery & creation (bot can create its own test markets)
    # ------------------------------------------------------------------

    def create_market(
        self,
        title: str,
        b: BType = 20.0,
        **kwargs: Any,
    ) -> Market:
        """
        Create a new market.

        Supports both fixed `b` (float) and adaptive strategies (callable or
        objects from `src/lmsr.adaptive`).

        Returns the created Market (same as simulator.create_market).
        """
        return self.simulator.create_market(title, b=b, **kwargs)

    def list_markets(self, status: str | None = "open") -> list[Market]:
        """List markets, optionally filtered by status ('open', 'closed', 'resolved')."""
        return self.simulator.list_markets(status)

    def get_market(self, market_id: str) -> Market:
        """Retrieve a market by id."""
        return self.simulator.get_market(market_id)

    # ------------------------------------------------------------------
    # Trading (the core ergonomic methods)
    # ------------------------------------------------------------------

    def trade(
        self,
        market_id: str,
        shares_yes: float = 0.0,
        shares_no: float = 0.0,
    ) -> dict[str, Any]:
        """
        Execute a trade (positive = buy, negative = sell).

        shares_yes / shares_no must be whole numbers. Fractional shares are not allowed.
        Returns the result dict from the underlying engine (cost, raw_cost, fee, etc.)
        or an error dict.
        """
        return self.simulator.place_trade(
            market_id, self.user_id, shares_yes, shares_no
        )

    def buy_yes(self, market_id: str, shares: float) -> dict[str, Any]:
        """Buy Yes shares (convenience wrapper). shares must be a whole number."""
        if shares <= 0:
            raise ValueError("shares must be positive for buy_yes")
        return self.trade(market_id, shares_yes=shares)

    def buy_no(self, market_id: str, shares: float) -> dict[str, Any]:
        """Buy No shares (convenience wrapper). shares must be a whole number."""
        if shares <= 0:
            raise ValueError("shares must be positive for buy_no")
        return self.trade(market_id, shares_no=shares)

    def sell_yes(self, market_id: str, shares: float) -> dict[str, Any]:
        """Sell Yes shares you hold (convenience wrapper). shares must be a whole number."""
        if shares <= 0:
            raise ValueError("shares must be positive for sell_yes")
        return self.trade(market_id, shares_yes=-shares)

    def sell_no(self, market_id: str, shares: float) -> dict[str, Any]:
        """Sell No shares you hold (convenience wrapper). shares must be a whole number."""
        if shares <= 0:
            raise ValueError("shares must be positive for sell_no")
        return self.trade(market_id, shares_no=-shares)

    # ------------------------------------------------------------------
    # Observation / state queries (scoped to this agent)
    # ------------------------------------------------------------------

    def get_position(self, market_id: str) -> list[int]:
        """Return this agent's current [yes_shares, no_shares] in the market (whole numbers)."""
        pos = self.simulator.get_user_position(market_id, self.user_id)
        return [int(pos[0]), int(pos[1])]

    def get_prices(self, market_id: str) -> tuple[float, float]:
        """Return current (p_yes, p_no) for the market."""
        market = self.get_market(market_id)
        return market.engine.price()

    def get_current_b(self, market_id: str) -> float:
        """Return the current effective liquidity parameter (handles adaptive b)."""
        market = self.get_market(market_id)
        return market.current_b

    def is_adaptive_b(self, market_id: str) -> bool:
        """Return True if this market is using a dynamic/adaptive b strategy."""
        market = self.get_market(market_id)
        return market.is_adaptive_b

    def observe(self, market_id: str) -> dict[str, Any]:
        """
        Return a compact observation dict suitable for RL agents and scripted bots.

        This aggregates the most commonly needed state into one call, making
        it easy to build observation vectors for reinforcement learning or
        to drive simple rule-based agents.

        The returned dict includes the three core account values users care about:
            - cash_balance: current cash (same as get_balance / get_cash_balance)
            - position_value: MTM value of *this market's* position at current prices
            - total_value: global cash + sum of position values across *all* markets

        Plus the usual per-market details.
        """
        market = self.get_market(market_id)
        prices = market.engine.price()
        pos = self.get_position(market_id)
        pos_value = float(pos[0] * prices[0] + pos[1] * prices[1])
        cash = self.get_balance()
        return {
            "market_id": market_id,
            "status": market.status,
            "prices": prices,
            "current_b": market.current_b,
            "is_adaptive": market.is_adaptive_b,
            "position": {
                "yes": int(pos[0]),
                "no": int(pos[1]),
                "total": int(pos[0] + pos[1]),
            },
            "balance": cash,                 # kept for backward compat
            "cash_balance": cash,
            "position_value": pos_value,
            "total_value": self.get_total_value(),
            "fee_rate": market.fee_rate,
            "num_trades": len(market.trades),
        }

    def quote(
        self, market_id: str, shares_yes: float = 0.0, shares_no: float = 0.0
    ) -> dict[str, float]:
        """
        Get cost, raw cost, and fee for a hypothetical trade without executing.

        Useful for agents that want to evaluate actions before committing.
        shares_yes/shares_no must be whole numbers (no fractional shares).
        """
        market = self.get_market(market_id)
        effective, raw = market.engine.quote(shares_yes, shares_no)
        return {
            "effective_cost": effective,
            "raw_cost": raw,
            "fee": effective - raw,
        }

    # ------------------------------------------------------------------
    # Personal state
    # ------------------------------------------------------------------

    def get_balance(self) -> float:
        """Current play-money balance (cash) for this agent."""
        return self.simulator.get_balance(self.user_id)

    def get_cash_balance(self) -> float:
        """Current cash balance. Clear synonym for get_balance()."""
        return self.get_balance()

    def get_position_value(self, market_id: str | None = None) -> float:
        """
        Mark-to-market value of positions.

        If market_id is given: value of the position in that single market.
        If None (default): sum of MTM values across *all* markets for this agent.
        """
        if market_id is not None:
            prices = self.get_prices(market_id)
            pos = self.get_position(market_id)
            return float(pos[0] * prices[0] + pos[1] * prices[1])
        return self.simulator.get_user_position_value(self.user_id)

    def get_total_value(self) -> float:
        """Total account value = cash balance + current position MTM (all markets)."""
        return self.get_cash_balance() + self.get_position_value()

    def get_portfolio(self) -> UserPortfolio:
        """Rich cross-market view of this agent's positions, PnL, etc.

        The portfolio object now carries .balance (cash), .position_value, and .total_value.
        """
        return self.simulator.get_user_portfolio(self.user_id)

    # ------------------------------------------------------------------
    # Resolution (mainly useful for controlled experiments / tests)
    # ------------------------------------------------------------------

    def resolve_market(self, market_id: str, outcome: str) -> dict:
        """
        Resolve a market (delegates to the simulator).

        Returns the resolution result including accounting identity checks.
        """
        return self.simulator.resolve_market(market_id, outcome)

    # ------------------------------------------------------------------
    # Convenience
    # ------------------------------------------------------------------

    def __repr__(self) -> str:
        return f"TradingAgent(user_id={self.user_id!r})"
