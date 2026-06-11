"""
Binary LMSR Market Maker — Numerically stable implementation.

This module implements the core of Robin Hanson's Logarithmic Market Scoring Rule
(LMSR) for **binary** (Yes/No) prediction markets, as designed in DESIGN.md.

Mathematical Foundation (from the design conversation)
----------------------------------------------------
The cost function for a binary LMSR market is:

    C(q) = b * ln( exp(q_yes / b) + exp(q_no / b) )

where:
- q = [q_yes, q_no]  : outstanding shares in each outcome
- b                  : liquidity parameter (higher b = more liquid market)

Current market prices are given by the softmax:

    p_yes = exp(q_yes / b) / (exp(q_yes / b) + exp(q_no / b))
    p_no  = 1 - p_yes

The cost of moving from state q to q' is simply C(q') - C(q). This gives
the market maker a bounded worst-case loss of b * ln(2) for binary markets.

Why LMSR for an internal tool (per DESIGN.md):
- Clean probability interpretation
- Bounded loss for the market maker (important when you control the subsidy)
- Single intuitive knob (b) to control sensitivity
- Excellent theoretical calibration properties

Numerical Stability (2025 hardening)
------------------------------------
Direct evaluation of C(q' ) - C(q) suffers from catastrophic cancellation
when trades are small relative to existing volume. This module therefore uses
the algebraically equivalent but numerically stable form:

    ΔC = b * ln( Σ p_i * exp(Δq_i / b) )

where p_i are the prices *before* the trade.

All price calculations use the stable softmax:
    p_i = exp(q_i/b - LSE(q/b))

See DESIGN.md sections:
- "numerical stability"
- "log-sum-exp trick"
- "catastrophic cancellation"
- "resolution and payout math"
- "the accounting identity"

References
----------
- Robin Hanson, "Logarithmic Market Scoring Rules for Modular Combinatorial
  Information Aggregation" (2002) — the original LMSR paper.
- DESIGN.md (primary source of truth for this project)
"""

from __future__ import annotations

import numpy as np
import numpy.typing as npt
from typing import Any, Callable, Union

# Type for b: either a fixed float or a function q -> b
BType = Union[float, Callable[[npt.NDArray[np.floating]], float]]


class BinaryLMSRMarket:
    """
    Numerically stable LMSR market maker for binary (Yes/No) events.

    This class maintains the market state and provides the core trading
    primitives recommended in DESIGN.md for an internal forecasting tool.

    Attributes
    ----------
    b : float | Callable
        Liquidity parameter or adaptive function.
        - If float: fixed liquidity (classic LMSR behavior).
        - If callable: dynamic/adaptive liquidity. The callable receives the
          current share vector `q` and must return a positive float for `b`.
          This enables Liquidity-Sensitive LMSR variants (see Othman et al. 2013).
    q : np.ndarray, shape (2,)
        Outstanding shares [q_yes, q_no]. This is the fundamental state.
    user_positions : dict[str, np.ndarray]
        Separate ledger of each user's holdings.
    total_revenue : float
        Net cash the market maker has received from traders so far
        (sum of effective_cost over all trades, positive and negative).
        Used for final P/L accounting at resolution.

    total_fees_earned : float
        Total fees/spread captured by the market maker across all trades
        (both buys and sells). This is the amount the MM actually "makes"
        from the asymmetric fee model / spread. Always non-negative and
        only increases.

    Design Notes
    ------------
    - Supports both fixed and dynamic/adaptive `b`.
    - When using adaptive b, `b` is re-evaluated at each pricing/costing step
      based on the current `q`.
    - User positions are tracked *separately* from q (as specified in DESIGN.md).

    Examples
    --------
    Fixed liquidity (classic):
        >>> m = BinaryLMSRMarket(b=50)

    Adaptive liquidity (b grows with volume):
        >>> from src.lmsr.adaptive import LinearVolumeB
        >>> m = BinaryLMSRMarket(b=LinearVolumeB(alpha=0.05, min_b=10))
    """

    def __init__(self, b: BType = 10.0, fee_rate: float = 0.02):
        """
        Create a new binary LMSR market.

        Parameters
        ----------
        b : float or callable
            Liquidity parameter.
            - float: Fixed b (classic LMSR). Typical values 10–200.
            - callable: Adaptive b function with signature `b(q) -> float`.
              The function receives the current share vector and returns
              the liquidity to use at that moment. Enables dynamic liquidity
              rules (e.g. b growing with trading volume).
        fee_rate : float
            Market-maker fee applied to every trade (default 2%).
        """
        self._b: BType = b
        self.fee_rate = float(fee_rate)
        self.q = np.array([0.0, 0.0])
        self.user_positions: dict[str, np.ndarray] = {}
        self.total_revenue = 0.0
        self.total_fees_earned = 0.0

    @property
    def b(self) -> float:
        """Return the current effective b (evaluates adaptive function if needed)."""
        return self._get_current_b()

    @b.setter
    def b(self, value: float) -> None:
        """
        Set a new fixed b value.

        This only works for markets that were originally created with a fixed
        (non-adaptive) b. If the market uses a dynamic b strategy (callable),
        attempting to set b will raise an AttributeError.
        """
        if callable(self._b):
            raise AttributeError(
                "Cannot directly set 'b' on a market that uses adaptive/dynamic liquidity. "
                "This market was created with a b strategy (e.g. LinearVolumeB). "
                "You can only change b on markets that use a fixed numeric value."
            )
        self._b = float(value)

    def _get_current_b(self) -> float:
        """Internal: get the liquidity value for the current state."""
        if callable(self._b):
            b_val = self._b(self.q)
            if b_val <= 0:
                raise ValueError("Adaptive b function must return a positive value")
            return float(b_val)
        return float(self._b)

    @property
    def is_adaptive_b(self) -> bool:
        """Returns True if this market uses a dynamic/adaptive b strategy."""
        return callable(self._b)

    def set_b_strategy(self, strategy: Any) -> None:
        """
        Replace the current b (fixed or adaptive) with a new strategy or fixed value.

        This is the recommended way to change liquidity behavior at runtime
        for both fixed and adaptive markets.
        """
        self._b = strategy

    # ------------------------------------------------------------------
    # Numerically stable helpers (see DESIGN.md for rationale)
    # ------------------------------------------------------------------

    def _lse(self, q_over_b: npt.NDArray[np.floating]) -> float:
        """
        Numerically stable log-sum-exp for two values.

        Uses numpy.logaddexp which is stable even for large positive inputs.

        Parameters
        ----------
        q_over_b : ndarray of shape (2,)
            The share vector divided by b, i.e. q / b.

        Returns
        -------
        float
            log(exp(x) + exp(y)) computed stably.
        """
        return float(np.logaddexp(q_over_b[0], q_over_b[1]))

    def _stable_prices(self, q: npt.NDArray[np.floating]) -> tuple[float, float]:
        """
        Compute stable prices for a given share vector `q`.

        Uses the numerically stable softmax:

            p_i = exp(q_i / b - LSE(q / b))

        Parameters
        ----------
        q : ndarray of shape (2,)
            Outstanding shares [q_yes, q_no].

        Returns
        -------
        tuple[float, float]
            (p_yes, p_no) — current market prices.
        """
        b = self._get_current_b()
        q_over_b = q / b
        lse = self._lse(q_over_b)
        p_yes = float(np.exp(q_over_b[0] - lse))
        p_no = float(np.exp(q_over_b[1] - lse))
        return p_yes, p_no

    def _raw_cost_delta(self, delta: npt.NDArray[np.floating]) -> float:
        """
        Numerically stable computation of the raw LMSR cost of a trade.

        Uses the identity:

            ΔC = b * ln( Σ_i p_i * exp(Δq_i / b) )

        where p_i are the prices *before* the trade.

        This avoids catastrophic cancellation for small trades (the most
        common case).

        Parameters
        ----------
        delta : ndarray of shape (2,)
            Proposed change in shares [Δq_yes, Δq_no].

        Returns
        -------
        float
            The raw cost (before fees) of the proposed trade.
        """
        if np.allclose(delta, 0.0):
            return 0.0

        b = self._get_current_b()
        p_yes, p_no = self._stable_prices(self.q)
        p = np.array([p_yes, p_no], dtype=float)

        exp_term = np.exp(delta / b)
        weighted_sum = float(np.sum(p * exp_term))

        return b * np.log(weighted_sum)

    def _cost(self, q: npt.NDArray[np.floating]) -> float:
        """
        Compute the absolute LMSR cost C(q) for a given share vector.

        This is the total "money" the market maker would have collected
        to reach the current outstanding shares `q` (ignoring fees).

        Parameters
        ----------
        q : ndarray of shape (2,)
            Outstanding shares [q_yes, q_no].

        Returns
        -------
        float
            The absolute cost C(q).
        """
        b = self._get_current_b()
        q_over_b = q / b
        return b * self._lse(q_over_b)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def price(self) -> tuple[float, float]:
        """
        Return the current market prices for Yes and No.

        Prices are always a valid probability distribution (sum to 1.0)
        and are computed using the numerically stable softmax.

        Returns
        -------
        tuple[float, float]
            (p_yes, p_no) — current prices in [0, 1].
        """
        return self._stable_prices(self.q)

    def quote(self, shares_yes: float = 0.0, shares_no: float = 0.0) -> tuple[float, float]:
        """
        Return the cost (with fee) of a hypothetical trade without executing it.

        Parameters
        ----------
        shares_yes : float, default 0.0
            Number of Yes shares to buy (positive) or sell (negative).
        shares_no : float, default 0.0
            Number of No shares to buy (positive) or sell (negative).

        Returns
        -------
        effective_cost : float
            Amount the user would pay (positive) or receive (negative),
            including the market maker fee.
        raw_cost : float
            The pure LMSR cost of the trade before fees.
        """
        delta = np.array([shares_yes, shares_no], dtype=float)
        raw_cost = self._raw_cost_delta(delta)

        if raw_cost > 0:
            effective_cost = raw_cost * (1 + self.fee_rate)
        else:
            effective_cost = raw_cost * (1 - self.fee_rate)

        return float(effective_cost), float(raw_cost)

    def trade(
        self, user_id: str, shares_yes: float = 0.0, shares_no: float = 0.0
    ) -> dict[str, Any]:
        """
        Execute a trade (buy or sell) for a given user.

        Parameters
        ----------
        user_id : str
            Identifier for the user executing the trade.
        shares_yes : float, default 0.0
            Number of Yes shares to buy (positive) or sell (negative).
        shares_no : float, default 0.0
            Number of No shares to buy (positive) or sell (negative).

        Returns
        -------
        dict
            On success:
                - "cost" : float
                    Total amount paid (positive) or received (negative), including fee.
                - "raw_cost" : float
                    Pure LMSR cost before fees.
                - "fee" : float
                    Fee paid to the market maker.
                - "new_prices" : tuple[float, float]
                    (p_yes, p_no) after the trade.
                - "user_position" : ndarray of shape (2,)
                    User's new [yes_shares, no_shares].

            On failure (insufficient shares to sell):
                - "error" : str
                    "Insufficient shares"
                - "current_position" : ndarray
                    User's position before the failed trade.
        """
        delta = np.array([shares_yes, shares_no], dtype=float)

        current = self.user_positions.get(user_id, np.array([0.0, 0.0]))
        new_pos = current + delta
        if new_pos[0] < 0 or new_pos[1] < 0:
            return {
                "error": "Insufficient shares",
                "current_position": current.copy(),
            }

        effective_cost, raw_cost = self.quote(shares_yes, shares_no)

        self.q += delta

        if user_id not in self.user_positions:
            self.user_positions[user_id] = np.array([0.0, 0.0])
        self.user_positions[user_id] += delta

        self.total_revenue += effective_cost

        # Always record the positive fee/spread earned by the MM on this trade.
        # This captures the spread whether the trader is buying or selling.
        fee = effective_cost - raw_cost
        self.total_fees_earned += fee

        new_prices = self.price()

        return {
            "cost": float(effective_cost),
            "raw_cost": float(raw_cost),
            "fee": float(fee),
            "new_prices": new_prices,
            "user_position": [float(x) for x in self.user_positions[user_id]],
        }

    def instantaneous_impact(
        self, shares_yes: float = 0.0, shares_no: float = 0.0
    ) -> dict[str, Any]:
        """
        Compute the immediate price impact of a hypothetical trade.

        This does **not** execute the trade — it only shows what would happen.

        Parameters
        ----------
        shares_yes : float, default 0.0
            Hypothetical Yes shares to trade.
        shares_no : float, default 0.0
            Hypothetical No shares to trade.

        Returns
        -------
        dict
            - "price_before" : tuple[float, float]
            - "price_after" : tuple[float, float]
            - "impact" : tuple[float, float]
                Change in price for (Yes, No).
        """
        p_before = self.price()
        delta = np.array([shares_yes, shares_no], dtype=float)
        new_q = self.q + delta

        p_after = self._stable_prices(new_q)
        impact_yes = float(p_after[0] - p_before[0])

        return {
            "price_before": tuple(float(x) for x in p_before),
            "price_after": tuple(float(x) for x in p_after),
            "impact": (impact_yes, -impact_yes),
        }

    def slippage(
        self, shares_yes: float = 0.0, shares_no: float = 0.0
    ) -> dict[str, float]:
        """
        Estimate the average execution price and slippage for a proposed trade.

        Parameters
        ----------
        shares_yes : float, default 0.0
            Proposed Yes shares.
        shares_no : float, default 0.0
            Proposed No shares.

        Returns
        -------
        dict
            - "average_execution_price" : float
            - "slippage" : float
                Absolute difference between average execution price and current price.
        """
        p_before = self.price()[0]
        effective_cost, _ = self.quote(shares_yes, shares_no)
        total_shares = shares_yes + shares_no
        avg_price = effective_cost / total_shares if total_shares != 0 else 0.0
        slip = abs(avg_price - p_before)

        return {
            "average_execution_price": float(avg_price),
            "slippage": float(slip),
        }

    def get_user_position(self, user_id: str) -> npt.NDArray[np.floating]:
        """
        Return the current share holdings of a user.

        Parameters
        ----------
        user_id : str

        Returns
        -------
        ndarray of shape (2,)
            [yes_shares, no_shares] for the given user.
        """
        return self.user_positions.get(user_id, np.array([0.0, 0.0])).copy()  # type: ignore[return-value]

    def resolve(self, outcome: str) -> dict[str, Any]:
        """
        Resolve the market to a final outcome.

        Parameters
        ----------
        outcome : {"yes", "no"}
            The outcome to resolve the market to.

        Returns
        -------
        dict
            - "market_maker_pl" : float
                Profit/loss for the market maker.
            - "total_revenue" : float
                Net cash received from traders (sum of effective_cost).
            - "total_fees_earned" : float
                Total spread/fees captured by the market maker on all trades
                (both buy and sell sides). This is what the MM actually earns.
            - "payout" : float
                Total amount paid out to winners.
            - "winning_outcome" : str
                The resolved outcome ("yes" or "no").
        """
        outcome = outcome.lower()
        idx = 0 if outcome == "yes" else 1
        winning_shares = float(self.q[idx])
        payout = winning_shares
        pl = float(self.total_revenue - payout)

        return {
            "market_maker_pl": pl,
            "total_revenue": float(self.total_revenue),
            "total_fees_earned": float(self.total_fees_earned),
            "payout": payout,
            "winning_outcome": outcome,
        }

    def reset(self) -> None:
        """
        Reset the market to its initial empty state.

        This clears all outstanding shares, user positions, and revenue.
        Useful for experiments and testing.
        """
        self.q = np.array([0.0, 0.0])
        self.user_positions = {}
        self.total_revenue = 0.0
        self.total_fees_earned = 0.0