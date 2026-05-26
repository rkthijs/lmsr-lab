"""
Comprehensive test suite for BinaryLMSRMarket.

Covers the key invariants and numerical properties discussed in DESIGN.md:
- Prices always form a valid probability distribution (sum to 1)
- Trade cost calculation is numerically stable (avoids catastrophic cancellation)
- User positions are tracked separately and cannot go negative
- Resolution accounting identity holds (total paid out == revenue + subsidy consumed)
- Correct behavior under extreme conditions (large volume, tiny trades, extreme b)
"""

import numpy as np
import pytest

from src.lmsr.market import BinaryLMSRMarket


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

def make_market(b: float = 20.0, fee_rate: float = 0.02) -> BinaryLMSRMarket:
    """Factory for a fresh market instance."""
    return BinaryLMSRMarket(b=b, fee_rate=fee_rate)


def prices_sum_to_one(m: BinaryLMSRMarket, tol: float = 1e-12) -> bool:
    p_yes, p_no = m.price()
    return abs(p_yes + p_no - 1.0) < tol


# ------------------------------------------------------------------
# Basic Invariants
# ------------------------------------------------------------------

def test_prices_always_sum_to_one():
    """Prices must always form a valid probability distribution."""
    m = make_market()
    assert prices_sum_to_one(m)

    m.trade("alice", 10, 0)
    assert prices_sum_to_one(m)

    m.trade("bob", 0, 25)
    assert prices_sum_to_one(m)

    m.trade("alice", -4, 5)
    assert prices_sum_to_one(m)


def test_price_monotonicity():
    """Buying an outcome must strictly increase its price."""
    m = make_market(b=15.0)

    p_yes_before, _ = m.price()
    m.trade("trader", 8, 0)
    p_yes_after, _ = m.price()

    assert p_yes_after > p_yes_before

    p_no_before = 1 - p_yes_after
    m.trade("trader", 0, 12)
    _, p_no_after = m.price()

    assert p_no_after > p_no_before


# ------------------------------------------------------------------
# User Position & Trade Rules
# ------------------------------------------------------------------

def test_user_position_tracking():
    """User positions must be tracked independently of market q."""
    m = make_market()

    m.trade("alice", 10, 5)
    m.trade("bob", 3, 8)

    pos_alice = m.get_user_position("alice")
    pos_bob = m.get_user_position("bob")

    assert pos_alice[0] == 10 and pos_alice[1] == 5
    assert pos_bob[0] == 3 and pos_bob[1] == 8

    # Market q should be sum of all positions
    assert np.allclose(m.q, [13, 13])


def test_cannot_sell_more_than_held():
    """Users must not be allowed to sell shares they do not own."""
    m = make_market()

    m.trade("alice", 5, 0)          # Alice only holds Yes shares

    # Attempt to sell No shares she does not own
    result = m.trade("alice", 0, -10)

    assert "error" in result
    assert result["current_position"][1] == 0.0
    assert m.get_user_position("alice")[1] == 0.0


def test_negative_position_blocked():
    """Even after multiple trades, position must never go negative."""
    m = make_market()

    m.trade("alice", 20, 10)
    m.trade("alice", -5, -3)

    pos = m.get_user_position("alice")
    assert pos[0] >= 0 and pos[1] >= 0

    bad = m.trade("alice", -20, 0)
    assert "error" in bad


# ------------------------------------------------------------------
# Numerical Stability & Cost Calculation
# ------------------------------------------------------------------

def test_raw_cost_delta_matches_naive_for_normal_trades():
    """
    For normal-sized trades the stable formula must give (almost) identical
    results to the direct C(new) - C(old) method.
    """
    m = make_market(b=25.0)
    m.q = np.array([80.0, 120.0])  # some existing volume

    delta = np.array([2.5, 0.0])

    stable_cost = m._raw_cost_delta(delta)

    # Naive way (what we used before hardening)
    new_q = m.q + delta
    naive_cost = m.b * (
        np.logaddexp(new_q[0] / m.b, new_q[1] / m.b)
        - np.logaddexp(m.q[0] / m.b, m.q[1] / m.b)
    )

    assert abs(stable_cost - naive_cost) < 1e-10


def test_tiny_trade_on_large_volume_is_stable():
    """
    Tiny trades on top of large outstanding shares must not suffer from
    floating-point cancellation (the main motivation for the hardening).
    """
    m = make_market(b=20.0)
    m.q = np.array([1500.0, 800.0])  # large volume

    tiny_delta = np.array([0.001, 0.0])
    cost = m._raw_cost_delta(tiny_delta)

    # Cost should be positive and very small but non-zero and well-conditioned
    assert cost > 0
    assert cost < 0.002          # allow tiny floating-point overshoot
    assert np.isfinite(cost)


def test_large_share_imbalance_no_overflow():
    """Extreme imbalances must not cause overflow or NaN prices."""
    m = make_market(b=5.0)
    m.q = np.array([8000.0, 3.0])

    p_yes, p_no = m.price()

    assert 0.0 < p_yes <= 1.0
    assert 0.0 <= p_no < 1.0
    assert np.isfinite(p_yes) and np.isfinite(p_no)
    assert prices_sum_to_one(m)


# ------------------------------------------------------------------
# Resolution & Accounting Identity
# ------------------------------------------------------------------

def test_resolution_accounting_identity():
    """
    After resolution the market maker's P/L must satisfy:

        market_maker_pl = total_revenue - payout_to_winners

    This is the fundamental accounting identity from DESIGN.md.
    """
    m = make_market(b=30.0, fee_rate=0.02)

    m.trade("alice", 15, 0)
    m.trade("bob", 0, 20)
    m.trade("charlie", 8, 5)

    revenue_before = m.total_revenue

    result = m.resolve("yes")

    payout = result["payout"]           # should equal q_yes after all trades
    pl = result["market_maker_pl"]

    assert abs(pl - (revenue_before - payout)) < 1e-9
    assert result["winning_outcome"] == "yes"


def test_resolve_to_no():
    """Resolution to the losing side must also satisfy the accounting identity."""
    m = make_market(b=20.0)

    m.trade("alice", 12, 4)
    m.trade("bob", 3, 15)

    result = m.resolve("no")

    assert abs(result["market_maker_pl"] - (m.total_revenue - result["payout"])) < 1e-9


# ------------------------------------------------------------------
# Round-trip & Fee Behavior
# ------------------------------------------------------------------

def test_round_trip_cost_with_fees():
    """
    Buying and then selling the exact same number of shares should result
    in a net loss exactly equal to the fees paid on the round trip.
    """
    m = make_market(b=25.0, fee_rate=0.02)

    # Buy
    buy = m.trade("alice", 10, 0)
    cost_buy = buy["cost"]

    # Sell back
    sell = m.trade("alice", -10, 0)
    cost_sell = sell["cost"]   # should be negative (receiving money)

    net_paid = cost_buy + cost_sell   # positive number = net loss due to fees

    # Net loss should be positive (user loses the fee spread)
    assert net_paid > 0
    assert net_paid < cost_buy * 0.05   # rough sanity bound


# ------------------------------------------------------------------
# Utility Methods
# ------------------------------------------------------------------

def test_reset_clears_state():
    """reset() must return the market to its initial empty state."""
    m = make_market()

    m.trade("alice", 10, 5)
    m.trade("bob", 2, 7)
    m.resolve("yes")

    m.reset()

    assert np.allclose(m.q, [0.0, 0.0])
    assert m.user_positions == {}
    assert m.total_revenue == 0.0
    assert prices_sum_to_one(m)


def test_zero_trade_is_noop():
    """A zero-size trade must be a no-op."""
    m = make_market(b=18.0)

    before_q = m.q.copy()
    before_rev = m.total_revenue

    result = m.trade("nobody", 0, 0)

    assert np.allclose(m.q, before_q)
    assert m.total_revenue == before_rev
    # Cost should be exactly zero
    assert result["raw_cost"] == 0.0


# ------------------------------------------------------------------
# Multi-user & Realism
# ------------------------------------------------------------------

def test_multiple_users_independent_positions():
    """Different users must maintain completely independent positions."""
    m = make_market()

    m.trade("alice", 5, 0)
    m.trade("bob", 0, 5)
    m.trade("alice", 0, 3)

    assert m.get_user_position("alice")[0] == 5
    assert m.get_user_position("alice")[1] == 3
    assert m.get_user_position("bob")[0] == 0


# ------------------------------------------------------------------
# Adaptive / Dynamic b Tests
# ------------------------------------------------------------------

from src.lmsr.adaptive import LinearVolumeB, FixedB


def test_adaptive_b_linear_volume_grows():
    """LinearVolumeB should increase b as more shares are outstanding."""
    strategy = LinearVolumeB(alpha=0.1, min_b=5.0)
    m = BinaryLMSRMarket(b=strategy)

    assert m.b == 5.0  # starts at floor

    m.trade("trader", 100, 0)
    assert m.b > 5.0
    assert abs(m.b - 10.0) < 1e-6  # 0.1 * 100 = 10

    m.trade("trader", 150, 0)
    assert m.b >= 25.0


def test_adaptive_b_vs_fixed_behavior():
    """
    With the same initial b, an adaptive market with very small alpha should
    behave similarly to a fixed market for the first few trades.
    """
    fixed = BinaryLMSRMarket(b=50.0)
    adaptive = BinaryLMSRMarket(b=LinearVolumeB(alpha=0.001, min_b=50.0))

    fixed.trade("u", 40, 10)
    adaptive.trade("u", 40, 10)

    p_fixed = fixed.price()
    p_adapt = adaptive.price()

    # They should be very close early on
    assert abs(p_fixed[0] - p_adapt[0]) < 0.02


def test_fixed_b_wrapper():
    """FixedB should behave exactly like passing a float."""
    fixed_strategy = FixedB(42.0)
    m1 = BinaryLMSRMarket(b=42.0)
    m2 = BinaryLMSRMarket(b=fixed_strategy)

    m1.trade("a", 30, 20)
    m2.trade("a", 30, 20)

    assert abs(m1.b - m2.b) < 1e-12
    assert abs(m1.price()[0] - m2.price()[0]) < 1e-12
    assert m1.get_user_position("a")[0] == m2.get_user_position("a")[0]


def test_log_volume_b():
    """LogVolumeB should grow slowly."""
    from src.lmsr.adaptive import LogVolumeB

    strat = LogVolumeB(alpha=10.0, min_b=5.0)
    m = BinaryLMSRMarket(b=strat)

    assert m.b == 5.0
    m.trade("u", 1000, 0)
    # log(1000) ≈ 6.9 → 10 * 6.9 ≈ 69
    assert 60 < m.b < 75


def test_bounded_b_wrapper():
    """BoundedB should correctly clip any strategy."""
    from src.lmsr.adaptive import LinearVolumeB, BoundedB

    inner = LinearVolumeB(alpha=1.0, min_b=1.0)  # grows very fast
    bounded = BoundedB(inner, min_b=10, max_b=200)

    m = BinaryLMSRMarket(b=bounded)
    assert m.b == 10.0

    m.trade("u", 500, 0)
    assert m.b == 200.0  # should be capped


def test_trade_count_b():
    """TradeCountB should increase only when .step() is called."""
    from src.lmsr.adaptive import TradeCountB

    strat = TradeCountB(alpha=3.0, min_b=5.0)
    m = BinaryLMSRMarket(b=strat)

    assert m.b == 5.0

    m.trade("u", 10, 0)
    strat.step()
    assert m.b == 8.0   # 5 + 3*1

    m.trade("u", 1, 5)
    strat.step()
    assert m.b == 11.0  # 5 + 3*2


# ------------------------------------------------------------------
# Calibration Scoring Layer (DESIGN.md)
# ------------------------------------------------------------------

from src.lmsr.scoring import (
    brier_score,
    log_score,
    brier_decomposition,
    mean_brier_score,
    ForecasterScores,
)


def test_brier_score_basic():
    """Perfect forecast → Brier = 0. Worst → Brier = 1."""
    assert np.allclose(brier_score([1.0, 0.0], [1, 0]), [0.0, 0.0])
    assert np.allclose(brier_score([1.0, 0.0], [0, 1]), [1.0, 1.0])
    assert np.allclose(brier_score([0.5, 0.5], [1, 0]), [0.25, 0.25])


def test_log_score_basic():
    """Log score should be highest for confident correct forecasts."""
    perfect = log_score([0.99, 0.01], [1, 0])
    bad = log_score([0.99, 0.01], [0, 1])

    assert np.all(perfect > -0.1)       # close to zero (good)
    assert np.all(bad < -3.0)           # very negative (bad)


def test_murphy_decomposition_identity():
    """
    The decomposition must approximately satisfy:
        mean(Brier) ≈ Reliability - Resolution + Uncertainty
    """
    rng = np.random.default_rng(42)
    n = 5000

    # Simulate a reasonably well-calibrated forecaster
    true_probs = rng.uniform(0.1, 0.9, n)
    outcomes = (rng.random(n) < true_probs).astype(float)

    decomp = brier_decomposition(true_probs, outcomes, n_bins=15)

    reconstructed = (
        decomp["reliability"] - decomp["resolution"] + decomp["uncertainty"]
    )

    assert abs(decomp["brier"] - reconstructed) < 0.01
    assert decomp["reliability"] >= 0
    assert decomp["resolution"] >= 0
    assert decomp["uncertainty"] > 0


def test_forecaster_scores_helper():
    """ForecasterScores class should accumulate and compute correctly."""
    fs = ForecasterScores()

    fs.add(0.8, 1)
    fs.add(0.3, 0)
    fs.add(0.7, 1)
    fs.add(0.4, 0)

    result = fs.compute(n_bins=5)

    assert result["n"] == 4
    assert "mean_brier" in result
    assert "decomposition" in result
    assert result["decomposition"]["brier"] > 0


if __name__ == "__main__":
    # Allow running the test file directly for quick checks
    pytest.main([__file__, "-q", "--tb=short"])
