# AGENTS.md — Project Steering File

This file provides guidance for AI agents (and human contributors) working in this repository. It will evolve as the project grows.

## Project Overview

**LMSR Prediction Market Simulator**

A clean, educational implementation of Robin Hanson's Logarithmic Market Scoring Rule (LMSR) for **binary** (Yes/No) prediction markets.

- Automated liquidity via the LMSR cost function
- Built-in 2% market-maker fee
- User position tracking (independent of aggregate `q`)
- Instantaneous price impact and slippage estimators
- Resolution P/L calculation for the market maker
- Interactive Streamlit demo (`app.py`)

**Core reference**: Robin Hanson’s LMSR papers and the standard formulation `C(q) = b * log(exp(q_yes/b) + exp(q_no/b))`.

**Current maturity**: Core engine + demo UI functional. Packaging, tests, examples, and docs are still minimal.

## Repository Layout

```
/home/bob/Projects/test
├── app.py                 # Streamlit UI (entry point for demo)
├── src/
│   └── lmsr/
│       └── market.py      # Core `BinaryLMSRMarket` implementation (single source of truth)
├── tests/                 # pytest suite (empty — add tests here)
├── examples/              # Experiment scripts, notebooks, CLI demos (empty)
├── .hermes/plans/         # Historical implementation plans (read-only reference)
├── .venv/                 # Project virtual environment (Python 3.12 + numpy + streamlit)
├── .git/
└── AGENTS.md              # This file
```

**Do not** commit or edit anything inside `.venv/`.

## Running the Project

### Activate environment
```bash
source .venv/bin/activate
# or use full paths below
```

### Run the Streamlit demo
```bash
PYTHONPATH=. .venv/bin/streamlit run app.py
# or
.venv/bin/streamlit run app.py --server.runOnSave true
```

The UI lets you:
- Adjust liquidity parameter `b`
- Trade Yes/No shares (with fee)
- Preview impact & slippage before trading
- View positions
- Resolve the market and see market-maker P/L

### Quick smoke test (Python)
```bash
.venv/bin/python -c '
import sys
sys.path.insert(0, ".")
from src.lmsr.market import BinaryLMSRMarket
m = BinaryLMSRMarket(b=20, fee_rate=0.02)
print("Prices:", m.price())
m.trade("alice", 10, 0)
print("After buy 10 Yes:", m.price())
print("OK")
'
```

## Core Implementation Notes (src/lmsr/market.py)

- `q` = outstanding shares vector `[q_yes, q_no]`
- `user_positions` = separate ledger per user (prevents negative holdings)
- `_cost(q)` uses `np.logaddexp` for numerical stability
- `fee_rate` applied asymmetrically on buys vs sells (current design)
- `resolve(outcome)` computes market-maker P/L = total_revenue - payout
- All public methods are side-effect free except `trade`, `resolve`, `reset`

**Invariants to preserve**:
- Prices always sum to 1.0
- Buying Yes increases p_yes (and vice versa)
- User cannot sell more shares than they hold
- `total_revenue` only increases on trades

## Coding & Contribution Guidelines

1. **Keep the market engine pure**
   - New logic belongs in `BinaryLMSRMarket` or small, well-tested helpers inside `market.py`
   - No new runtime dependencies for the core (numpy only)
   - Prefer `np` vectorized code over Python loops

2. **Testing**
   - All new behavior **must** come with tests in `tests/`
   - Use `pytest` (add to `pyproject.toml` when we introduce it)
   - Key test categories:
     - Cost/price mathematical correctness and sum-to-1
     - Round-trip trade + position consistency
     - Impact/slippage calculations
     - Resolution P/L accounting
     - Edge cases (b=1, b=100, huge trades, zero shares, sells)

3. **UI changes**
   - `app.py` is intentionally a single-file demo for now
   - When it grows, consider extracting components but keep the market class as the only source of truth

4. **Documentation**
   - Update this `AGENTS.md` when you introduce new conventions, commands, or architectural decisions
   - Add or improve docstrings and type hints on any public API you touch
   - Keep the math comments accurate

5. **General agent rules**
   - Before editing core logic, read the latest version of `src/lmsr/market.py` and this file
   - Run the smoke test (or the full app) after any change that affects trading or pricing
   - Prefer small, reviewable diffs
   - Never delete or weaken existing tests (once they exist)
   - Use the project `.venv` Python for all verification
   - If you create new files, add them to the appropriate directory (`tests/`, `examples/`, `src/...`)

6. **Packaging & Tooling (future)**
   - When we add `pyproject.toml`, follow PEP 621 / modern Python packaging
   - Use `ruff` for linting/formatting (plan to adopt)
   - Keep `.gitignore` sensible (ignore `__pycache__`, `.venv`, `.hermes` local state if needed)

## Current Gaps / Roadmap (May 2026)

- [ ] Add `src/lmsr/__init__.py`
- [ ] Write `pyproject.toml` + basic packaging
- [ ] Populate `tests/test_lmsr.py` with comprehensive cases
- [ ] Add `examples/experiments.py` (parameter sweeps, simulated traders)
- [ ] Write `README.md` with math explanation + usage
- [ ] Add type hints + full docstrings to `market.py`
- [ ] Consider CLI entry point for experiments

## Questions or Ambiguities?

When an agent is unsure about requirements, math, or design choices:
1. Re-read this file and `src/lmsr/market.py`
2. Re-read the original plan in `.hermes/plans/`
3. Ask the user for clarification before making large changes

---

**Last updated**: 2026-05 (initial version created after project exploration)
**Maintainer note**: Treat this file as living documentation. Keep it concise but actionable.