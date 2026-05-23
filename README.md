# LMSR Prediction Market Simulator

A clean, numerically stable implementation of Robin Hanson's **Logarithmic Market Scoring Rule (LMSR)** for binary prediction markets, built as a fully-featured in-memory multi-market simulator.

This project was developed following the detailed design discussion captured in [`DESIGN.md`](./DESIGN.md) (a long-form Claude conversation about building an internal/company forecasting tool).

## Overview

The goal is to provide a high-quality, experiment-friendly LMSR engine that can later be embedded into a larger system (database-backed API, web UI, scoring layer, etc.).

## License & Ownership

This project is maintained by **Robert Thijs Kozma** in a personal capacity.  
It is licensed under the [MIT License](LICENSE).

The repository is hosted under a personal GitHub account (`rkthijs/lmsr-lab`) and is **not** owned by any company.  
Contributions are accepted under the MIT License. A formal Contributor License Agreement (CLA) may be introduced in the future if the project receives significant external contributions.

The simulator currently supports:

- Multiple independent binary markets
- Numerically stable pricing and cost calculations
- Per-market immutable trade history
- Explicit payout records on resolution
- Stored per-trade calibration scores (Brier + Log)
- User balances and cross-market portfolio tracking
- Global leaderboard (by calibration or realized PnL)
- Accounting identity verification
- Full state persistence (save/load)

## Key Features

| Feature                        | Status     | Notes |
|--------------------------------|------------|-------|
| Core LMSR engine (`BinaryLMSRMarket`) | ✅ Complete | Numerically hardened (stable softmax + cost delta formula) |
| Multi-market support           | ✅ Complete | Each market has its own engine, trades, payouts, and scores |
| Payout records                 | ✅ Complete | Immutable `Payout` objects created on resolution |
| Resolution scoring             | ✅ Complete | `Score` records (Brier + Log) stored for every trade |
| User model + balances          | ✅ Complete | `User` objects with balances; trades check and update balance |
| Portfolio view                 | ✅ Complete | `get_user_portfolio()` aggregates positions, PnL, and payouts |
| Global leaderboard             | ✅ Complete | Rank by Brier, Log score, or PnL |
| Accounting identity checks     | ✅ Complete | Verifies payouts match engine state after resolution |
| Persistence                    | ✅ Complete | `save()` / `load()` using pickle |
| Streamlit demo                 | ✅ Complete | Full multi-market UI with Portfolio and Leaderboard tabs |

## Project Structure

```
.
├── app.py                      # Streamlit demo application
├── src/lmsr/
│   ├── market.py               # Core `BinaryLMSRMarket` engine
│   ├── scoring.py              # Brier, Log score, and Murphy decomposition
│   └── simulator.py            # `LMSRMarketSimulator` + User/Trade/Payout/Score models
├── tests/
│   ├── test_lmsr.py
│   └── test_simulator.py
├── DESIGN.md                   # Original design discussion (primary source of truth)
├── AGENTS.md                   # Project steering / contributor guidelines
└── README.md
```

## Getting Started

### 1. Run the Demo App

```bash
source .venv/bin/activate
streamlit run app.py
```

The app includes:
- Multi-market trading with live impact & slippage
- Payout multipliers
- Portfolio view across markets
- Global leaderboard (Brier / Log / PnL)
- Resolution with stored calibration scores

### 2. Programmatic Usage

```python
from src.lmsr.simulator import LMSRMarketSimulator

sim = LMSRMarketSimulator()

# Create markets
m1 = sim.create_market("Will revenue beat target?", b=30.0)
m2 = sim.create_market("Will the product launch on time?", b=20.0)

# Trade
sim.place_trade(m1.id, "alice", 12, 0)
sim.place_trade(m1.id, "bob", 0, 8)

# Resolve
result = sim.resolve_market(m1.id, "yes")
print(result["accounting_identity"])

# View portfolio
portfolio = sim.get_user_portfolio("alice")
print(portfolio)

# Leaderboard
board = sim.get_leaderboard(metric="brier", min_resolved_trades=1)
```

## Core Concepts

- **Market** — Independent LMSR market with its own engine, trade history, payouts, and scores.
- **Trade** — Immutable record of a trade (includes the price at which it was executed).
- **Payout** — Immutable record created on resolution for every user holding the winning side.
- **Score** — Stored Brier and Log score for each trade after resolution.
- **User** — Central identity with balance; positions and P/L are derived.
- **Portfolio** — Aggregated view of a user's positions, realized PnL, and payouts across all markets.

## Accounting Invariant

After every resolution the simulator verifies:

```
initial_subsidy + total_raw_costs - total_payouts ≈ 0
```

(within floating-point tolerance). This check is exposed via `check_accounting_identity()` and is automatically run on resolution.

## Examples

The `examples/` directory contains ready-to-use trade histories and helper scripts for exploring how the liquidity parameter `b` affects price paths:

```bash
python examples/replay_history.py
```

See [examples/README.md](examples/README.md) for details and how to create your own histories.

## Contributing

We welcome contributions! Please see [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

This project is maintained in a personal capacity. All contributions are accepted under the MIT License.

## License

This project is licensed under the MIT License — see the [LICENSE](LICENSE) file for details.

## Next Steps / Future Work

See `DESIGN.md` for the original roadmap. High-value remaining items include:

- Storing resolution scores in the `UserPortfolio`
- Global leaderboard improvements (e.g., weighting by number of markets)
- Proper persistence format (JSON + versioned schema)
- API layer on top of the simulator
- Multi-outcome / scalar markets

## License

This project is licensed under the [MIT License](LICENSE).

Copyright © 2025 Robert Thijs Kozma. All rights reserved.

---

Built following the detailed design in `DESIGN.md`. All core backend features described there that are relevant to an in-memory simulator have been implemented and tested.