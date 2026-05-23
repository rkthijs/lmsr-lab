import streamlit as st
import glob
from pathlib import Path

from src.lmsr.simulator import LMSRMarketSimulator
from examples.replay_history import load_history, replay_history, plot_price_with_volume  # type: ignore

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
        b_value = st.slider("Liquidity (b)", 5.0, 100.0, 25.0, 1.0)
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

    # Liquidity
    new_b = st.slider("Liquidity (b)", 5.0, 100.0, market.b, 1.0, key=f"b_{active_id}")
    if new_b != market.b:
        market.engine.b = float(new_b)
        market.b = float(new_b)
        st.rerun()

    if market.status == "open":
        col1, col2 = st.columns(2)

        st.subheader("Place Trade")

        sy = st.number_input("Yes shares (+ = buy)", value=0.0, step=1.0, key=f"sy_{active_id}")
        sn = st.number_input("No shares (+ = buy)", value=0.0, step=1.0, key=f"sn_{active_id}")

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
        st.dataframe(pos_data, use_container_width=True, hide_index=True)

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
            st.dataframe(score_rows, use_container_width=True, hide_index=True)
        else:
            st.write("No scores recorded for this market.")

# =====================
# TAB 2: MY PORTFOLIO
# =====================
with tab_portfolio:
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
        st.dataframe(pos_rows, use_container_width=True, hide_index=True)
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
        st.dataframe(payout_rows, use_container_width=True, hide_index=True)
    else:
        st.write("No payouts received yet.")

# =====================
# TAB 3: LEADERBOARD
# =====================
with tab_leaderboard:
    st.header("Global Leaderboard")

    metric = st.radio("Rank by", ["brier (lower better)", "log (higher better)", "pnl (higher better)"], horizontal=True)

    metric_map = {
        "brier (lower better)": "brier",
        "log (higher better)": "log",
        "pnl (higher better)": "pnl",
    }

    board = sim.get_leaderboard(metric=metric_map[metric], min_resolved_trades=1)

    if board:
        st.dataframe(board, use_container_width=True, hide_index=True)
    else:
        st.info("No resolved markets with enough trades yet for a leaderboard.")

# =====================
# TAB 4: INTERACTIVE b EXPLORER
# =====================
with tab_explorer:
    st.header("Interactive b Explorer")
    st.caption("Load one of the example trade histories and see in real time how the liquidity parameter `b` changes the price path and volume impact.")

    # Discover available histories
    history_files = sorted(glob.glob("examples/trade_histories/*.json"))
    if not history_files:
        st.error("No trade histories found in examples/trade_histories/")
        st.stop()

    history_names = [Path(f).stem.replace("_", " ").title() for f in history_files]
    selected_name = st.selectbox("Trade History", history_names, index=0)
    selected_path = history_files[history_names.index(selected_name)]

    history = load_history(selected_path)

    st.markdown(f"**{history.get('name', selected_name)}**")
    if "description" in history:
        st.caption(history["description"])

    # b slider
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

    # Replay with current b
    snapshots = replay_history(history, b=b)

    # Convert to DataFrames for plotting
    import pandas as pd

    price_df = pd.DataFrame({
        "Step": [s["step"] for s in snapshots],
        "P(Yes)": [s["price_yes"] for s in snapshots],
    })

    vol_df = pd.DataFrame({
        "Step": [s["step"] for s in snapshots],
        "Yes Volume": [s["yes_shares"] for s in snapshots],
        "No Volume": [s["no_shares"] for s in snapshots],
    })

    # Price chart
    st.subheader("Price Path (P(Yes))")
    st.line_chart(price_df.set_index("Step"))

    # Volume bars
    st.subheader("Volume per Step (Yes vs No)")
    st.bar_chart(vol_df.set_index("Step"))

    # Quick stats
    final_price = snapshots[-1]["price_yes"] if snapshots else 0.5
    max_price = max(s["price_yes"] for s in snapshots) if snapshots else 0.5
    st.metric("Final P(Yes)", f"{final_price:.4f}")
    st.metric("Maximum P(Yes) Reached", f"{max_price:.4f}")

    with st.expander("Raw price path data"):
        st.dataframe(price_df, use_container_width=True, hide_index=True)

st.caption("All data comes from the backend simulator (payouts, scores, portfolio, leaderboard).")