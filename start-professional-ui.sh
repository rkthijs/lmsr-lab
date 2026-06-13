#!/bin/bash
#
# start-professional-ui.sh
#
# One-command helper to set up and run the *professional separate frontend + backend*
# (Next.js UI + FastAPI admin/user API). This is completely independent of the Streamlit demo.
#
# What it does:
#   - Creates/activates the project .venv if needed
#   - Installs the package with [api] extras
#   - Runs the 300-round bot demo to seed a rich unresolved market (true p≈0.8, starts at 0.5)
#   - Starts the FastAPI backend (lmsr serve) in the foreground
#
# In a *separate terminal* you then run the frontend:
#   cd frontend && npm run dev
#
# Then open http://localhost:3000
#   - Use the top user dropdown to instantly switch users and see *exactly* what each user sees
#     (cash, position value/MTM, total equity, their portfolio, per-market positions, and trade as them).
#   - Switch to the Admin tab:
#     • See global activity across all users/markets and resolve any market.
#     • "Demo Scenarios" panel: load ANY of the curated demos that the Streamlit app offers
#       (Balanced, Rug Pull, High-Activity Kelly, Long Trend, Full Teaching multi-market, Experts vs Punters,
#        or the default 300-round bot activity). "Load Selected Scenario" resets state + populates the DB.
#
# Prerequisites:
#   - Python + the project's .venv (created by `python -m venv .venv` if missing)
#   - Node.js + npm (for the frontend in the other terminal)
#
# Usage:
#   ./start-professional-ui.sh
#   (or bash start-professional-ui.sh)
#
# Stop the backend with Ctrl-C. The frontend is independent.

set -e

echo "=== LMSR Professional Separate UI Starter ==="
echo

# 1. Ensure we have a venv
if [ ! -d ".venv" ]; then
    echo "Creating .venv ..."
    python3 -m venv .venv
fi

echo "Activating .venv ..."
# shellcheck disable=SC1091
source .venv/bin/activate

# 2. Install the project with API extras (idempotent)
echo "Installing package with [api] extras (this may take a minute the first time)..."
pip install -e ".[api]" --quiet

echo "✓ Environment ready"

# 3. Seed the rich 300-round unresolved demo market (true p≈0.8, starts at 0.5)
#    This populates lmsr_demo.db with ~300 rounds of activity from the bot mix
#    (informed bull driving price toward true value, seeded contrarian selling on the move,
#    boosted random, inventory, LP, etc.). 
#    After this, the frontend user dropdown will show many users (bull, contrarian, random, etc.)
#    instead of only "demo_bot". 
#    In the Admin tab of the UI you can later switch to any other curated demo scenario
#    (the full set from examples/demo_seeding.py, matching the Streamlit "Quick Demo Scenarios").
echo
echo "Seeding 300-round bot demo (this will take a little while and is great for the UI)..."
python examples/ui_300_round_bots.py

echo "✓ Seeding complete. Market left unresolved with real history."
echo "  (Use the Admin → Demo Scenarios panel in the frontend to load other demos on demand.)"

# 4. Start the backend.
#    We use `exec` so this script becomes the server process (easy to Ctrl-C).
#    The frontend is started in a *different terminal* (see instructions below).
echo
echo "Starting the FastAPI backend (admin + user-level endpoints + CORS for the frontend)..."
echo
echo ">>> IMPORTANT: In another terminal, run the frontend with:"
echo "    cd frontend && npm run dev"
echo
echo "Then open http://localhost:3000"
echo "    • Top dropdown lets you switch users → you instantly see exactly what that user sees"
echo "      (cash balance, position value at current prices, total account value, their trades/positions)."
echo "    • Admin tab: global activity across everyone + resolve any market."
echo
echo "Backend is now starting on http://0.0.0.0:8000 (API docs at /docs)"
echo "Press Ctrl-C to stop the backend."
echo

# This replaces the script with the server process
exec lmsr serve --host 0.0.0.0 --port 8000
