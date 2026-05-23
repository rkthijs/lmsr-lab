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

import numpy as np

class BinaryLMSRMarket:
    """
    Numerically stable LMSR market maker for binary (Yes/No) events.

    This class maintains the market state and provides the core trading
    primitives recommended in DESIGN.md for an internal forecasting tool.

    Attributes
    ----------
    b : float
        Liquidity parameter. Larger values make the market "deeper" —
        prices move less for a given trade size. Typical values: 10–100.
    q : np.ndarray, shape (2,)
        Outstanding shares [q_yes, q_no]. This is the fundamental state.
    user_positions : dict[str, np.ndarray]
        Separate ledger of each user's holdings. Critical for preventing
        users from selling shares they do not own.
    total_revenue : float
        Total money collected by the market maker so far (including fees).
        Used at resolution to compute the market maker's P/L.

    Design Notes
    ------------
    - User positions are tracked *separately* from q (as specified in DESIGN.md).
    - All pricing and costing uses the hardened numerical methods.
    - A 2% fee is applied asymmetrically (see `quote`).
    - Resolution uses the simple "payout = winning shares" rule, which
      satisfies the fundamental accounting identity when combined with
      the cost function.
    """

    def __init__(self, b: float = 10.0, fee_rate: float = 0.02):
        """
        Create a new binary LMSR market.

        Parameters
        ----------
        b : float
            Liquidity parameter. Controls how much prices move per share traded.
            - Small b (e.g. 5–15): prices are very sensitive; good for small groups.
            - Larger b (e.g. 30–100): deeper market, less slippage on big trades.
        fee_rate : float
            Market-maker fee applied to every trade (default 2%).
            Positive fees are charged on buys, negative on sells (asymmetric).
        """
        self.b = float(b)
        self.fee_rate = float(fee_rate)
        self.q = np.array([0.0, 0.0])  # [q_yes, q_no]
        self.user_positions: dict[str, np.ndarray] = {}
        self.total_revenue = 0.0

    # ------------------------------------------------------------------
    # Numerically stable helpers (see DESIGN.md for rationale)
    # ------------------------------------------------------------------

    def _lse(self, q_over_b: np.ndarray) -> float:
        """Numerically stable log-sum-exp using logaddexp (avoids overflow)."""
        return float(np.logaddexp(q_over_b[0], q_over_b[1]))

    def _stable_prices(self, q: np.ndarray) -> tuple[float, float]:
        """
        Return (p_yes, p_no) using the stable softmax form:

            p_i = exp(q_i/b - LSE(q/b))

        This is equivalent to the direct formula but remains accurate even
        when q values are large.
        """
        q_over_b = q / self.b
        lse = self._lse(q_over_b)
        p_yes = float(np.exp(q_over_b[0] - lse))
        p_no = float(np.exp(q_over_b[1] - lse))
        return p_yes, p_no

    def _raw_cost_delta(self, delta: np.ndarray) -> float:
        """
        Numerically stable computation of C(q + delta) - C(q).

        Uses the identity derived in the design discussion:

            C(q') - C(q) = b * ln( Σ_i p_i * exp(Δq_i / b) )

        where p_i are the prices at the *starting* state q.

        This formula avoids catastrophic cancellation when |delta| is small
        relative to the current outstanding shares (the most common case in
        real trading). The old pattern `_cost(new_q) - _cost(q)` loses
        precision in exactly this regime.
        """
        if np.allclose(delta, 0.0):
            return 0.0

        p_yes, p_no = self._stable_prices(self.q)
        p = np.array([p_yes, p_no], dtype=float)

        exp_term = np.exp(delta / self.b)
        weighted_sum = float(np.sum(p * exp_term))

        return self.b * np.log(weighted_sum)

    def _cost(self, q: np.ndarray) -> float:
        """
        Absolute cost function C(q).

        Kept for reference / future use (e.g. when initializing a market with
        a known subsidy). For *differences* during trading, prefer
        _raw_cost_delta().
        """
        q_over_b = q / self.b
        return self.b * self._lse(q_over_b)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def price(self) -> tuple[float, float]:
        """
        Return the current market prices (p_yes, p_no).

        Prices are computed using the numerically stable softmax:

            p_yes = exp(q_yes/b - LSE(q/b))
            p_no  = exp(q_no/b  - LSE(q/b))

        Guarantees: p_yes + p_no == 1.0 (within floating point precision).

        This is the "fair" probability the market is currently assigning to
        each outcome, and is the quantity used for the Murphy decomposition
        in the scoring layer.
        """
        return self._stable_prices(self.q)

    def quote(self, shares_yes: float = 0.0, shares_no: float = 0.0) -> tuple[float, float]:
        """
        Compute the cost (including fee) of a hypothetical trade.

        Uses the hardened cost delta formula from DESIGN.md:

            raw_cost = b * ln( Σ p_i * exp(Δq_i / b) )

        Fee model (asymmetric):
            - When buying (raw_cost > 0): pay raw_cost * (1 + fee_rate)
            - When selling (raw_cost < 0): receive |raw_cost| * (1 - fee_rate)

        This is the function that should be called for "preview" calculations
        before executing a real trade.

        Returns
        -------
        effective_cost : float
            Amount the user actually pays (positive) or receives (negative).
        raw_cost : float
            The pure LMSR cost before fees.
        """
        delta = np.array([shares_yes, shares_no], dtype=float)

        # Use the numerically stable delta formula (see _raw_cost_delta docstring)
        raw_cost = self._raw_cost_delta(delta)

        # Apply fee (market maker cut)
        if raw_cost > 0:
            effective_cost = raw_cost * (1 + self.fee_rate)
        else:
            effective_cost = raw_cost * (1 - self.fee_rate)
        return effective_cost, raw_cost

    def trade(self, user_id: str, shares_yes: float = 0.0, shares_no: float = 0.0) -> dict:
        """
        Execute a trade for a user.

        This is the central state-mutating method. It:
        1. Validates that the user will not go negative on either outcome.
        2. Computes cost using the stable formula via `quote()`.
        3. Updates the global share vector `q`.
        4. Updates the user's separate position ledger.
        5. Records revenue (including fees) for the market maker.

        The separation of `q` (market state) and user_positions is deliberate
        and required by the design in DESIGN.md — it enables clean resolution
        accounting and prevents users from "selling what they don't own".

        Returns
        -------
        dict
            On success:
                cost, raw_cost, fee, new_prices, user_position
            On failure (insufficient shares):
                {"error": "Insufficient shares", "current_position": ...}
        """
        delta = np.array([shares_yes, shares_no], dtype=float)

        # Check that the user would not go negative on either leg
        current = self.user_positions.get(user_id, np.array([0.0, 0.0]))
        new_pos = current + delta
        if new_pos[0] < 0 or new_pos[1] < 0:
            return {
                "error": "Insufficient shares",
                "current_position": current.copy()
            }

        effective_cost, raw_cost = self.quote(shares_yes, shares_no)

        # Mutate market state
        self.q += delta

        # Update per-user ledger (the source of truth for what the user owns)
        if user_id not in self.user_positions:
            self.user_positions[user_id] = np.array([0.0, 0.0])
        self.user_positions[user_id] += delta

        # Record revenue for the market maker (used at resolution)
        self.total_revenue += effective_cost

        new_prices = self.price()
        return {
            "cost": effective_cost,
            "raw_cost": raw_cost,
            "fee": effective_cost - raw_cost,
            "new_prices": new_prices,
            "user_position": self.user_positions[user_id].copy()
        }

    def instantaneous_impact(self, shares_yes: float = 0.0, shares_no: float = 0.0) -> dict:
        """
        Compute the instantaneous price impact of a hypothetical trade
        **without** executing it.

        Useful for UI preview ("what would prices be after I buy 50 Yes?").

        Uses the same stable price computation as the live market.
        """
        p_before = self.price()
        delta = np.array([shares_yes, shares_no], dtype=float)
        new_q = self.q + delta

        p_after = self._stable_prices(new_q)
        impact_yes = p_after[0] - p_before[0]
        return {
            "price_before": p_before,
            "price_after": p_after,
            "impact": (impact_yes, -impact_yes)
        }

    def slippage(self, shares_yes: float = 0.0, shares_no: float = 0.0) -> dict:
        """
        Estimate average execution price and slippage for a proposed trade.

        Slippage here is defined as |average execution price - current price|.
        This is a practical UX metric, not a formal definition.
        """
        p_before = self.price()[0]
        effective_cost, _ = self.quote(shares_yes, shares_no)
        total_shares = shares_yes + shares_no
        avg_price = effective_cost / total_shares if total_shares != 0 else 0.0
        slip = abs(avg_price - p_before)
        return {
            "average_execution_price": avg_price,
            "slippage": slip
        }

    def get_user_position(self, user_id: str) -> np.ndarray:
        """Return a user's current holdings [yes_shares, no_shares]."""
        return self.user_positions.get(user_id, np.array([0.0, 0.0])).copy()

    def resolve(self, outcome: str) -> dict:
        """
        Resolve the market to 'yes' or 'no'.

        Payout rule (simple and correct per DESIGN.md):
            Every winning share pays exactly 1.0 unit.

        Therefore:
            payout = q_winning
            market_maker_pl = total_revenue - payout

        This satisfies the fundamental accounting identity:
            Σ payouts == total money paid in by traders + subsidy consumed

        After calling resolve(), the market should normally be considered closed.
        """
        outcome = outcome.lower()
        idx = 0 if outcome == "yes" else 1
        winning_shares = self.q[idx]
        payout = winning_shares
        pl = self.total_revenue - payout

        return {
            "market_maker_pl": pl,
            "total_revenue": self.total_revenue,
            "payout": payout,
            "winning_outcome": outcome
        }

    def reset(self) -> None:
        """
        Reset the market to its initial empty state.

        Useful for experiments, demos, and testing. In a production system
        you would almost never call this on a live market.
        """
        self.q = np.array([0.0, 0.0])
        self.user_positions = {}
        self.total_revenue = 0.0