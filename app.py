import streamlit as st
import numpy as np
from src.lmsr.market import BinaryLMSRMarket

st.set_page_config(page_title="LMSR Prediction Market", layout="centered")
st.title("Robin Hanson LMSR Market Maker")
st.caption("Binary Yes/No market with 2% market maker fee, impact, slippage & P/L on resolution")

if "market" not in st.session_state:
    st.session_state.market = BinaryLMSRMarket(b=20.0, fee_rate=0.02)
    st.session_state.user_id = "alice"

market = st.session_state.market

# Sidebar controls
with st.sidebar:
    st.header("Market Settings")
    new_b = st.slider("Liquidity parameter b", 1.0, 100.0, market.b, 1.0)
    if new_b != market.b:
        market.b = new_b
        st.rerun()

    st.divider()
    st.header("User")
    user_id = st.text_input("User ID", value=st.session_state.user_id)
    if user_id != st.session_state.user_id:
        st.session_state.user_id = user_id

    if st.button("Reset Market"):
        market.reset()
        st.rerun()

# Main area
p_yes, p_no = market.price()
st.metric("Current Prices", f"Yes: {p_yes:.4f}  |  No: {p_no:.4f}")

col1, col2 = st.columns(2)

with col1:
    st.subheader("Trade (includes 2% fee)")
    shares_yes = st.number_input("Yes shares (positive = buy)", value=0.0, step=1.0, format="%.1f")
    shares_no = st.number_input("No shares (positive = buy)", value=0.0, step=1.0, format="%.1f")

    if st.button("Execute Trade", type="primary"):
        if shares_yes == 0 and shares_no == 0:
            st.warning("Enter some shares to trade")
        else:
            result = market.trade(user_id, shares_yes, shares_no)
            if "error" in result:
                st.error(f"{result['error']}. You currently hold {result['current_position']}")
            else:
                st.success(f"Total paid: {result['cost']:.4f} (base: {result['raw_cost']:.4f} + fee: {result['fee']:.4f})")
                st.rerun()

with col2:
    st.subheader("Preview Impact & Slippage")
    preview_yes = st.number_input("Preview Yes shares", value=5.0, step=1.0, key="preview_yes")
    preview_no = st.number_input("Preview No shares", value=0.0, step=1.0, key="preview_no")

    if preview_yes != 0 or preview_no != 0:
        impact = market.instantaneous_impact(preview_yes, preview_no)
        slip = market.slippage(preview_yes, preview_no)

        st.write(f"**Price after trade:** {impact['price_after'][0]:.4f} / {impact['price_after'][1]:.4f}")
        st.write(f"**Impact on Yes:** {impact['impact'][0]:+.4f}")
        st.write(f"**Average execution price:** {slip['average_execution_price']:.4f}")
        st.write(f"**Slippage:** {slip['slippage']:.4f}")

st.divider()
st.subheader("Your Position")
pos = market.get_user_position(user_id)
st.write(f"Yes shares: {pos[0]:.1f}")
st.write(f"No shares: {pos[1]:.1f}")

if market.user_positions:
    st.subheader("All Users")
    user_data = []
    for uid, shares in market.user_positions.items():
        user_data.append({
            "User": uid,
            "Yes": round(float(shares[0]), 1),
            "No": round(float(shares[1]), 1)
        })
    st.dataframe(user_data, use_container_width=True)

st.divider()
st.subheader("Market Maker P/L on Resolution")

col_r1, col_r2 = st.columns(2)
with col_r1:
    if st.button("Resolve to Yes"):
        result = market.resolve("yes")
        st.info(f"Market Maker P/L: {result['market_maker_pl']:.4f}")
        st.write(f"Total revenue collected: {result['total_revenue']:.4f}")
        st.write(f"Payout to Yes holders: {result['payout']:.4f}")
with col_r2:
    if st.button("Resolve to No"):
        result = market.resolve("no")
        st.info(f"Market Maker P/L: {result['market_maker_pl']:.4f}")
        st.write(f"Total revenue collected: {result['total_revenue']:.4f}")
        st.write(f"Payout to No holders: {result['payout']:.4f}")

st.caption("2% fee is taken on every trade. Market maker P/L = total revenue (incl. fees) - payout on resolution.")