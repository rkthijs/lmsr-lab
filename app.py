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
from src.lmsr.simulator import LMSRMarketSimulator  # noqa: E402

st.set_page_config(page_title="LMSR Multi-Market Demo", layout="wide")
st.title("LMSR Prediction Markets")
st.caption("Multi-market simulator with full backend features — based on DESIGN.md")

# =====================
# SESSION STATE
# =====================
if "sim" not in st.session_state:
    st.session_state.sim = LMSRMarketSimulator()
    st.session_state.user_id = "alice"
    st.session_state.active_market_id = None

sim = st.session_state.sim

# =====================
# SIDEBAR
# =====================
with st.sidebar:
    st.header("User")
    user_id = st.text_input("User ID", value=st.session_state.user_id)
    st.session_state.user_id = user_id

    balance = sim.get_balance(user_id)
    st.metric("Your Balance", f"{balance:,.2f}")

    st.divider()
    st.header("Markets")

    with st.expander("➕ Create New Market", expanded=True):
        title = st.text_input("Market Question", value="Will revenue exceed $50M this quarter?")
        b_value = st.slider("Liquidity (b)", 1.0, 1000.0, 25.0, 1.0)
        resolution_criteria = st.text_area(
            "Resolution Criteria (optional)",
            value="Official earnings release published by the company.",
            height=80
        )
        if st.button("Create Market", type="primary"):
            market = sim.create_market(
                title=title,
                resolution_criteria=resolution_criteria,
                b=b_value,
            )
            st.session_state.active_market_id = market.id
            st.rerun()

    # ------------------------------------------------------------------
    # Quick Demo Seeding (solves "always start from zero")
    # ------------------------------------------------------------------
    with st.expander("🚀 Quick Demo Scenarios", expanded=False):
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
            sim.reset()
            st.session_state.active_market_id = None
            st.info("Simulator reset to empty state.")
            st.rerun()

    st.divider()

    all_markets = sim.list_markets()
    if all_markets:
        market_labels = {m.id: f"{m.title} | {m.status.upper()} | {len(m.trades)} trades" for m in all_markets}
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

# =====================
# TABS
# =====================
tab_trade, tab_portfolio, tab_leaderboard, tab_explorer = st.tabs(
    ["📈 Trade", "👤 My Portfolio", "🏆 Leaderboard", "🔬 Interactive b Explorer"]
)


@st.fragment
def _render_market_b_controls_and_price_chart(market, active_id, sim):
    """Fragment that isolates all b-related UI and the dynamic price history chart
    for the currently visible market. Changing b here only reruns this fragment,
    not the rest of the app (Portfolio, Leaderboard, etc.).
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

        # Subsidy budget acts as an upper bound on recommended liquidity
        rec_b = min(b_from_conviction, b_from_subsidy)

        low_b = rec_b * 0.65
        high_b = rec_b * 1.55

        st.markdown(f"**Recommended b range:** **{low_b:,.0f} - {high_b:,.0f}**")
        st.caption(
            f"Center suggestion: **{rec_b:,.0f}** (capped by your subsidy budget) "
            f"→ implied max theoretical loss ≈ **{rec_b * 0.693:,.0f}**"
        )

        if st.button("Apply recommended b to this market", type="primary", use_container_width=True):
            market.b = float(rec_b)
            market.engine.b = float(rec_b)
            st.rerun()   # scoped to this fragment only

    # Liquidity (b) setting — dual control
    st.markdown("**Liquidity (b)** — higher = deeper market, prices react less to each trade")
    b_slider_col, b_num_col = st.columns([3, 1])
    with b_slider_col:
        slider_b = st.slider(
            "b (slider)",
            min_value=1.0,
            max_value=1000.0,
            value=float(market.b),
            step=5.0,
            key=f"b_slider_{active_id}",
            label_visibility="collapsed",
        )
    with b_num_col:
        num_b = st.number_input(
            "b (exact)",
            min_value=1.0,
            max_value=1000.0,
            value=float(market.b),
            step=1.0,
            key=f"b_num_{active_id}",
            label_visibility="collapsed",
        )

    new_b = num_b if num_b != market.b else slider_b
    if new_b != market.b:
        market.engine.b = float(new_b)
        market.b = float(new_b)
        st.rerun()   # scoped to this fragment only

    # Price history chart — only for the visible market
    if market.trades:
        import pandas as pd

        from src.lmsr.market import BinaryLMSRMarket

        temp = BinaryLMSRMarket(b=market.b, fee_rate=market.fee_rate)
        dyn_prices = []
        for t in market.trades:
            temp.trade("__replay__", t.shares_yes, t.shares_no)
            p_yes, _ = temp.price()
            dyn_prices.append(round(p_yes, 4))

        price_df = pd.DataFrame({
            "Trade #": list(range(1, len(dyn_prices) + 1)),
            "P(Yes)": dyn_prices,
        })
        st.line_chart(
            price_df.set_index("Trade #"),
            height=220,
            width="stretch",
        )
        st.caption(f"Price path recomputed with current b = {market.b}")
    else:
        st.caption("No trades yet — the market starts at 50/50. Place the first trade to see the price chart.")

    # Current price (cheap)
    p_yes, p_no = market.engine.price()
    st.caption(f"**Current price:** Yes {p_yes:.4f}  |  No {p_no:.4f}")


@st.fragment
def _render_portfolio_tab(sim, user_id):
    """Isolated fragment for the Portfolio tab.
    Only reruns when something inside this fragment changes.
    """
    st.header(f"Portfolio for {user_id}")

    portfolio = sim.get_user_portfolio(user_id)

    st.metric("Current Balance", f"{portfolio.balance:,.2f}")
    st.metric("Total Payouts Received", f"{portfolio.total_payouts_received:,.2f}")
    st.metric("Realized PnL (from resolutions)", f"{portfolio.realized_pnl:,.2f}")

    st.subheader("Positions Across Markets")

    if portfolio.positions:
        pos_rows = []
        for mid, pos in portfolio.positions.items():
            m = sim.get_market(mid)
            pos_rows.append({
                "Market": m.title,
                "Status": m.status,
                "Yes": pos["yes"],
                "No": pos["no"],
                "Total Exposure": pos["total"],
            })
        st.dataframe(pos_rows, width="stretch", hide_index=True)
    else:
        st.info("You have not traded in any markets yet.")

    st.subheader("Payout History")
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


@st.fragment
def _render_leaderboard_tab(sim):
    """Isolated fragment for the Leaderboard tab.
    Only reruns when the radio or other widgets inside change.
    """
    st.header("Global Leaderboard")

    metric = st.radio("Rank by", ["brier (lower better)", "log (higher better)", "pnl (higher better)"], horizontal=True)

    metric_map = {
        "brier (lower better)": "brier",
        "log (higher better)": "log",
        "pnl (higher better)": "pnl",
    }

    board = sim.get_leaderboard(metric=metric_map[metric], min_resolved_trades=1)

    if board:
        st.dataframe(board, width="stretch", hide_index=True)
    else:
        st.info("No resolved markets with enough trades yet for a leaderboard.")


# =====================
# TAB 1: TRADE / MARKET VIEW
# =====================
with tab_trade:
    active_id = st.session_state.active_market_id
    market = sim.get_market(active_id)

    st.header(market.title)
    if market.resolution_criteria:
        st.caption(f"**Resolution Criteria:** {market.resolution_criteria}")

    cols = st.columns([1, 1, 1, 1])
    with cols[0]:
        st.metric("Status", market.status.upper())
    with cols[1]:
        st.metric("Trades", len(market.trades))
    with cols[2]:
        st.metric("Traders", len(set(t.user_id for t in market.trades)))
    with cols[3]:
        if market.status == "resolved":
            st.success(f"Resolved: **{market.resolution_outcome.upper()}**")

    # Only the visible market's b controls + price chart live in a fragment.
    # Changing b here only reruns this fragment — Portfolio, Leaderboard and
    # other markets are not recomputed.
    _render_market_b_controls_and_price_chart(market, active_id, sim)

    if market.status == "open":
        st.subheader("Place Trade")

        # Side-by-side inputs so they don't take full width
        yes_col, no_col = st.columns(2)
        with yes_col:
            sy = st.number_input(
                "Yes shares",
                value=0.0,
                step=1.0,
                key=f"sy_{active_id}",
                help="+ = buy,  - = sell"
            )
        with no_col:
            sn = st.number_input(
                "No shares",
                value=0.0,
                step=1.0,
                key=f"sn_{active_id}",
                help="+ = buy,  - = sell"
            )

        cost, _ = market.engine.quote(sy, sn)
        st.caption(f"Est. cost: **{cost:.2f}**")

        # Live preview based on the trade inputs (no separate fields)
        if sy != 0 or sn != 0:
            st.markdown("**Expected Impact & Slippage**")
            impact = market.engine.instantaneous_impact(sy, sn)
            slip = market.engine.slippage(sy, sn)

            st.write(f"**Price after trade:** {impact['price_after'][0]:.4f} / {impact['price_after'][1]:.4f}")
            st.write(f"**Impact on Yes:** {impact['impact'][0]:+.4f}")
            st.write(f"**Slippage:** {slip['slippage']:.4f}")

            # Payout multiplier
            if cost > 0:
                mult_yes = sy / cost
                mult_no = sn / cost
                st.markdown("**Payout Multiplier**")
                st.write(f"If Yes wins: **{mult_yes:.2f}x**")
                st.write(f"If No wins: **{mult_no:.2f}x**")
            else:
                st.caption("Payout multiplier not shown for selling trades")

        if st.button("Execute Trade", type="primary", key=f"trade_{active_id}"):
            res = sim.place_trade(active_id, user_id, sy, sn)
            if "error" in res:
                st.error(res["error"])
            else:
                st.success(f"Executed! Cash flow: {res['cost']:.2f}")
                st.rerun()

    else:
        st.info("Market is resolved.")

    st.divider()

    # Positions
    st.subheader("Positions in this Market")
    your_pos = sim.get_user_position(active_id, user_id)
    st.write(f"**You** — Yes: {your_pos[0]:.1f} | No: {your_pos[1]:.1f}")

    pos_data = []
    for t in market.trades:
        p = sim.get_user_position(active_id, t.user_id)
        pos_data.append({"User": t.user_id, "Yes": round(p[0], 1), "No": round(p[1], 1)})

    if pos_data:
        st.dataframe(pos_data, width="stretch", hide_index=True)

    st.divider()

    # Resolution + Scoring (now using stored scores when possible)
    if market.status == "open":
        st.subheader("Resolve Market")
        c1, c2 = st.columns(2)
        with c1:
            if st.button("Resolve to Yes", type="secondary"):
                res = sim.resolve_market(active_id, "yes")
                st.success(f"Resolved to Yes. MM P/L: {res['market_maker_pl']:.4f}")
                st.rerun()
        with c2:
            if st.button("Resolve to No", type="secondary"):
                res = sim.resolve_market(active_id, "no")
                st.success(f"Resolved to No. MM P/L: {res['market_maker_pl']:.4f}")
                st.rerun()
    else:
        st.subheader("Resolution & Stored Scores")

        st.metric("Market Maker Final P/L", f"{market.engine.total_revenue - sum(p.amount for p in market.payouts):.4f}")

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
    _render_portfolio_tab(sim, user_id)

# =====================
# TAB 3: LEADERBOARD
# =====================
with tab_leaderboard:
    _render_leaderboard_tab(sim)

# =====================
# TAB 4: INTERACTIVE b EXPLORER
# =====================
with tab_explorer:
    st.header("Interactive b Explorer")
    st.caption("Load one of the example trade histories and see in real time how the liquidity parameter `b` changes the price path and volume impact.")

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

        color_scale = alt.Scale(
            domain=["Yes Volume", "No Volume"],
            range=["#2ecc71", "#e74c3c"]   # green for Yes, red for No
        )

        vol_chart = alt.Chart(vol_long).mark_bar().encode(
            x=alt.X("Step:O", title="Step"),
            y=alt.Y("AbsVolume:Q", title="Volume", scale=alt.Scale(domain=[0, None])),
            color=alt.Color(
                "Side:N",
                scale=color_scale,
                legend=alt.Legend(title="Side", orient="top")
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