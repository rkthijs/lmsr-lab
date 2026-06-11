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
    fee_rate: float = 0.02
    initial_subsidy: float = 0.0


class TradeRequest(BaseModel):
    user_id: str
    shares_yes: float = 0.0
    shares_no: float = 0.0


class ResolveRequest(BaseModel):
    outcome: Literal["yes", "no"]


class MarketResponse(BaseModel):
    id: str
    title: str
    status: str
    current_prices: tuple[float, float]
    current_b: float
    is_adaptive: bool
    total_trades: int
    total_fees_earned: float
    fee_rate: float = 0.02


# Global simulator instance (in-memory for now; later can be DB-backed)
_sim: LMSRMarketSimulator | None = None


def get_sim() -> LMSRMarketSimulator:
    if _sim is None:
        raise RuntimeError("Simulator not initialized")
    return _sim


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan to initialize one shared simulator for the demo server."""
    global _sim
    _sim = LMSRMarketSimulator()
    # Seed a couple of demo markets so the API is immediately useful
    try:
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


def _market_to_response(market) -> MarketResponse:
    eng = market.engine
    return MarketResponse(
        id=market.id,
        title=market.title,
        status=market.status,
        current_prices=eng.price(),
        current_b=market.current_b,
        is_adaptive=market.is_adaptive_b,
        total_trades=len(market.trades),
        total_fees_earned=eng.total_fees_earned,
        fee_rate=market.fee_rate,
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
    """Convenient endpoint that returns a rich observation (similar to TradingAgent.observe)."""
    sim = get_sim()
    try:
        market = sim.get_market(market_id)
    except KeyError:
        raise HTTPException(404, f"Market {market_id} not found") from None

    prices = market.engine.price()
    pos = sim.get_user_position(market_id, user_id)
    return {
        "market_id": market_id,
        "status": market.status,
        "prices": prices,
        "current_b": market.current_b,
        "is_adaptive": market.is_adaptive_b,
        "position": {
            "yes": float(pos[0]),
            "no": float(pos[1]),
            "total": float(pos[0] + pos[1]),
        },
        "balance": sim.get_balance(user_id),
        "fee_rate": market.fee_rate,
        "num_trades": len(market.trades),
    }


@app.get("/markets/{market_id}/quote")
def quote_trade(market_id: str, shares_yes: float = 0.0, shares_no: float = 0.0):
    """Pure quote (cost estimate) without executing or requiring a user."""
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
    """Return list of trades for the market (for charts etc in the demo)."""
    sim = get_sim()
    try:
        market = sim.get_market(market_id)
    except KeyError:
        raise HTTPException(404, f"Market {market_id} not found") from None
    return [
        {
            "id": t.id,
            "user_id": t.user_id,
            "shares_yes": t.shares_yes,
            "shares_no": t.shares_no,
            "price_after_yes": t.price_after_yes,
            "price_after_no": t.price_after_no,
        }
        for t in market.trades
    ]


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
    """Full reset (for the demo 'Reset Simulator' button)."""
    global _sim
    _sim = LMSRMarketSimulator()
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
# Convenience runner (for `python -m lmsr.api` or uvicorn)
# ---------------------------------------------------------------------------

def run(host: str = "0.0.0.0", port: int = 8000, reload: bool = False):
    """Run the API server (requires uvicorn)."""
    import uvicorn

    uvicorn.run("lmsr.api:app", host=host, port=port, reload=reload)


if __name__ == "__main__":
    run()
