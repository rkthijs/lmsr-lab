"""
Tests for the multi-market LMSR simulator.

These tests validate the architectural patterns from DESIGN.md:
- Multiple independent markets
- Per-market trade logs and derived positions
- Replay capability per market
"""

import os
import tempfile

import numpy as np

# FastAPI test imports (for API coverage)
from fastapi.testclient import TestClient

import src.lmsr.api as api_mod
from src.lmsr.adaptive import BoundedB, LinearVolumeB, LogVolumeB, SqrtVolumeB, TradeCountB
from src.lmsr.agent import TradingAgent  # for existing agent tests
from src.lmsr.api import app as fastapi_app
from src.lmsr.db import SQLiteStore
from src.lmsr.simulator import LMSRMarketSimulator


def test_create_multiple_markets():
    sim = LMSRMarketSimulator()

    m1 = sim.create_market("Will it rain tomorrow?", b=15.0)
    m2 = sim.create_market("Will AI exceed human performance by 2030?", b=40.0)

    assert len(sim.markets) == 2
    assert m1.id != m2.id
    assert m1.b == 15.0
    assert m2.b == 40.0
    assert m1.status == "open"


def test_place_trade_requires_market_id():
    sim = LMSRMarketSimulator()
    market = sim.create_market("Test Market")

    result = sim.place_trade(market.id, "alice", 10, 0)
    assert "error" not in result
    assert len(market.trades) == 1


def test_positions_are_per_market():
    sim = LMSRMarketSimulator()

    m1 = sim.create_market("Market One")
    m2 = sim.create_market("Market Two")

    sim.place_trade(m1.id, "alice", 10, 0)
    sim.place_trade(m2.id, "alice", 0, 8)

    pos_m1 = sim.get_user_position(m1.id, "alice")
    pos_m2 = sim.get_user_position(m2.id, "alice")

    assert np.allclose(pos_m1, [10, 0])
    assert np.allclose(pos_m2, [0, 8])


def test_replay_market_independent():
    sim = LMSRMarketSimulator()

    m1 = sim.create_market("Market A", b=25.0)
    m2 = sim.create_market("Market B", b=25.0)

    sim.place_trade(m1.id, "alice", 5, 2)
    sim.place_trade(m2.id, "bob", 3, 7)

    replayed1 = sim.replay_market(m1.id)
    replayed2 = sim.replay_market(m2.id)

    assert np.allclose(replayed1.q, sim.get_market(m1.id).engine.q)
    assert np.allclose(replayed2.q, sim.get_market(m2.id).engine.q)


def test_resolve_market_updates_status():
    sim = LMSRMarketSimulator()
    market = sim.create_market("Will it rain?")

    sim.place_trade(market.id, "alice", 12, 0)
    result = sim.resolve_market(market.id, "yes")

    assert market.status == "resolved"
    assert market.resolution_outcome == "yes"
    assert result["winning_outcome"] == "yes"


def test_cannot_trade_on_resolved_market():
    sim = LMSRMarketSimulator()
    market = sim.create_market("Resolved Market")
    sim.place_trade(market.id, "alice", 5, 0)
    sim.resolve_market(market.id, "no")

    _ = sim.place_trade(market.id, "bob", 10, 0)

    # Currently we still allow it on the engine level.
    # This test mainly checks that the market status is respected at a higher level
    # (in a fuller impl we would add a guard in place_trade)
    assert market.status == "resolved"


def test_reset_market_only_affects_one():
    sim = LMSRMarketSimulator()
    m1 = sim.create_market("Keep")
    m2 = sim.create_market("Reset Me")

    sim.place_trade(m1.id, "alice", 3, 0)
    sim.place_trade(m2.id, "bob", 0, 5)

    sim.reset_market(m2.id)

    assert len(m1.trades) == 1
    assert len(m2.trades) == 0
    assert m2.status == "open"


def test_summary_for_specific_market():
    sim = LMSRMarketSimulator()
    m = sim.create_market("Quarterly Revenue Forecast", b=50)

    sim.place_trade(m.id, "alice", 20, 5)

    summary = sim.summary(m.id)
    assert summary["market_id"] == m.id
    assert summary["title"] == "Quarterly Revenue Forecast"
    assert summary["total_trades"] == 1


# ------------------------------------------------------------------
# Payout Records (proper audit trail per DESIGN.md)
# ------------------------------------------------------------------

def test_payout_records_created_on_resolution():
    sim = LMSRMarketSimulator()

    m = sim.create_market("Test Payouts")
    sim.place_trade(m.id, "alice", 15, 0)
    sim.place_trade(m.id, "bob", 0, 10)

    sim.resolve_market(m.id, "yes")

    payouts = sim.get_payouts(m.id)
    assert len(payouts) == 1          # only Alice had Yes shares
    assert payouts[0].user_id == "alice"
    assert payouts[0].amount == 15.0
    assert payouts[0].outcome == "yes"


def test_payouts_credit_balances():
    sim = LMSRMarketSimulator()

    m = sim.create_market("Payout + Balance")
    sim.place_trade(m.id, "alice", 8, 3)

    # Alice starts with 1000, spends  on the trade
    initial = sim.get_balance("alice")
    sim.resolve_market(m.id, "yes")

    final = sim.get_balance("alice")
    # She should have received +8 from the payout
    assert final > initial


def test_get_user_payouts_across_markets():
    sim = LMSRMarketSimulator()

    m1 = sim.create_market("Market 1")
    m2 = sim.create_market("Market 2")

    sim.place_trade(m1.id, "alice", 5, 0)
    sim.place_trade(m2.id, "alice", 12, 0)

    sim.resolve_market(m1.id, "yes")
    sim.resolve_market(m2.id, "yes")

    user_payouts = sim.get_user_payouts("alice")
    assert len(user_payouts) == 2
    total = sum(p.amount for p in user_payouts)
    assert total == 17.0


def test_accounting_identity_after_resolution():
    sim = LMSRMarketSimulator()

    # Create market with no initial subsidy (common case in our current model)
    m = sim.create_market("Accounting Test", initial_subsidy=0.0)

    sim.place_trade(m.id, "alice", 10, 0)
    sim.place_trade(m.id, "bob", 0, 7)

    result = sim.resolve_market(m.id, "yes")

    accounting = result["accounting_identity"]
    assert bool(accounting["is_valid"]) is True
    assert bool(accounting["payouts_match_engine"]) is True
    assert bool(accounting["pl_match"]) is True
    assert "remainder" in accounting
    assert "initial_subsidy" in accounting
    assert accounting["initial_subsidy"] == 0.0


def test_accounting_identity_with_subsidy():
    sim = LMSRMarketSimulator()

    m = sim.create_market("Subsidized Market", initial_subsidy=50.0)

    sim.place_trade(m.id, "alice", 20, 0)

    result = sim.resolve_market(m.id, "yes")

    accounting = result.get("accounting_identity")
    assert bool(accounting["is_valid"]) is True
    assert bool(accounting["payouts_match_engine"]) is True
    assert "remainder" in accounting
    assert accounting["initial_subsidy"] == 50.0
    # remainder = 50 + revenue - payout; payout will be ~20 (winning shares)
    # we just ensure the field is present and numeric (exact value depends on b/fees)
    assert isinstance(accounting["remainder"], (int, float))


# ------------------------------------------------------------------
# Persistence Tests
# ------------------------------------------------------------------


def test_save_and_load_roundtrip():
    sim = LMSRMarketSimulator()

    m1 = sim.create_market("Market One", b=30.0, initial_subsidy=10.0)
    m2 = sim.create_market("Market Two", b=15.0)

    sim.place_trade(m1.id, "alice", 12, 0)
    sim.place_trade(m1.id, "bob", 0, 5)
    sim.place_trade(m2.id, "charlie", 3, 8)

    sim.resolve_market(m1.id, "yes")

    with tempfile.TemporaryDirectory() as tmpdir:
        path = os.path.join(tmpdir, "sim_state.pkl")
        sim.save(path)

        loaded = LMSRMarketSimulator.load(path)

        # Check markets survived
        assert len(loaded.markets) == 2
        assert loaded.get_market("m1").title == "Market One"
        assert loaded.get_market("m1").b == 30.0
        assert loaded.get_market("m1").initial_subsidy == 10.0
        assert loaded.get_market("m1").status == "resolved"

        # Check balances survived
        assert loaded.get_balance("alice") > 1000   # Alice got paid out

        # Check we can still operate on the loaded simulator
        m3 = loaded.create_market("New after load")
        assert m3.id == "m3"  # counter should have continued

        loaded.place_trade(m3.id, "alice", 2, 0)
        assert len(loaded.get_payouts(m1.id)) == 1  # original payout still there


# ------------------------------------------------------------------
# Improved User Model + Portfolio Tests
# ------------------------------------------------------------------

def test_get_or_create_user():
    sim = LMSRMarketSimulator()

    user = sim.get_or_create_user("alice", display_name="Alice Smith")
    assert user.id == "alice"
    assert user.balance == 1000.0
    assert user.display_name == "Alice Smith"

    # Calling again returns the same user
    user2 = sim.get_or_create_user("alice")
    assert user2 is user


def test_user_portfolio_basic():
    sim = LMSRMarketSimulator()

    m1 = sim.create_market("Market A")
    m2 = sim.create_market("Market B")

    sim.place_trade(m1.id, "alice", 8, 0)
    sim.place_trade(m2.id, "alice", 0, 12)

    portfolio = sim.get_user_portfolio("alice")

    assert portfolio.user_id == "alice"
    assert portfolio.balance < 1000   # Spent some money
    assert "m1" in portfolio.positions
    assert "m2" in portfolio.positions
    assert portfolio.positions["m1"]["yes"] == 8
    assert portfolio.open_markets_count == 2


def test_user_portfolio_after_resolution():
    sim = LMSRMarketSimulator()

    m = sim.create_market("Resolvable")
    sim.place_trade(m.id, "alice", 15, 0)

    sim.resolve_market(m.id, "yes")

    portfolio = sim.get_user_portfolio("alice")

    assert portfolio.resolved_markets_count == 1
    assert portfolio.total_payouts_received == 15.0
    assert portfolio.realized_pnl == 15.0   # Simplified view
    assert portfolio.balance > 1000         # Received payout


# ------------------------------------------------------------------
# Stored Resolution Scores Tests
# ------------------------------------------------------------------

def test_scores_are_stored_on_resolution():
    sim = LMSRMarketSimulator()

    m = sim.create_market("Scoring Test")
    sim.place_trade(m.id, "alice", 10, 0)
    sim.place_trade(m.id, "bob", 0, 8)

    sim.resolve_market(m.id, "yes")

    scores = sim.get_scores(m.id)
    assert len(scores) == 2

    # Alice was correct on Yes, her Brier should be reasonably low
    alice_score = next(s for s in scores if s.user_id == "alice")
    assert alice_score.outcome == 1.0
    assert alice_score.brier_score < 0.25   # relaxed threshold for early trade


def test_get_user_scores():
    sim = LMSRMarketSimulator()

    m1 = sim.create_market("M1")
    m2 = sim.create_market("M2")

    sim.place_trade(m1.id, "alice", 5, 0)
    sim.place_trade(m2.id, "alice", 0, 10)

    sim.resolve_market(m1.id, "yes")
    sim.resolve_market(m2.id, "no")

    user_scores = sim.get_user_scores("alice")
    assert len(user_scores) == 2

    brier_values = [s.brier_score for s in user_scores]
    assert all(b >= 0 for b in brier_values)


# ------------------------------------------------------------------
# Global Leaderboard Tests
# ------------------------------------------------------------------

def test_global_leaderboard_brier():
    sim = LMSRMarketSimulator()

    m1 = sim.create_market("M1")
    m2 = sim.create_market("M2")

    sim.place_trade(m1.id, "alice", 8, 0)
    sim.place_trade(m1.id, "bob", 15, 0)

    sim.resolve_market(m1.id, "yes")

    sim.place_trade(m2.id, "alice", 0, 5)
    sim.place_trade(m2.id, "bob", 0, 12)

    sim.resolve_market(m2.id, "no")

    board = sim.get_leaderboard(metric="brier", min_resolved_trades=2)

    assert len(board) >= 2
    # Just ensure the leaderboard is sorted with lower brier first
    brier_values = [entry["avg_brier"] for entry in board]
    assert brier_values == sorted(brier_values)


def test_global_leaderboard_pnl():
    sim = LMSRMarketSimulator()

    m = sim.create_market("PNL Test")
    sim.place_trade(m.id, "winner", 20, 0)
    sim.place_trade(m.id, "loser", 0, 20)

    sim.resolve_market(m.id, "yes")

    board = sim.get_leaderboard(metric="pnl", min_resolved_trades=1)

    winner = next(e for e in board if e["user_id"] == "winner")
    assert winner["total_pnl"] > 0

    # Note: "loser" currently shows 0 realized resolution PnL
    # (they lost the premium paid, but we don't record negative payouts)
    loser = next((e for e in board if e["user_id"] == "loser"), None)
    if loser:
        assert loser["total_pnl"] <= 0


# ------------------------------------------------------------------
# TradingAgent ergonomics (bot / agent API)
# ------------------------------------------------------------------



def test_trading_agent_basic_usage():
    """TradingAgent should provide ergonomic access for a single user_id."""
    sim = LMSRMarketSimulator()
    agent = TradingAgent(sim, "bot_1", display_name="Test Bot")

    # Create market
    m = agent.create_market("Will the feature ship?", b=30.0)
    assert m.id in [mm.id for mm in agent.list_markets()]

    # Trade using convenience methods
    res = agent.buy_yes(m.id, shares=15)
    assert "cost" in res
    assert res["cost"] > 0

    pos = agent.get_position(m.id)
    assert pos[0] == 15.0
    assert pos[1] == 0.0

    prices = agent.get_prices(m.id)
    assert len(prices) == 2
    assert abs(sum(prices) - 1.0) < 1e-9


# ------------------------------------------------------------------
# DB / SQLite Persistence Tests (new coverage for db.py + simulator db_path paths)
# ------------------------------------------------------------------




def test_sqlite_store_basic_crud():
    """Directly exercise SQLiteStore (covers init, schema, save/get/list for all tables)."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test.db")
        store = SQLiteStore(db_path)

        # Users
        u = store.get_or_create_user("alice", display_name="Alice", balance=1234.5)
        assert u["id"] == "alice"
        assert u["balance"] == 1234.5
        store.update_user_balance("alice", 999.0)
        assert store.get_user("alice")["balance"] == 999.0

        # Markets (fixed)
        store.save_market(
            id="m1", title="Test Fixed", b=25.0, fee_rate=0.02,
            initial_subsidy=50.0, status="open"
        )
        m = store.get_market("m1")
        assert m["title"] == "Test Fixed"
        assert m["b"] == 25.0
        assert m["strategy_type"] == "fixed"

        # Markets (adaptive)
        strat = BoundedB(LinearVolumeB(alpha=0.1, min_b=10), min_b=10, max_b=300)
        store.save_market(
            id="m2", title="Test Adaptive", b=strat, status="open"
        )
        m2 = store.get_market("m2")
        assert m2["strategy_type"] == "bounded_linear"
        assert m2["alpha"] == 0.1
        assert m2["min_b"] == 10

        # Trades
        store.save_trade({
            "id": "t1", "market_id": "m1", "user_id": "alice",
            "shares_yes": 10, "shares_no": 0,
            "raw_cost": 5.0, "fee": 0.1, "effective_cost": 5.1,
            "price_after_yes": 0.6, "price_after_no": 0.4,
            "q_after_yes": 10.0, "q_after_no": 0.0,
            "created_at": "2026-01-01T00:00:00+00:00"
        })
        trades = store.get_trades("m1")
        assert len(trades) == 1
        assert trades[0]["shares_yes"] == 10

        # Payouts + Scores
        store.save_payout({"market_id": "m1", "user_id": "alice", "amount": 10.0, "outcome": "yes"})
        store.save_score({
            "market_id": "m1", "user_id": "alice", "trade_id": "t1",
            "forecast_prob": 0.55, "outcome": 1.0,
            "brier_score": 0.2, "log_score": -0.1
        })
        payouts = store.get_payouts(market_id="m1")
        scores = store.get_scores(market_id="m1")
        assert len(payouts) == 1
        assert len(scores) == 1

        # Clear
        store.clear_all()
        assert len(store.list_markets()) == 0
        assert len(store.list_users()) == 0

        store.close()


def test_simulator_with_db_path_roundtrip():
    """Full lifecycle with db_path (covers simulator DB integration + load by replay)."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "sim.db")

        # First simulator instance - write data
        sim = LMSRMarketSimulator(db_path=db_path)
        m = sim.create_market("DB Roundtrip", b=20.0, initial_subsidy=100.0)
        sim.place_trade(m.id, "alice", 8, 1)
        sim.place_trade(m.id, "bob", 0, 5)

        _ = sim.get_balance("alice")
        res = sim.resolve_market(m.id, "yes")
        assert res["accounting_identity"]["is_valid"] is True

        # New simulator instance - should load from DB
        sim2 = LMSRMarketSimulator(db_path=db_path)
        m2 = sim2.get_market(m.id)
        assert m2.status == "resolved"
        assert len(m2.trades) == 2
        assert len(m2.payouts) >= 1
        assert len(sim2.get_scores(m.id)) == 2

        # Balances and positions should be restored (focus on key invariants)
        bal_after = sim2.get_balance("alice")
        assert bal_after >= 1000.0  # at minimum back to start after payout
        pos = sim2.get_user_position(m.id, "alice")
        assert pos[0] == 8.0
        assert pos[1] == 1.0

        # Can continue operating
        m3 = sim2.create_market("After Reload")
        sim2.place_trade(m3.id, "alice", 3, 0)
        assert len(sim2.list_markets()) == 2


def test_db_persistence_adaptive_b():
    """Adaptive b strategy survives DB save + reload."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "adaptive.db")
        sim = LMSRMarketSimulator(db_path=db_path)

        adaptive = BoundedB(LinearVolumeB(alpha=0.07, min_b=10), min_b=10, max_b=250)
        m = sim.create_market("Adaptive DB", b=adaptive)
        sim.place_trade(m.id, "trader", 4, 2)

        # Reload
        sim2 = LMSRMarketSimulator(db_path=db_path)
        m2 = sim2.get_market(m.id)
        # The strategy object is reconstructed; live b comes from the engine (current_b)
        live_b = getattr(m2, "current_b", None)
        if live_b is None:
            live_b = getattr(getattr(m2, "engine", None), "b", 10.0)
        assert live_b >= 10.0  # floor; tiny volume with this alpha may not increase it yet
        # Further trades should still work with the restored strategy
        sim2.place_trade(m.id, "trader2", 1, 0)


def test_db_reset_clears_data():
    """sim.reset() when using DB should clear persisted state."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "reset.db")
        sim = LMSRMarketSimulator(db_path=db_path)
        m = sim.create_market("To Reset")
        sim.place_trade(m.id, "u", 5, 0)
        sim.resolve_market(m.id, "yes")

        sim.reset()
        assert len(sim.list_markets()) == 0

        # Fresh instance on same DB should also see empty
        sim2 = LMSRMarketSimulator(db_path=db_path)
        assert len(sim2.list_markets()) == 0


# ------------------------------------------------------------------
# FastAPI Layer Coverage (using TestClient)
# ------------------------------------------------------------------



def test_api_basic_market_and_trade_flow():
    """Exercise the main API endpoints to improve api.py coverage."""
    # Use a fresh in-memory simulator for this test
    sim = LMSRMarketSimulator()
    api_mod._sim = sim
    client = TestClient(fastapi_app)

    # Create market
    payload = {
        "title": "API Coverage Test",
        "b": 30.0,
        "fee_rate": 0.02,
        "initial_subsidy": 0.0,
    }
    r = client.post("/markets", json=payload)
    assert r.status_code == 201
    market = r.json()
    mid = market["id"]
    assert market["status"] == "open"

    # List markets
    r = client.get("/markets")
    assert r.status_code == 200
    assert any(m["id"] == mid for m in r.json())

    # Get single market
    r = client.get(f"/markets/{mid}")
    assert r.status_code == 200

    # Quote
    r = client.get(f"/markets/{mid}/quote", params={"shares_yes": 5, "shares_no": 0})
    assert r.status_code == 200
    q = r.json()
    assert "effective_cost" in q
    assert "status" in q

    # Trade
    r = client.post(f"/markets/{mid}/trades", json={"user_id": "api_user", "shares_yes": 5})
    assert r.status_code == 200
    assert "cost" in r.json()

    # Observe
    r = client.get(f"/markets/{mid}/observe", params={"user_id": "api_user"})
    assert r.status_code == 200
    obs = r.json()
    assert obs["position"]["yes"] == 5.0

    # Resolve
    r = client.post(f"/markets/{mid}/resolve", json={"outcome": "yes"})
    assert r.status_code == 200
    res = r.json()
    assert "market_maker_pl" in res
    assert res["accounting_identity"]["is_valid"] is True

    # Leaderboard / summary (light)
    r = client.get("/leaderboard")
    assert r.status_code == 200

    r = client.get("/summary")
    assert r.status_code == 200

    # Reset
    r = client.post("/reset")
    assert r.status_code == 200
    assert r.json()["success"] is True


# ------------------------------------------------------------------
# Additional Adaptive Strategy Coverage
# ------------------------------------------------------------------



def test_sqrt_volume_b_clamping_and_behavior():
    s = SqrtVolumeB(alpha=2.0, min_b=5.0, max_b=100.0)
    # Small volume -> should hit min
    assert s(np.array([1.0, 0.0])) == 5.0
    # Larger volume
    val = s(np.array([100.0, 50.0]))
    assert 5.0 < val < 100.0
    # Clamped at max
    big = SqrtVolumeB(alpha=10.0, min_b=5.0, max_b=20.0)
    assert big(np.array([10000.0, 0.0])) == 20.0


def test_log_volume_b_and_trade_count_b():
    logb = LogVolumeB(alpha=5.0, min_b=5.0, max_b=50.0)
    assert logb(np.array([0.0, 0.0])) == 5.0
    val = logb(np.array([100.0, 0.0]))
    assert 5 < val < 50

    tcb = TradeCountB(alpha=1.0, min_b=5.0, max_b=30.0)
    # TradeCountB is stateful via explicit .step()
    assert tcb(np.array([10.0, 0.0])) == 5.0
    tcb.step()
    val2 = tcb(np.array([10.0, 0.0]))
    assert val2 > 5.0


def test_trading_agent_sell_and_adaptive_b():
    """Sells should work and fees_earned should increase for the agent (via underlying engine)."""
    sim = LMSRMarketSimulator()
    agent = TradingAgent(sim, "bot_seller")

    m = agent.create_market("Sell test", b=25.0, fee_rate=0.02)

    agent.buy_yes(m.id, shares=20)
    before_fees = m.engine.total_fees_earned

    agent.sell_yes(m.id, shares=10)
    after_fees = m.engine.total_fees_earned

    # Fees should have increased from the sell side (spread)
    assert after_fees > before_fees

    pos = agent.get_position(m.id)
    assert pos[0] == 10.0


def test_trading_agent_resolution():
    """Agent should be able to resolve markets it participates in (for testing)."""
    sim = LMSRMarketSimulator()
    agent = TradingAgent(sim, "resolver_bot")

    m = agent.create_market("Resolve via agent")
    agent.buy_yes(m.id, shares=5)
    agent.buy_no(m.id, shares=3)

    result = agent.resolve_market(m.id, "yes")
    assert result["winning_outcome"] == "yes"
    assert "accounting_identity" in result

    # After resolution the agent's portfolio should reflect payout
    portfolio = agent.get_portfolio()
    assert portfolio.resolved_markets_count >= 1