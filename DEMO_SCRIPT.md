# Soft Demo Script – LMSR Prediction Market Simulator

**Date**: Soft Demo (Tomorrow)  
**Audience**: Internal / Stakeholders (informal)  
**Duration**: Aim for 8–12 minutes core walkthrough + Q&A  
**Tool**: `streamlit run app.py`

---

## 1. Pre-Demo Checklist (Do This Before Starting)

- [ ] Run the app locally at least twice end-to-end
- [ ] Make sure you can navigate the four main tabs smoothly
- [ ] Test the "Full Teaching Demo" loads correctly (it should auto-load now)
- [ ] Note the current effective `b` on the adaptive market
- [ ] Have this script open on a second screen or printed

**Command to start:**
```bash
source .venv/bin/activate
streamlit run app.py
```

---

## 2. Recommended Demo Flow (Core Narrative)

### Opening (30–45 seconds)
- "This is an in-memory research simulator for Logarithmic Market Scoring Rule (LMSR) prediction markets."
- "It's designed for internal forecasting and calibration work — think company-internal markets rather than public crypto prediction markets."
- "The core is written in Python. We're currently exploring moving toward a more professional web stack (FastAPI + modern frontend)."

### Step 1: Show Multi-Market + Portfolio (2 minutes)
- Point to the pre-loaded markets (should have several from the "Full Teaching Demo").
- Switch between markets using the sidebar selector.
- Go to **My Portfolio** tab.
- Highlight:
  - One user has positions across multiple markets
  - Realized PnL after resolutions
  - Balance updates

**Talking point**: "This is one of the more useful parts for internal use — people can see their exposure across different questions."

### Step 2: Leaderboard + Calibration Scoring (2–3 minutes)
- Go to the **Leaderboard** tab.
- Switch between the three ranking modes and open the "How the three rankings work" expander.

**Talking points**:

- **Brier Score** (lower is better): Measures how close your probability forecasts were to reality. Being confidently wrong is heavily penalized.

- **Log Score** (higher is better): A strict scoring rule that *strongly* punishes overconfidence. Predicting 99% when you're wrong is extremely expensive.

- **PnL** (higher is better): This is **not** traditional net profit/loss.  
  It only counts the money you *received* when you were on the winning side.  
  If you were wrong, you simply lose what you spent — that loss does **not** appear as a negative number.  
  This is why PnL is almost always positive in the leaderboard.

**Key message**:  
"The PnL column shows who made money on correct bets. The Brier and Log columns show who was actually well-calibrated, which is often more valuable for internal forecasting."

### Step 3: Highlight Adaptive b (Biggest Technical Differentiator) (2–3 minutes)
- In the sidebar or Trade tab, find the market titled **"Will the new product launch on time? (Adaptive b)"**.
- Show the current `b` value (it should be higher than the starting floor because trades have already happened).
- Explain the concept simply:

**Script suggestion**:
"Normally `b` is fixed. Here we're experimenting with adaptive liquidity — `b` grows as more money and activity comes into the market. This reduces the crazy price swings you get in thin markets early on, while still letting prices move when there's real information."

- If time allows, mention the different strategies available (`LinearVolumeB`, `LogVolumeB`, `BoundedB`, etc.).

### Step 4: Interactive b Explorer (Optional but impressive) (1–2 minutes)
- Switch to the **Interactive b Explorer** tab.
- Load one of the rug-pull or high-activity histories.
- Move the b slider and click "Recompute".
- Show how dramatically different the price path looks at low vs high b.

**Talking point**: "This has been really useful for us to understand when low liquidity is dangerous versus when it's actually desirable."

### Closing / Future Direction (30–45 seconds)
- "Right now this is a research-grade tool with a Streamlit interface."
- "Our next steps include:
  - A proper FastAPI backend that wraps this Python engine
  - A more professional frontend (Node.js / React)
  - A robust SQL persistence layer for real audit and concurrency needs
  - An internal agent API so bots and automated strategies can participate cleanly"
- "The Python core stays as the engine — we're just adding professional layers around it."

---

## 3. Backup / Alternative Flows

If something goes wrong or the audience wants something different:

- **Rug Pull Demo**: Load "Kelly Rug Pull (Resolved)" and walk through the price movement + final resolution.
- **Experts vs Punters**: Good for showing high-b behavior and slow information aggregation.
- **Create Market Live**: If they want to see trading in real time, create a new market and do a few manual trades.

---

## 4. Timing Guide (Soft 10-minute version)

| Section                        | Time    |
|--------------------------------|---------|
| Intro + context                | 1 min   |
| Multi-market + Portfolio       | 2 min   |
| Leaderboard + Scoring          | 2–3 min |
| Adaptive b demonstration       | 2–3 min |
| Explorer or live trading       | 1–2 min |
| Future direction + wrap-up     | 1 min   |
| **Total**                      | **~10 min** |

---

## 5. Tips for Delivery

- **Don't over-explain the math** unless asked. Focus on the *value* (calibration tracking, liquidity control, agent participation).
- If someone asks about production readiness, be honest: "This is still research-grade. We're actively planning the move to a more robust architecture (FastAPI + proper DB)."
- Have one or two specific numbers ready (e.g., current b on the adaptive market, how many trades in the teaching demo).
- Be ready to show the code structure quickly if a technical person asks ("The core is in `src/lmsr/simulator.py` and `market.py`").

---

## 6. Quick Environment Notes

- The app now auto-loads good demo data on first start.
- If you need a clean state, use the **Reset Simulator** button in the sidebar.
- The adaptive b market is pre-seeded with a few trades so you can immediately show that `b` has already increased.

Good luck with the soft demo!
