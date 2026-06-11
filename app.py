import sys
from pathlib import Path

import streamlit as st

# Ensure "from examples.*" and "from src.lmsr" imports work reliably regardless
# of the current working directory when the user runs `streamlit run app.py`.
# This fixes the fragile packaging / import bug for the Streamlit demo.
_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

from examples.demo_seeding import (  # noqa: E402
    get_available_scenarios,
    load_history_into_simulator,
    run_scenario,
)
from examples.replay_history import load_history, replay_history  # noqa: E402
from src.lmsr.adaptive import BoundedB, LinearVolumeB  # noqa: E402
from src.lmsr.simulator import (
    LMSRMarketSimulator as _DirectSimulator,  # only used for complex demo seeding
)

# The Streamlit demo now exclusively uses the FastAPI layer (in-process for a single-command demo).
# You need the api extra for this to work: pip install -e ".[demo,api]"
try:
    from fastapi.testclient import TestClient

    from src.lmsr.api import app as fastapi_app
    _HAS_FASTAPI = True
except ImportError:
    TestClient = None
    fastapi_app = None
    _HAS_FASTAPI = False

st.set_page_config(page_title="LMSR Multi-Market Demo", layout="wide")
st.title("LMSR Prediction Markets")
st.caption("Multi-market simulator with full backend features — based on DESIGN.md")

# Small banner for demo context
st.info(
    "This is a **research & demonstration tool**. The UI now exclusively talks to the FastAPI layer "
    "(in-process TestClient for the self-contained demo). The Python engine remains the source of truth."
)

# =====================
# SESSION STATE
# =====================
if "sim" not in st.session_state:
    # We still keep a direct simulator instance **only** for the complex demo seeding logic
    # (run_scenario, load_history_into_simulator etc.). After seeding we inject it into
    # the API module so that **all UI interactions** (trade, portfolio, leaderboard, b controls,
    # create market, etc.) go exclusively through the FastAPI layer (using TestClient for the
    # self-contained `streamlit run app.py` experience).
    st.session_state.sim = _DirectSimulator()
    st.session_state.user_id = "alice"
    st.session_state.active_market_id = None
    st.session_state.demo_initialized = False
    st.session_state.trade_counter = 0

sim = st.session_state.sim

# From this point on the Streamlit UI only talks to the API (never directly to the simulator
# for user actions or display data). This is the new architecture.
if _HAS_FASTAPI:
    import src.lmsr.api as api_mod
    api_mod._sim = sim
    api_client = TestClient(fastapi_app)
else:
    # Fallback (the app will still run the seeding but interactive parts that need the client will be limited)
    api_client = None
    # Users who want the pure "UI talks only to the API" experience should install with the api extra.


def _safe_api(path, method="GET", json=None, params=None):
    """Small helper so most api_client calls have basic status + error surfacing.
    Returns the parsed JSON on success or {"error": ...} on failure.
    """
    if api_client is None:
        return {"error": "API client not available (install with the [api] extra)"}
    try:
        if method.upper() == "POST":
            r = api_client.post(path, json=json or {}, params=params)
        else:
            r = api_client.get(path, params=params)
        if r.status_code >= 400:
            body = r.json() if r.headers.get("content-type", "").startswith("application/json") else {"detail": r.text}
            msg = body.get("error") or body.get("detail") or str(body)
            st.error(f"API {r.status_code}: {msg}")
            return {"error": msg, "status": r.status_code}
        return r.json()
    except Exception as e:
        st.error(f"API call failed: {e}")
        return {"error": str(e)}

# Auto-load a strong demo state on first run (great for soft demos)
if not st.session_state.demo_initialized:
    try:
        mids = run_scenario(sim, "Full Teaching Demo (Multi-Market)")
        if isinstance(mids, list):
            st.session_state.active_market_id = mids[0]
        else:
            st.session_state.active_market_id = mids

        # Add one market using adaptive b so we can demonstrate the concept live.
        # Seeded with many small, mixed trades so the price starts at a
        # reasonable level (~0.72) while b has already grown from the floor.
        adaptive_b = BoundedB(LinearVolumeB(alpha=0.07, min_b=10), min_b=10, max_b=300)
        adaptive_market = sim.create_market(
            title="Will the new product launch on time? (Adaptive b)",
            b=adaptive_b,
            resolution_criteria="Internal launch tracking system + executive sign-off."
        )

        # Gradual mixed seeding (reproducible) — designed so the price
        # starts at a sensible level (~0.73) while b has already grown
        # noticeably from the floor. Good for demonstrating adaptive b.
        seed_trades = [
            (3,5),(2,4),(4,3),(1,4),(3,2),(2,5),(4,4),(3,6),
            (5,3),(2,3),(4,2),(5,5),(3,4),(6,3),(2,4),(4,5),
            (7,3),(3,2),(5,4),(2,3),(4,3),(8,4),(3,5),(5,2),
            (6,3),(2,2),(4,4),(9,3),(3,3),(5,5),(4,2),(3,4),(7,3)
        ]
        for i, (yes, no) in enumerate(seed_trades):
            sim.place_trade(adaptive_market.id, f"trader_{i}", yes, no)

    except Exception:
        # If seeding fails for any reason, continue with empty state
        pass
    st.session_state.demo_initialized = True

# Make sure the (now seeded) simulator is visible to the API layer (only when FastAPI is available).
if _HAS_FASTAPI:
    import src.lmsr.api as api_mod
    api_mod._sim = sim

# =====================
# SIDEBAR
# =====================
with st.sidebar:
    st.markdown("### Demo Controls")
    st.header("User")
    user_id = st.text_input("User ID", value=st.session_state.user_id)
    st.session_state.user_id = user_id

    if api_client is not None:
        balance = api_client.get(f"/users/{user_id}/balance").json()["balance"]
    else:
        balance = 1000.0  # fallback when API extra not installed
    st.metric("Your Balance", f"{balance:,.2f}")

    st.divider()
    st.header("Markets")
    st.caption("Load realistic scenarios or create your own.")

    with st.expander("➕ Create New Market", expanded=False):
        title = st.text_input("Market Question", value="Will revenue exceed $50M this quarter?")
        b_value = st.slider("Liquidity (b)", 1.0, 1000.0, 25.0, 1.0)
        resolution_criteria = st.text_area(
            "Resolution Criteria (optional)",
            value="Official earnings release published by the company.",
            height=80
        )
        if st.button("Create Market", type="primary"):
            resp = api_client.post(
                "/markets",
                json={
                    "title": title,
                    "resolution_criteria": resolution_criteria,
                    "b": float(b_value),
                },
            )
            if resp.status_code == 201:
                market = resp.json()
                st.session_state.active_market_id = market["id"]
            else:
                st.error(resp.text)
            st.rerun()

    # ------------------------------------------------------------------
    # Quick Demo Seeding (solves "always start from zero")
    # ------------------------------------------------------------------
    with st.expander("🚀 Quick Demo Scenarios", expanded=True):
        st.caption("One-click population of realistic markets using pre-generated histories (Kelly sizing, rug pulls, trends, etc.).")

        scenarios = get_available_scenarios()

        # Vertical list of buttons (one under the other) — easier to scan
        for i, name in enumerate(scenarios):
            if st.button(name, key=f"seed_{i}", width="stretch"):
                result = run_scenario(sim, name)
                # For multi-market scenarios, activate the first one
                if isinstance(result, list):
                    st.session_state.active_market_id = result[0]
                else:
                    st.session_state.active_market_id = result
                st.success(f"Loaded: {name}")
                st.rerun()

        st.divider()
        if st.button("🧹 Reset Simulator (clear everything)", width="stretch"):
            # Use the safe wrapper so errors are surfaced nicely
            res = _safe_api("/reset", method="POST")
            if "error" not in res:
                # Replace our local simulator instance with a fresh one and reset flags
                # so that on rerun the injection and the "not demo_initialized" auto-seed
                # both see a clean state. This makes the reset button actually observable.
                st.session_state.sim = _DirectSimulator()
                st.session_state.demo_initialized = False
                st.session_state.active_market_id = None
                st.session_state.trade_counter = 0
                # Re-inject immediately (the top-of-script injection will also run on rerun)
                if _HAS_FASTAPI:
                    import src.lmsr.api as api_mod
                    api_mod._sim = st.session_state.sim
                st.info("Simulator reset to empty state.")
            st.rerun()

    st.divider()

    all_markets = api_client.get("/markets").json()
    if all_markets:
        market_labels = {}
        for m in all_markets:
            label = f"{m['title']} | {m['status'].upper()} | {m.get('total_trades', 0)} trades"
            if m.get("is_adaptive"):
                label += " [Adaptive]"
            market_labels[m["id"]] = label
        market_ids = list(market_labels.keys())

        default_idx = 0
        if st.session_state.active_market_id in market_ids:
            default_idx = market_ids.index(st.session_state.active_market_id)

        selected_id = st.selectbox(
            "Active Market",
            options=market_ids,
            format_func=lambda x: market_labels[x],
            index=default_idx,
        )
        st.session_state.active_market_id = selected_id
    else:
        st.info("No markets yet. Create one above.")
        st.stop()

# Get the current active market **via the API** (as a dict)
active_id = st.session_state.active_market_id
market = api_client.get(f"/markets/{active_id}").json()

# =====================
# TABS
# =====================
tab_trade, tab_portfolio, tab_leaderboard, tab_explorer = st.tabs(
    ["📈 Trade", "👤 My Portfolio", "🏆 Leaderboard", "🔬 Interactive b Explorer"]
)


@st.dialog("Confirm Trade")
def _show_trade_confirmation_dialog(active_id, user_id, sy, sn, cost, raw_cost, current_pos, market_title):
    """Confirmation dialog before executing a trade (calls go through the FastAPI layer)."""
    st.markdown(f"**Market:** {market_title}")

    direction_yes = "Buy" if sy > 0 else "Sell"
    direction_no = "Buy" if sn > 0 else "Sell"

    col1, col2 = st.columns(2)
    with col1:
        st.metric("Yes Shares", f"{abs(sy):.1f}", delta=f"{direction_yes} Yes" if sy != 0 else None)
    with col2:
        st.metric("No Shares", f"{abs(sn):.1f}", delta=f"{direction_no} No" if sn != 0 else None)

    st.divider()

    if cost >= 0:
        st.metric("Estimated Cost", f"{cost:,.2f}")
    else:
        st.metric("Estimated Proceeds", f"{-cost:,.2f}")

    st.write(f"**Current Position:** Yes {current_pos[0]:.1f} | No {current_pos[1]:.1f}")

    new_yes = current_pos[0] + sy
    new_no = current_pos[1] + sn
    st.write(f"**Position After Trade:** Yes {new_yes:.1f} | No {new_no:.1f}")

    st.divider()

    col_confirm, col_cancel = st.columns(2)

    with col_confirm:
        if st.button("✅ Confirm Trade", type="primary", use_container_width=True):
            res = api_client.post(
                f"/markets/{active_id}/trades",
                json={"user_id": user_id, "shares_yes": sy, "shares_no": sn},
            ).json()
            if "error" in res:
                st.error(res["error"])
            else:
                st.success(f"Trade executed! Cash flow: {res['cost']:.2f}")
                st.session_state.trade_counter += 1
            st.rerun()

    with col_cancel:
        if st.button("Cancel", use_container_width=True):
            st.rerun()


@st.fragment
def _render_market_b_controls_and_price_chart(market, active_id, trades, refresh: int = 0):
    """Fragment that isolates all b-related UI and the dynamic price history chart
    for the currently visible market. Changing b here only reruns this fragment,
    not the rest of the app (Portfolio, Leaderboard, etc.).

    'market' here is a dict from the /markets/{id} JSON response (MarketResponse shape).
    'trades' is the list of trade dicts from /markets/{id}/trades (already fetched by caller).
    We avoid any direct simulator Market or .engine access inside this fragment.
    """
    # ------------------------------------------------------------------
    # b Recommendation Calculator
    # ------------------------------------------------------------------
    with st.expander("🧮 Help me choose a good b value", expanded=False):
        st.caption("Quick heuristic based on your risk tolerance and goals. Especially useful for long-running markets like *Experts vs Punters*.")

        c1, c2 = st.columns(2)
        with c1:
            subsidy = st.number_input("Your risk / subsidy budget", min_value=100, max_value=20000, value=1000, step=100,
                                      help="Roughly how much loss the market maker is willing to absorb")
            typical_size = st.number_input("Size of a strong conviction bet", min_value=10, max_value=2000, value=80, step=10,
                                           help="How much money a confident trader might risk on one bet")
        with c2:
            desired_move = st.slider("Desired price impact of one strong bet", 1.0, 15.0, 5.0, 0.5,
                                     help="How many percentage points should one meaningful trade move the market?")
            activity = st.select_slider("Expected trading activity", options=["Low", "Medium", "High"], value="Medium")

        activity_mult = {"Low": 0.7, "Medium": 1.0, "High": 1.45}[activity]

        b_from_conviction = (typical_size * 0.25) / (desired_move / 100.0) * activity_mult
        b_from_subsidy = subsidy / 0.693147  # binary LMSR worst-case loss ≈ b * ln(2)

        # Ideal fixed b the user "wants" for their desired impact
        rec_b = min(b_from_conviction, b_from_subsidy)

        if market.get("is_adaptive"):
            # --- Adaptive market version (data comes from the API) ---
            st.markdown("**Recommended adaptive parameters**")

            # We don't have the raw q vector from the basic /markets response.
            # For the demo we approximate using a reasonable default volume.
            current_total = 1000.0
            recommended_alpha = rec_b / current_total

            low_alpha = recommended_alpha * 0.65
            high_alpha = recommended_alpha * 1.55

            st.markdown(f"**Recommended alpha range:** **{low_alpha:.4f} – {high_alpha:.4f}**")
            st.caption(
                f"Suggested alpha: **{recommended_alpha:.4f}** "
                f"(based on your desired impact of ~{desired_move:.1f} points for a strong bet)"
            )

            if st.button("Apply recommended alpha to this market", type="primary", use_container_width=True):
                # Use the new API endpoint to set the strategy
                api_client.post(
                    f"/markets/{active_id}/set_strategy",
                    json={
                        "type": "bounded_linear",
                        "alpha": recommended_alpha,
                        "min_b": 8,
                        "max_b": 400,
                    },
                )
                st.rerun()

        else:
            # --- Fixed market version (original behavior) ---
            low_b = rec_b * 0.65
            high_b = rec_b * 1.55

            st.markdown(f"**Recommended b range:** **{low_b:,.0f} - {high_b:,.0f}**")
            st.caption(
                f"Center suggestion: **{rec_b:,.0f}** (capped by your subsidy budget) "
                f"→ implied max theoretical loss ≈ **{rec_b * 0.693:,.0f}**"
            )

            if st.button("Apply recommended b to this market", type="primary", use_container_width=True):
                # Use the set_strategy endpoint (type=fixed)
                api_client.post(
                    f"/markets/{active_id}/set_strategy",
                    json={"type": "fixed", "value": float(rec_b)},
                )
                st.rerun()   # scoped to this fragment only

    # Liquidity (b) setting (data now comes from the API response)
    if market.get("is_adaptive"):
        st.markdown("**Liquidity (b)** — this market uses **adaptive** liquidity")
        st.metric("Current b", f"{market.get('current_b', 0):.1f}")
        st.caption(
            "b is managed dynamically by a strategy (e.g. grows with trading volume). "
            "You cannot manually set a fixed value on this market."
        )
    else:
        # For fixed-b markets, put manual editing behind an expander
        # because the recommender + adaptive strategies are now the preferred way
        with st.expander("Advanced: Manually adjust fixed liquidity (b)", expanded=False):
            st.caption("Higher = deeper market, prices react less to each trade. "
                       "Most users should use the recommender above or an adaptive strategy instead.")

            current_b = float(market.get("current_b", 25.0))
            max_b_control = max(1000.0, current_b * 1.3 + 50)

            b_slider_col, b_num_col = st.columns([3, 1])
            with b_slider_col:
                slider_b = st.slider(
                    "b (slider)",
                    min_value=1.0,
                    max_value=max_b_control,
                    value=min(current_b, max_b_control),
                    step=5.0,
                    key=f"b_slider_{active_id}",
                    label_visibility="collapsed",
                )
            with b_num_col:
                num_b = st.number_input(
                    "b (exact)",
                    min_value=1.0,
                    max_value=max_b_control,
                    value=min(current_b, max_b_control),
                    step=1.0,
                    key=f"b_num_{active_id}",
                    label_visibility="collapsed",
                )

            new_b = num_b if num_b != current_b else slider_b
            if new_b != current_b:
                # Use the API to update the strategy (fixed)
                api_client.post(
                    f"/markets/{active_id}/set_strategy",
                    json={"type": "fixed", "value": float(new_b)},
                )
                st.rerun()  # the fragment will pick up the new value on next run via the market dict from the selectbox

    # Price history chart — only for the visible market (data via API)
    if trades:
        import pandas as pd

        from src.lmsr.market import BinaryLMSRMarket

        replay_b = market.get("current_b", 25.0)
        replay_fee = market.get("fee_rate", 0.02)
        temp = BinaryLMSRMarket(b=replay_b, fee_rate=replay_fee)
        dyn_prices = []
        for t in trades:
            temp.trade("__replay__", t["shares_yes"], t["shares_no"])
            p_yes, _ = temp.price()
            dyn_prices.append(round(p_yes, 4))

        price_df = pd.DataFrame({
            "Trade #": list(range(1, len(dyn_prices) + 1)),
            "P(Yes)": dyn_prices,
        })

        try:
            import altair as alt
            price_chart = alt.Chart(price_df).mark_line().encode(
                x=alt.X("Trade #:O", title="Trade #"),
                y=alt.Y("P(Yes):Q", scale=alt.Scale(domain=[0, 1]), title="P(Yes)"),
                tooltip=["Trade #", "P(Yes)"]
            ).properties(height=220, title="Price Path (P(Yes))")
            st.altair_chart(price_chart, use_container_width=True)
        except Exception:
            st.line_chart(
                price_df.set_index("Trade #"),
                height=220,
                width="stretch",
            )
            st.caption("Install altair for better charts (fixed y-axis [0,1])")

        st.caption(f"Price path recomputed with current b = {replay_b:.1f}")

        # Volume per step (Yes vs No) — use the trades list (dicts from API)
        if trades:
            vol_df = pd.DataFrame({
                "Trade #": list(range(1, len(trades) + 1)),
                "Yes Volume": [t["shares_yes"] for t in trades],
                "No Volume": [t["shares_no"] for t in trades],
            })

            try:
                import altair as alt

                vol_long = vol_df.melt(
                    id_vars=["Trade #"],
                    var_name="Side",
                    value_name="Volume"
                )
                vol_long["AbsVolume"] = vol_long["Volume"].abs()

                color_scale = alt.Scale(
                    domain=["Yes Volume", "No Volume"],
                    range=["#2ecc71", "#e74c3c"]
                )

                vol_chart = alt.Chart(vol_long).mark_bar().encode(
                    x=alt.X("Trade #:O", title="Trade #"),
                    y=alt.Y("AbsVolume:Q", title="Volume"),
                    color=alt.Color(
                        "Side:N",
                        scale=color_scale,
                        title=None
                    ),
                    tooltip=["Trade #", "Side", alt.Tooltip("Volume", title="Signed Volume")]
                ).properties(
                    height=160,
                    title="Volume per Step (Yes vs No)"
                )
                st.altair_chart(vol_chart, use_container_width=True)
            except Exception:
                st.bar_chart(vol_df.set_index("Trade #"), height=160)
    else:
        st.caption("No trades yet — the market starts at 50/50. Place the first trade to see the price chart.")

    # Current price (from the market response dict, which came from the engine via API)
    prices = market.get("current_prices", [0.5, 0.5])
    st.caption(f"**Current price:** Yes {prices[0]:.4f}  |  No {prices[1]:.4f}")


@st.fragment
def _render_portfolio_tab(user_id):
    """Isolated fragment for the Portfolio tab.
    Only reruns when something inside this fragment changes.
    Data comes from the API layer (portfolio + markets list for titles).
    """
    st.header(f"Portfolio for {user_id}")
    st.caption("See your positions, balance, and realized performance across all markets.")

    # Primary data via API
    port_resp = api_client.get(f"/users/{user_id}/portfolio").json()
    bal_resp = api_client.get(f"/users/{user_id}/balance").json()

    balance = port_resp.get("balance", bal_resp.get("balance", 0.0))
    st.metric("Current Balance", f"{balance:,.2f}")
    st.metric("Total Payouts Received", f"{port_resp.get('total_payouts_received', 0):,.2f}")
    st.metric("Realized PnL (from resolutions)", f"{port_resp.get('realized_pnl', 0):,.2f}")

    st.subheader("Positions Across Markets")

    # Build id->title map from API list (cheaper than per-market gets)
    try:
        markets_list = api_client.get("/markets").json()
        id_to_title = {m["id"]: m.get("title", m["id"]) for m in markets_list}
        id_to_status = {m["id"]: m.get("status", "?") for m in markets_list}
    except Exception:
        id_to_title = {}
        id_to_status = {}

    positions = port_resp.get("positions", {})
    if positions:
        pos_rows = []
        for mid, pos in positions.items():
            pos_rows.append({
                "Market": id_to_title.get(mid, mid),
                "Status": id_to_status.get(mid, "?"),
                "Yes": pos.get("yes", 0),
                "No": pos.get("no", 0),
                "Total Exposure": pos.get("total", 0),
            })
        st.dataframe(pos_rows, width="stretch", hide_index=True)
    else:
        st.info("You have not traded in any markets yet.")

    st.subheader("Payout History")
    # Payout history detail still uses simulator for the demo (full Payout records with timestamps/titles).
    # The core trading + balance/portfolio summary are API-driven.
    try:
        user_payouts = sim.get_user_payouts(user_id)
        if user_payouts:
            payout_rows = [
                {
                    "Market": sim.get_market(p.market_id).title,
                    "Outcome": p.outcome.upper(),
                    "Amount Received": p.amount,
                    "Date": p.timestamp.strftime("%Y-%m-%d %H:%M"),
                }
                for p in user_payouts
            ]
            st.dataframe(payout_rows, width="stretch", hide_index=True)
        else:
            st.write("No payouts received yet.")
    except Exception:
        st.write("No payouts received yet.")


@st.fragment
def _render_leaderboard_tab():
    """Isolated fragment for the Leaderboard tab.
    Only reruns when the radio or other widgets inside change.
    Data fetched via the API /leaderboard endpoint.
    """
    st.header("Global Leaderboard")
    st.caption("See who has been most accurate (Brier / Log) or profitable (PnL) across resolved markets.")

    metric = st.radio("Rank by", ["brier (lower better)", "log (higher better)", "pnl (higher better)"], horizontal=True)

    metric_map = {
        "brier (lower better)": "brier",
        "log (higher better)": "log",
        "pnl (higher better)": "pnl",
    }

    with st.expander("How the three rankings work", expanded=False):
        st.markdown("""
        **Brier Score** (lower is better)  
        Measures how close your probability forecasts were to the actual outcomes.  
        Being confidently wrong is heavily penalized. A perfect forecaster scores 0.

        **Log Score** (higher is better)  
        A strict proper scoring rule that *strongly* punishes overconfidence.  
        Predicting 99% when you're wrong is extremely costly. Higher (less negative) is better.

        **PnL** (higher is better)  
        This is **not** a traditional net profit/loss.  
        It only counts the money you received when the market resolved in your favor.  
        If you were wrong, you simply lose what you spent — it does **not** appear as a negative PnL.  
        This is why PnL is almost always positive in the leaderboard.
        """)

    # Via API (supports query params)
    board = api_client.get("/leaderboard", params={"metric": metric_map[metric], "min_resolved_trades": 1}).json()

    if board:
        st.dataframe(board, width="stretch", hide_index=True)
    else:
        st.info("No resolved markets with enough trades yet for a leaderboard.")


# =====================
# TAB 1: TRADE / MARKET VIEW
# =====================
with tab_trade:
    active_id = st.session_state.active_market_id
    market = api_client.get(f"/markets/{active_id}").json()

    # Fetch trades via API for charts (the basic market response doesn't include full trade list)
    trades = api_client.get(f"/markets/{active_id}/trades").json() if active_id else []

    st.header(market["title"])
    if market.get("resolution_criteria"):
        st.caption(f"**Resolution Criteria:** {market['resolution_criteria']}")

    # Prominent callout for adaptive b markets (very useful for the soft demo)
    if market.get("is_adaptive"):
        st.info(
            f"**Adaptive Liquidity Active** — This market uses a dynamic `b` strategy "
            f"that grows with trading volume. Current b = **{market.get('current_b', 0):.1f}** "
            f"(started at the floor of 10.0). This reduces early volatility compared to a fixed low b."
        )

    cols = st.columns([1, 1, 1, 1])
    with cols[0]:
        st.metric("Status", market.get("status", "open").upper())
    with cols[1]:
        st.metric("Trades", market.get("total_trades", 0))
    with cols[2]:
        # We don't have the full trade list in the basic market response; approximate or fetch if needed.
        # For the demo we can live with "Traders" being less precise or fetch via another call.
        # To keep it simple and API-driven, we'll show a placeholder or skip the expensive computation.
        st.metric("Traders (via API)", "—")  # could be enhanced with a dedicated /markets/{id}/traders endpoint

    with cols[3]:
        st.metric(
            "Fees Earned (Spread)",
            f"{market.get('total_fees_earned', 0):,.2f}",
            help="Total fees/spread captured by the market maker on all trades (buys + sells). "
                 "This is what the MM actually makes from the asymmetric fee model. "
                 "Net cash position (used for P/L at resolution) may differ due to sells."
        )

    # Only the visible market's b controls + price chart live in a fragment.
    # Changing b here only reruns this fragment — Portfolio, Leaderboard and
    # other markets are not recomputed.
    _render_market_b_controls_and_price_chart(
        market, active_id, trades, refresh=st.session_state.trade_counter
    )

    if market.get("status") == "open":
        st.subheader("Place Trade")
        st.caption("Enter positive numbers to buy shares, negative to sell. You can trade both sides in one transaction.")

        # Side-by-side inputs so they don't take full width
        yes_col, no_col = st.columns(2)
        with yes_col:
            sy = st.number_input(
                "Yes shares",
                value=0.0,
                step=1.0,
                key=f"sy_{active_id}",
                help="Positive = buy Yes, Negative = sell Yes"
            )
        with no_col:
            sn = st.number_input(
                "No shares",
                value=0.0,
                step=1.0,
                key=f"sn_{active_id}",
                help="Positive = buy No, Negative = sell No"
            )

        # Accurate preview using the dedicated /quote endpoint (pure, no user needed)
        q = api_client.get(
            f"/markets/{active_id}/quote",
            params={"shares_yes": sy, "shares_no": sn},
        ).json()
        cost = q["effective_cost"]
        st.caption(f"Est. cost: **{cost:.2f}**")

        # Live preview based on the trade inputs (data from API quote)
        if sy != 0 or sn != 0:
            st.markdown("**Expected Impact & Slippage**")
            price_after = q.get("price_after", [0.5, 0.5])
            impact = q.get("impact", [0.0, 0.0])
            slip_val = q.get("slippage", 0.0)

            st.write(f"**Price after trade:** {price_after[0]:.4f} / {price_after[1]:.4f}")
            st.write(f"**Impact on Yes:** {impact[0]:+.4f}")
            st.write(f"**Slippage:** {slip_val:.4f}")

            # Payout multiplier
            if cost > 0:
                mult_yes = sy / cost
                mult_no = sn / cost
                st.markdown("**Payout Multiplier**")
                st.write(f"If Yes wins: **{mult_yes:.2f}x**")
                st.write(f"If No wins: **{mult_no:.2f}x**")
            else:
                st.caption("Payout multiplier not shown for selling trades")

        # Prevent no-op trades (both sides zero)
        trade_disabled = (sy == 0 and sn == 0)

        if st.button("Execute Trade", type="primary", key=f"trade_{active_id}", disabled=trade_disabled):
            # Everything (preview + execution) now goes exclusively through the FastAPI layer
            obs = api_client.get(f"/markets/{active_id}/observe", params={"user_id": user_id}).json()
            current_pos = [obs["position"]["yes"], obs["position"]["no"]]
            mkt = api_client.get(f"/markets/{active_id}").json()

            # Accurate preview using the dedicated /quote endpoint (pure, no user needed)
            q = api_client.get(
                f"/markets/{active_id}/quote",
                params={"shares_yes": sy, "shares_no": sn},
            ).json()
            cost = q["effective_cost"]
            raw_cost = q["raw_cost"]

            _show_trade_confirmation_dialog(
                active_id=active_id,
                user_id=user_id,
                sy=sy,
                sn=sn,
                cost=cost,
                raw_cost=raw_cost,
                current_pos=current_pos,
                market_title=mkt["title"],
            )

        if trade_disabled:
            st.caption("Enter a non-zero number of shares on at least one side to execute a trade.")

    else:
        st.info("Market is resolved.")

    st.divider()

    # Positions
    st.subheader("Positions in this Market")
    st.caption("Your current holdings in the selected market (via observe).")
    # User-specific position always via API observe for consistency with TradingAgent / bots
    obs_here = api_client.get(f"/markets/{active_id}/observe", params={"user_id": user_id}).json()
    your_pos = [obs_here["position"]["yes"], obs_here["position"]["no"]]
    st.write(f"**You** — Yes: {your_pos[0]:.1f} | No: {your_pos[1]:.1f}")

    # Cross-user positions table (demo visibility of market state).
    # Now driven purely from the already-fetched /trades response + per-user /observe calls
    # so it stays consistent with the "UI talks to API" architecture even for the all-traders view.
    # (If a dedicated /markets/{id}/positions endpoint is added later this can be simplified further.)
    pos_data = []
    seen_users = set()
    for t in trades:  # list of dicts from /markets/{id}/trades (already fetched above)
        uid = t.get("user_id")
        if not uid or uid in seen_users:
            continue
        seen_users.add(uid)
        try:
            o = api_client.get(f"/markets/{active_id}/observe", params={"user_id": uid}).json()
            p = o.get("position", {})
            pos_data.append({"User": uid, "Yes": round(p.get("yes", 0), 1), "No": round(p.get("no", 0), 1)})
        except Exception:
            pass
    if not pos_data and (your_pos[0] or your_pos[1]):
        # Fallback for the current user only (should be rare)
        pos_data.append({"User": user_id, "Yes": round(your_pos[0], 1), "No": round(your_pos[1], 1)})

    if pos_data:
        st.dataframe(pos_data, width="stretch", hide_index=True)
    else:
        st.info("No trades recorded yet for positions.")

    st.divider()

    # Resolution + Scoring (now using stored scores when possible)
    # Resolve action goes through the API; display of full scores/payouts for demo uses sim (read-only views).
    if market.get("status") == "open":
        st.subheader("Resolve Market")
        st.caption("Resolve the market to see final payouts and calibration scores.")
        c1, c2 = st.columns(2)
        with c1:
            if st.button("Resolve to Yes", type="secondary"):
                res = _safe_api(f"/markets/{active_id}/resolve", method="POST", json={"outcome": "yes"})
                if "error" not in res:
                    mm_pl = res.get("market_maker_pl", res.get("pl", 0.0))
                    st.success(f"Resolved to Yes. MM P/L: {mm_pl:.4f}")
                st.rerun()
        with c2:
            if st.button("Resolve to No", type="secondary"):
                res = _safe_api(f"/markets/{active_id}/resolve", method="POST", json={"outcome": "no"})
                if "error" not in res:
                    mm_pl = res.get("market_maker_pl", res.get("pl", 0.0))
                    st.success(f"Resolved to No. MM P/L: {mm_pl:.4f}")
                st.rerun()
    else:
        st.subheader("Resolution & Stored Scores")

        # For the resolved view numbers we fall back to sim (the engine state after resolve is authoritative for demo display)
        try:
            mkt_res = sim.get_market(active_id)
            eng = mkt_res.engine
            payout_sum = sum(p.amount for p in mkt_res.payouts)
            st.metric("Market Maker Final P/L", f"{eng.total_revenue - payout_sum:.4f}")
            st.caption(f"Total fees/spread earned: {eng.total_fees_earned:,.2f}")
        except Exception:
            st.caption("Resolution details available via simulator for this demo view.")

        stored_scores = sim.get_scores(active_id)
        if stored_scores:
            st.write("**Stored Calibration Scores (from simulator)**")
            score_rows = []
            for s in stored_scores:
                score_rows.append({
                    "User": s.user_id,
                    "Forecast (p_yes)": round(s.forecast_prob, 4),
                    "Brier Score": round(s.brier_score, 4),
                    "Log Score": round(s.log_score, 4),
                })
            st.dataframe(score_rows, width="stretch", hide_index=True)
        else:
            st.write("No scores recorded for this market.")

# =====================
# TAB 2: MY PORTFOLIO
# =====================
with tab_portfolio:
    _render_portfolio_tab(user_id)

# =====================
# TAB 3: LEADERBOARD
# =====================
with tab_leaderboard:
    _render_leaderboard_tab()

# =====================
# TAB 4: INTERACTIVE b EXPLORER
# =====================
with tab_explorer:
    st.header("Interactive b Explorer")
    st.caption("Explore how different liquidity levels (`b`) affect price behavior on real trade histories. Great for understanding why adaptive b matters.")

    # Discover available histories — use __file__ so this works no matter the CWD
    # (fixes the relative-path bug when Streamlit is started from a different directory).
    data_dir = Path(__file__).parent / "examples" / "trade_histories"
    history_files = sorted(str(p) for p in data_dir.glob("*.json"))
    if not history_files:
        st.error(f"No trade histories found in {data_dir}")
        st.stop()

    history_names = [Path(f).stem.replace("_", " ").title() for f in history_files]
    selected_name = st.selectbox("Trade History", history_names, index=0)
    selected_path = history_files[history_names.index(selected_name)]

    history = load_history(selected_path)

    st.markdown(f"**{history.get('name', selected_name)}**")
    if "description" in history:
        st.caption(history["description"])

    # b slider - selection is free, heavy work only happens on explicit button click
    b_max = 1500
    b = st.slider(
        "Liquidity parameter b (higher = deeper market, less price impact)",
        min_value=1.0,
        max_value=float(b_max),
        value=30.0,
        step=5.0,
        key="explorer_b"
    )

    st.caption(f"Theoretical worst-case loss for market maker ≈ {b * 0.693:.0f} units")

    import pandas as pd

    @st.cache_data(show_spinner="Replaying with new b...")
    def get_replayed_data(history_path: str, b: float):
        h = load_history(history_path)
        snaps = replay_history(h, b=b)
        p_df = pd.DataFrame({
            "Step": [s["step"] for s in snaps],
            "P(Yes)": [s["price_yes"] for s in snaps],
        })
        v_df = pd.DataFrame({
            "Step": [s["step"] for s in snaps],
            "Yes Volume": [s["yes_shares"] for s in snaps],
            "No Volume": [s["no_shares"] for s in snaps],
        })
        return p_df, v_df

    # Initialize the committed b (the value we last actually computed for)
    if "explorer_b_committed" not in st.session_state:
        st.session_state.explorer_b_committed = b

    # Only trigger expensive replay when the user explicitly clicks the button
    if st.button("Recompute charts with this b", type="primary"):
        st.session_state.explorer_b_committed = b

    # Always render using the last committed b (safe, no widget key conflict)
    committed_b = st.session_state.explorer_b_committed
    price_df, vol_df = get_replayed_data(selected_path, committed_b)

    # Price chart with fixed y-axis [0, 1]
    st.subheader("Price Path (P(Yes))")
    try:
        import altair as alt
        price_chart = alt.Chart(price_df).mark_line().encode(
            x=alt.X("Step:O"),
            y=alt.Y("P(Yes):Q", scale=alt.Scale(domain=[0, 1]), title="P(Yes)"),
            tooltip=["Step", "P(Yes)"]
        ).properties(height=220, title="Price Path (P(Yes))")
        st.altair_chart(price_chart, use_container_width=True)
    except Exception:
        st.line_chart(price_df.set_index("Step"))
        st.caption("Install altair for better charts (fixed y-axis, etc.)")

    # Volume bars — green for Yes Volume, red for No Volume
    st.subheader("Volume per Step (Yes vs No)")

    try:
        import altair as alt

        vol_long = vol_df.melt(
            id_vars=["Step"],
            var_name="Side",
            value_name="Volume"
        )

        # Use absolute volume for bar height so bars don't get dwarfed by negative sells
        vol_long["AbsVolume"] = vol_long["Volume"].abs()

        # Volume chart — prefer Altair bars when reasonable.
        # Fall back to native Streamlit chart only for very long histories
        # (Altair bars become unreadable or fail to render properly past ~45 steps).
        if len(vol_long) > 45:
            st.bar_chart(vol_df.set_index("Step")[["Yes Volume", "No Volume"]], height=220)
            st.caption("Volume per Step (Yes vs No) — using fallback for long history")
        else:
            vol_chart = alt.Chart(vol_long).mark_bar().encode(
                x=alt.X("Step:O", title="Step"),
                y=alt.Y("AbsVolume:Q", title="Volume", scale=alt.Scale(domain=[0, None])),
                color=alt.Color(
                    "Side:N",
                    scale=alt.Scale(
                        domain=["Yes Volume", "No Volume"],
                        range=["#2ecc71", "#e74c3c"]
                    ),
                    title=None
                ),
                tooltip=["Step", "Side", alt.Tooltip("Volume", title="Signed Volume (buy +, sell -)")]
            ).properties(
                height=220,
                title="Volume per Step (Yes vs No)"
            )
            st.altair_chart(vol_chart, use_container_width=True)

    except Exception:
        # Fallback if altair is not installed
        st.bar_chart(vol_df.set_index("Step"))
        st.caption("Install altair for colored volume bars: pip install altair")

    # Quick stats
    final_price = float(price_df["P(Yes)"].iloc[-1]) if not price_df.empty else 0.5
    max_price = float(price_df["P(Yes)"].max()) if not price_df.empty else 0.5
    st.metric("Final P(Yes)", f"{final_price:.4f}")
    st.metric("Maximum P(Yes) Reached", f"{max_price:.4f}")

    # ------------------------------------------------------------------
    # High-value bridge: bring the current explorer view into the live app
    # ------------------------------------------------------------------
    st.divider()
    if st.button(
        "📥 Import this history into the main simulator (Trade / Portfolio / Leaderboard)",
        type="primary",
        width="stretch",
        key="import_from_explorer",
    ):
        # Use the exact b the user is currently exploring
        market_id = load_history_into_simulator(
            sim,
            selected_path,
            b=b,
            market_title=f"{selected_name} (b={b})",
        )
        st.session_state.active_market_id = market_id
        st.success(
            f"Imported '{selected_name}' with b={b} into the live simulator. "
            "Go to the Trade or Portfolio tab to continue experimenting."
        )
        st.rerun()

    with st.expander("Raw price path data"):
        st.dataframe(price_df, width="stretch", hide_index=True)

st.caption("All data comes from the backend simulator (payouts, scores, portfolio, leaderboard).")