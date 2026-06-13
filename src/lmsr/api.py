"""
FastAPI layer for the LMSR simulator.

This provides a clean, stable HTTP API (as recommended in the project plan
and AGENTS.md) so that:

- External bots/agents (RL, Kelly, market-making) can participate remotely
- UIs (beyond Streamlit) can be built on top
- The core `LMSRMarketSimulator` + `TradingAgent` remain the single source of truth

The API is intentionally thin: it wraps the existing Python objects and
preserves all invariants (accounting identity, adaptive b support, etc.).

Run with (after `pip install -e ".[api]"`):

    uvicorn lmsr.api:app --reload

Or via the CLI (once extended):

    lmsr serve

OpenAPI docs at /docs when running.

Models support fixed `b` (float) and simple adaptive strategies via a
lightweight Strategy spec (expandable).

Example client usage (with httpx or requests):

    import httpx
    r = httpx.post("http://localhost:8000/markets", json={"title": "Test", "b": 30})
    market = r.json()
    r = httpx.post(f"/markets/{market['id']}/trades", json={"user_id": "bot1", "shares_yes": 10})
    print(r.json())
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any, Literal

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from .adaptive import BoundedB, LinearVolumeB
from .simulator import LMSRMarketSimulator

# ---------------------------------------------------------------------------
# Pydantic models (request / response)
# ---------------------------------------------------------------------------

class StrategySpec(BaseModel):
    """Lightweight spec for creating markets with adaptive b over HTTP."""
    type: Literal["fixed", "linear", "bounded_linear"] = "fixed"
    value: float | None = Field(None, description="For fixed: the b value")
    alpha: float | None = Field(None, description="Growth rate for linear volume")
    min_b: float = 5.0
    max_b: float = 300.0


class MarketCreate(BaseModel):
    title: str
    description: str = ""
    resolution_criteria: str = ""
    b: float | StrategySpec = 20.0
    fee_rate: float = 0.025
    initial_subsidy: float = 0.0


class TradeRequest(BaseModel):
    user_id: str
    shares_yes: int = 0
    shares_no: int = 0


class ResolveRequest(BaseModel):
    outcome: Literal["yes", "no"]


class ScenarioLoadRequest(BaseModel):
    """Request to load one of the curated demo scenarios (same set as the Streamlit demo)."""
    name: str = Field(..., description="Friendly name from get_available_scenarios(), e.g. 'Long Bot Activity Demo (300 rounds, Open)'")


class MarketResponse(BaseModel):
    id: str
    title: str
    status: str
    current_prices: tuple[float, float]
    current_b: float
    is_adaptive: bool = False
    total_trades: int
    total_fees_earned: float
    fee_rate: float = 0.025
    resolution_outcome: str | None = None
    market_maker_pl: float | None = None
    liquidity_alpha: float | None = None
    liquidity_min_b: float | None = None
    liquidity_max_b: float | None = None


# Global simulator instance (in-memory for now; later can be DB-backed)
_sim: LMSRMarketSimulator | None = None


def get_sim() -> LMSRMarketSimulator:
    if _sim is None:
        raise RuntimeError("Simulator not initialized")
    return _sim


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan to initialize one shared simulator for the demo server.
    Uses SQLite for durable storage instead of pickle.
    """
    global _sim
    # Use a file DB so state survives restarts of the demo server / streamlit.
    # For pure tests you can still do LMSRMarketSimulator(db_path=":memory:")
    _sim = LMSRMarketSimulator(db_path="lmsr_demo.db")
    # Seed only if the DB is empty (first run)
    try:
        if not _sim.list_markets():
            from .adaptive import BoundedB, LinearVolumeB
            from .agent import TradingAgent

            m1 = _sim.create_market("Will revenue beat target? (fixed)", b=45.0)
            agent = TradingAgent(_sim, "demo_bot")
            agent.buy_yes(m1.id, 12)
            agent.buy_no(m1.id, 5)

            adaptive = BoundedB(LinearVolumeB(alpha=0.07, min_b=8), min_b=8, max_b=250)
            _sim.create_market("Will the feature ship? (adaptive)", b=adaptive)
    except Exception:
        pass  # seeding is best-effort for demo
    yield
    _sim = None


app = FastAPI(
    title="LMSR API",
    description="FastAPI wrapper around LMSRMarketSimulator for bots, agents, and UIs.",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS for separate professional frontend (Next.js on :3000 by default)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:3001",  # in case of port conflict
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _market_to_response(market) -> MarketResponse:
    eng = market.engine

    # Compute liquidity strategy details for visibility in admin views
    liquidity_alpha = None
    liquidity_min_b = None
    liquidity_max_b = None
    try:
        if getattr(market, 'is_adaptive_b', False):
            b = getattr(market, 'b', None)
            if b is not None:
                if hasattr(b, "inner"):  # BoundedB wrapper
                    inner = b.inner
                    liquidity_alpha = getattr(inner, "alpha", None)
                    liquidity_min_b = getattr(b, "min_b", None)
                    liquidity_max_b = getattr(b, "max_b", None)
                elif hasattr(b, "alpha"):  # direct LinearVolumeB
                    liquidity_alpha = getattr(b, "alpha", None)
                    liquidity_min_b = getattr(b, "min_b", None)
                    liquidity_max_b = getattr(b, "max_b", None)
    except Exception:
        pass

    mm_pl = None
    if market.status == "resolved":
        # Market maker PnL for resolved markets: revenue collected minus payouts made
        # (initial subsidy is the "capital at risk"; the pl here is the trading result)
        try:
            total_payouts = float(sum(p.amount for p in getattr(market, "payouts", [])))
            mm_pl = float(eng.total_revenue - total_payouts)
        except Exception:
            pass

    return MarketResponse(
        id=market.id,
        title=market.title,
        status=market.status,
        current_prices=eng.price(),
        current_b=market.current_b,
        is_adaptive=getattr(market, 'is_adaptive_b', False),
        total_trades=len(market.trades),
        total_fees_earned=eng.total_fees_earned,
        fee_rate=market.fee_rate,
        resolution_outcome=getattr(market, 'resolution_outcome', None),
        market_maker_pl=mm_pl,
        liquidity_alpha=liquidity_alpha,
        liquidity_min_b=liquidity_min_b,
        liquidity_max_b=liquidity_max_b,
    )




def _parse_b(spec: float | StrategySpec) -> Any:
    """Convert API StrategySpec into a real b value or strategy object."""
    if isinstance(spec, (int, float)):
        return float(spec)
    if spec.type == "fixed":
        return spec.value or 20.0
    if spec.type == "linear":
        return LinearVolumeB(alpha=spec.alpha or 0.05, min_b=spec.min_b)
    if spec.type == "bounded_linear":
        inner = LinearVolumeB(alpha=spec.alpha or 0.05, min_b=spec.min_b)
        return BoundedB(inner, min_b=spec.min_b, max_b=spec.max_b)
    return 20.0


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@app.get("/markets", response_model=list[MarketResponse])
def list_markets(status: str | None = Query(None, description="Filter by status")):
    sim = get_sim()
    markets = sim.list_markets(status)
    return [_market_to_response(m) for m in markets]


@app.post("/markets", response_model=MarketResponse, status_code=201)
def create_market(payload: MarketCreate):
    sim = get_sim()
    b = _parse_b(payload.b)
    market = sim.create_market(
        title=payload.title,
        description=payload.description,
        resolution_criteria=payload.resolution_criteria,
        b=b,
        fee_rate=payload.fee_rate,
        initial_subsidy=payload.initial_subsidy,
    )
    return _market_to_response(market)


@app.get("/markets/{market_id}", response_model=MarketResponse)
def get_market(market_id: str):
    sim = get_sim()
    try:
        market = sim.get_market(market_id)
    except KeyError:
        raise HTTPException(404, f"Market {market_id} not found") from None
    return _market_to_response(market)


@app.post("/markets/{market_id}/trades")
def place_trade(market_id: str, trade: TradeRequest):
    sim = get_sim()
    try:
        result = sim.place_trade(
            market_id, trade.user_id, trade.shares_yes, trade.shares_no
        )
    except Exception as e:  # broad for demo; in prod be more specific
        raise HTTPException(400, str(e)) from None
    if "error" in result:
        raise HTTPException(400, result["error"])
    return result


@app.get("/markets/{market_id}/observe")
def observe(market_id: str, user_id: str = Query(..., description="User / agent id")):
    """Convenient endpoint that returns a rich observation (similar to TradingAgent.observe).

    Includes the three key values: cash_balance, position_value (for this market),
    and total_value (global cash + all positions).
    """
    sim = get_sim()
    try:
        market = sim.get_market(market_id)
    except KeyError:
        raise HTTPException(404, f"Market {market_id} not found") from None

    prices = market.engine.price()
    pos = sim.get_user_position(market_id, user_id)
    pos_value = float(pos[0] * prices[0] + pos[1] * prices[1])
    cash = sim.get_balance(user_id)
    total = sim.get_user_total_value(user_id)
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
        "total_value": total,
        "fee_rate": market.fee_rate,
        "num_trades": len(market.trades),
    }


@app.get("/markets/{market_id}/quote")
def quote_trade(market_id: str, shares_yes: int = 0, shares_no: int = 0):
    """Pure quote (cost estimate) without executing or requiring a user.
    Shares must be integers (no fractional shares).
    """
    sim = get_sim()
    try:
        market = sim.get_market(market_id)
    except KeyError:
        raise HTTPException(404, f"Market {market_id} not found") from None
    effective, raw = market.engine.quote(shares_yes, shares_no)
    impact = market.engine.instantaneous_impact(shares_yes, shares_no)
    slip = market.engine.slippage(shares_yes, shares_no)
    return {
        "effective_cost": effective,
        "raw_cost": raw,
        "fee": effective - raw,
        "price_after": list(impact["price_after"]),
        "impact": list(impact["impact"]),
        "slippage": slip.get("slippage", 0.0),
        "status": market.status,
    }


@app.get("/markets/{market_id}/trades")
def get_market_trades(market_id: str):
    """Return list of trades for the market (for charts etc in the demo).
    Enriched with effective_cost, fee and running mm_profit (cumulative revenue
    minus the marked-to-market value of outstanding shares at post-trade prices).
    The mm_profit series is what powers the admin MM P/L track under the price chart.
    """
    sim = get_sim()
    try:
        market = sim.get_market(market_id)
    except KeyError:
        raise HTTPException(404, f"Market {market_id} not found") from None
    return _enrich_market_trades(market)


def _enrich_market_trades(market) -> list[dict]:
    """Compute running market-maker P/L after each trade for charting.
    mm_profit_after = cumulative_revenue - (p_yes * q_yes + p_no * q_no)
    This gives a live marked P/L for the house (useful for open markets in admin).
    """
    out: list[dict] = []
    revenue = 0.0
    for t in market.trades:
        revenue += float(getattr(t, "effective_cost", 0.0) or 0.0)
        qy = qn = 0.0
        try:
            qa = getattr(t, "market_q_after", None)
            if qa is not None and len(qa) == 2:
                qy, qn = float(qa[0]), float(qa[1])
        except Exception:
            pass
        py = float(getattr(t, "price_after_yes", 0.5) or 0.5)
        pn = float(getattr(t, "price_after_no", 0.5) or 0.5)
        marked = py * qy + pn * qn
        mm_profit = revenue - marked
        out.append({
            "id": getattr(t, "id", None),
            "user_id": t.user_id,
            "shares_yes": t.shares_yes,
            "shares_no": t.shares_no,
            "effective_cost": getattr(t, "effective_cost", None),
            "fee": getattr(t, "fee", None),
            "price_after_yes": t.price_after_yes,
            "price_after_no": t.price_after_no,
            "mm_profit": round(mm_profit, 6),
        })
    return out


@app.get("/users/{user_id}/portfolio")
def get_portfolio(user_id: str):
    sim = get_sim()
    try:
        return sim.get_user_portfolio(user_id)
    except Exception as e:
        raise HTTPException(404, str(e)) from None


@app.get("/users/{user_id}/balance")
def get_balance(user_id: str):
    sim = get_sim()
    return {"user_id": user_id, "balance": sim.get_balance(user_id)}


@app.get("/users/{user_id}/account")
def get_account(user_id: str):
    """Canonical 'three values' summary for a user: cash, open position MTM, and total account value.

    This is the recommended way for UIs and clients to show the always-visible
    account overview (cash balance, position value, total equity).
    """
    sim = get_sim()
    try:
        cash = sim.get_balance(user_id)
        pos_val = sim.get_user_position_value(user_id)
        return {
            "user_id": user_id,
            "cash_balance": cash,
            "position_value": pos_val,
            "total_value": cash + pos_val,
        }
    except Exception as e:
        raise HTTPException(404, str(e)) from None


@app.post("/markets/{market_id}/resolve")
def resolve_market(market_id: str, payload: ResolveRequest):
    sim = get_sim()
    try:
        result = sim.resolve_market(market_id, payload.outcome)
    except Exception as e:
        raise HTTPException(400, str(e)) from None
    return result


@app.get("/leaderboard")
def get_leaderboard(metric: str = "brier", min_resolved_trades: int = 1):
    sim = get_sim()
    return sim.get_leaderboard(metric=metric, min_resolved_trades=min_resolved_trades)


@app.get("/summary")
def summary():
    sim = get_sim()
    return sim.summary()


@app.post("/reset")
def reset_simulator():
    """Full reset (for the demo 'Reset Simulator' button).
    Uses the simulator's reset() which also clears the underlying DB when present.
    """
    global _sim
    if _sim is not None:
        _sim.reset()
    else:
        _sim = LMSRMarketSimulator(db_path="lmsr_demo.db")
    return {"success": True}


@app.post("/markets/{market_id}/set_strategy")
def set_b_strategy(market_id: str, strategy: StrategySpec):
    """Update the b / liquidity strategy on a market (used by the b-recommendation UI)."""
    sim = get_sim()
    try:
        market = sim.get_market(market_id)
    except KeyError:
        raise HTTPException(404, f"Market {market_id} not found") from None

    new_b = _parse_b(strategy)
    # We mutate the engine's strategy (the same pattern the old UI used via market.engine.set_b_strategy)
    market.engine.set_b_strategy(new_b)
    # Also update the stored b on the Market dataclass for consistency with current_b property
    # (for fixed it will be the number; for adaptive it will be the strategy object)
    market.b = new_b
    return {"success": True, "current_b": market.current_b, "is_adaptive": market.is_adaptive_b}


# ---------------------------------------------------------------------------
# Admin endpoints (for the separate professional backend UI)
# See all activity, global views, resolve any market. User-level views remain
# available via the existing per-user endpoints (get_portfolio, get_account, observe, etc.).
# The frontend can switch "current user" to see exactly what that user sees.
# ---------------------------------------------------------------------------

@app.get("/admin/users")
def admin_list_users():
    """List all users with current balances and basic portfolio summary.
    Allows the admin UI to see everyone.
    """
    sim = get_sim()
    result = []
    for user_id in list(sim.users.keys()):
        try:
            balance = sim.get_balance(user_id)
            port = sim.get_user_portfolio(user_id)
            result.append({
                "user_id": user_id,
                "balance": balance,
                "open_markets": port.open_markets_count,
                "resolved_markets": port.resolved_markets_count,
                "realized_pnl": port.realized_pnl,
            })
        except Exception:
            result.append({"user_id": user_id, "balance": balance, "error": "could not load portfolio"})
    return result


@app.get("/admin/markets")
def admin_list_markets():
    """Full list of all markets with details (including market_maker_pl for resolved,
    and liquidity strategy params for adaptive b markets). For admin overview.
    Use /admin/markets/{id} for a single market's admin details."""
    sim = get_sim()
    return [_market_to_response(m) for m in sim.list_markets(status=None)]


@app.get("/admin/markets/{market_id}")
def admin_get_market(market_id: str):
    """Detailed view of a single market, including admin-only fields like
    market_maker_pl (for resolved markets) and full liquidity config.
    This powers the per-market admin view in the professional frontend."""
    sim = get_sim()
    try:
        market = sim.get_market(market_id)
    except KeyError:
        raise HTTPException(404, f"Market {market_id} not found") from None
    return _market_to_response(market)


@app.get("/admin/activity")
def admin_activity(limit: int = 200):
    """All (or recent) trade activity across all markets. For seeing everything."""
    sim = get_sim()
    all_trades = []
    for m in sim.list_markets(status=None):
        for t in m.trades:
            all_trades.append({
                "id": t.id,
                "market_id": m.id,
                "market_title": m.title,
                "user_id": t.user_id,
                "shares_yes": t.shares_yes,
                "shares_no": t.shares_no,
                "effective_cost": t.effective_cost,
                "fee": t.fee,
                "price_after_yes": t.price_after_yes,
                "price_after_no": t.price_after_no,
                "timestamp": t.timestamp.isoformat() if hasattr(t, "timestamp") else None,
            })
    # Most recent first
    all_trades.sort(key=lambda x: x.get("timestamp") or "", reverse=True)
    return all_trades[:limit]


@app.post("/admin/markets/{market_id}/resolve")
def admin_resolve_market(market_id: str, payload: ResolveRequest):
    """Admin-only resolve endpoint. Allows resolving any market."""
    sim = get_sim()
    try:
        result = sim.resolve_market(market_id, payload.outcome)
    except Exception as e:
        raise HTTPException(400, str(e)) from None
    return result


@app.get("/admin/scenarios")
def list_scenarios():
    """List all curated demo scenarios that can be loaded (same registry as the Streamlit app).
    These match the 'Quick Demo Scenarios' available in app.py.
    """
    import sys
    from pathlib import Path

    # Ensure the project root is importable so "import examples" works
    # when running via `lmsr serve` / uvicorn from an installed package.
    here = Path(__file__).resolve()
    project_root = here.parents[2]  # .../src/lmsr/api.py -> src -> project root
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))

    try:
        from examples.demo_seeding import get_available_scenarios
        return {"scenarios": get_available_scenarios()}
    except Exception as e:
        # Return empty list + error so the UI can show a useful message
        # instead of a 500 that would be swallowed.
        return {"scenarios": [], "error": f"Could not load scenarios: {e}"}


@app.post("/admin/scenarios/load")
def load_scenario(payload: ScenarioLoadRequest):
    """Load (and replace current state with) one of the curated demo scenarios.
    This resets the simulator/DB first, then runs the seeder exactly like the
    Streamlit "Quick Demo Scenarios" buttons do. All the demos from demo_seeding.py
    become available in the professional UI.
    """
    import sys
    from pathlib import Path

    here = Path(__file__).resolve()
    project_root = here.parents[2]
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))

    sim = get_sim()
    try:
        from examples.demo_seeding import run_scenario, get_available_scenarios
        available = get_available_scenarios()
        if payload.name not in available:
            raise HTTPException(400, f"Unknown scenario. Available: {available}")
        # Reset clears all state + the underlying SQLite DB (see simulator.reset + api /reset)
        sim.reset()
        try:
            result = run_scenario(sim, payload.name)
            return {
                "success": True,
                "scenario": payload.name,
                "result": result,
                "message": f"Loaded scenario '{payload.name}'. State replaced.",
            }
        except Exception:
            # Clean up any partial state from a failed mid-load (e.g. partial trades
            # for a long history like Experts vs Punters). Leaves the simulator
            # in a clean state for the next attempt.
            sim.reset()
            raise
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(400, f"Failed to load scenario '{payload.name}': {e}") from None


# ---------------------------------------------------------------------------
# Convenience runner (for `python -m lmsr.api` or uvicorn)
# ---------------------------------------------------------------------------

def run(host: str = "0.0.0.0", port: int = 8000, reload: bool = False):
    """Run the API server (requires uvicorn)."""
    import uvicorn

    uvicorn.run("lmsr.api:app", host=host, port=port, reload=reload)


if __name__ == "__main__":
    run()
