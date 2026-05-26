# LMSR Prediction Market Simulator

**lmsr-lab** — An educational and research-oriented simulator for Robin Hanson's Logarithmic Market Scoring Rule (LMSR) for binary prediction markets.

This project was built following the detailed design conversation in [`DESIGN.md`](./DESIGN.md), which explores how to create a clean, numerically stable LMSR engine suitable for internal forecasting tools.

---

## Background & Motivation

Traditional prediction markets (especially crypto ones) are often designed for public, permissionless, real-money environments. For **internal company forecasting** or low-stakes experimental use, the requirements are very different:

- No need for trustless settlement (you control resolution)
- Play money or points are sufficient
- Small number of users (no need for blockchain scalability)
- Strong emphasis on **calibration** (how well people’s forecasts match reality)

In the original design discussion, the conclusion was to build a lightweight, self-hosted system using **LMSR** as the core market maker mechanism.

### Why LMSR?

LMSR has several properties that make it particularly suitable for internal tools:

- **Bounded loss**: The market maker’s worst-case loss is bounded by `b · ln(n)` (where `n` is the number of outcomes). For binary markets this is simply `b · ln(2)`.
- **Clean probabilities**: Prices are always a valid probability distribution.
- **Single intuitive parameter**: The liquidity parameter `b` directly controls how much prices move per trade.
- **Good theoretical calibration properties**: LMSR is a strictly proper scoring rule, which aligns well with wanting honest reporting and good calibration.

---

## Mathematical Foundation

### Core LMSR Formulas

For a binary market with outcomes *Yes* and *No*, let:

- `q = [q_yes, q_no]` = outstanding shares in each outcome
- `b` = liquidity parameter

**Cost function** (how much it costs the market maker to reach a certain state):

$$
C(q) = b \cdot \ln \left( e^{q_\text{yes}/b} + e^{q_\text{no}/b} \right)
$$

Or more generally for multiple outcomes:

$$
C(q) = b \cdot \ln \left( \sum_i \exp(q_i / b) \right)
$$

**Price** of outcome *i*:

$$
p_i = \frac{\exp(q_i / b)}{\sum_j \exp(q_j / b)}
$$

This is simply the softmax of the share vector `q / b`.

**Cost of a trade** (buying `Δq` shares):

The cost to the trader is:

$$
\Delta C = C(q + \Delta q) - C(q)
$$

### Numerical Stability (Important Detail)

A naive implementation of `C(q + Δq) - C(q)` suffers from **catastrophic cancellation** when trades are small relative to existing volume. This project uses the algebraically equivalent but numerically stable form (derived in the design discussion):

$$
\Delta C = b \cdot \ln \left( \sum_i p_i \cdot \exp(\Delta q_i / b) \right)
$$

where `p_i` are the prices *before* the trade.

All price calculations in this simulator use the stable softmax form:

$$
p_i = \exp\left( \frac{q_i}{b} - \text{LSE}(q/b) \right)
$$

where `LSE` is the log-sum-exp operation.

---

## Why This Project?

Most existing LMSR implementations are either:

- Very basic (no user tracking, no resolution accounting)
- Tied to specific frontends or blockchains
- Missing proper calibration scoring

This simulator was built to be **educational and research-friendly**, making it easy to:

- Experiment with different values of `b`
- Study how price paths evolve under different trading patterns (including rug-pull style histories)
- Explore calibration scoring (Brier score, Log score, Murphy decomposition)
- Understand the relationship between liquidity, price impact, and information aggregation

See the [`examples/`](./examples/) directory for ready-made trade histories and tools to replay them with different `b` values.

---

## Core Components

- **`BinaryLMSRMarket`** (`src/lmsr/market.py`)  
  The numerically stable core engine.

- **`LMSRMarketSimulator`** (`src/lmsr/simulator.py`)  
  The higher-level multi-market system that adds:
  - Trade history
  - Payout records
  - Stored resolution scores
  - User balances and portfolio tracking
  - Accounting identity verification
  - Leaderboard

- **Calibration Scoring** (`src/lmsr/scoring.py`)  
  Brier score, Log score, and Murphy decomposition.

- **Adaptive Liquidity Strategies** (`src/lmsr/adaptive.py`)  
  Support for dynamic/adaptive `b` (in addition to classic fixed `b`).
  Includes `LinearVolumeB`, `LogVolumeB`, `BoundedB`, `TradeCountB`, etc.
  See the module for details and usage.

---

## Getting Started

### Run the Demo

```bash
source .venv/bin/activate
streamlit run app.py
```

The app includes live trading, portfolio views, stored scoring, and a global leaderboard.

### Programmatic Usage

```python
from src.lmsr.simulator import LMSRMarketSimulator

sim = LMSRMarketSimulator()

# Create a market with subsidy ≈ 1000 (educational default)
m = sim.create_market(
    title="Will revenue beat target?",
    b=45.0,
    initial_subsidy=1000.0
)

# Trade
sim.place_trade(m.id, "alice", 12, 0)
sim.place_trade(m.id, "bob", 0, 8)

# Resolve
result = sim.resolve_market(m.id, "yes")
print("Accounting check:", result["accounting_identity"])

# View user's portfolio across markets
portfolio = sim.get_user_portfolio("alice")
print(portfolio)
```

---

## Educational Examples

The `examples/` directory is designed for exploration:

```bash
# Replay a history with different b values
python examples/replay_history.py

# Or programmatically
from examples.replay_history import load_history, compare_b_values
history = load_history("examples/trade_histories/kelly_rug_pull.json")
compare_b_values(history, b_values=[15, 30, 60, 120])
```

You can also use the **Interactive b Explorer** tab in the Streamlit app to load any history and move a slider for `b`.

---

## Fixed vs Adaptive Liquidity (`b`)

By default, `b` is a fixed constant (classic LMSR). However, the library also supports **dynamic/adaptive `b`** strategies. These allow liquidity to change over time — typically growing with trading volume — which helps reduce excessive early volatility (the "thin market problem").

### Basic Usage

```python
from src.lmsr import BinaryLMSRMarket, LMSRMarketSimulator
from src.lmsr.adaptive import LinearVolumeB, LogVolumeB, BoundedB

# Fixed b (traditional)
m_fixed = BinaryLMSRMarket(b=60)

# Adaptive: b grows linearly with total shares, but capped
adaptive = BoundedB(
    LinearVolumeB(alpha=0.05, min_b=10),
    min_b=10,
    max_b=350
)
m_adaptive = BinaryLMSRMarket(b=adaptive)

# Use with the simulator
sim = LMSRMarketSimulator()
m = sim.create_market("Test Market", b=LogVolumeB(alpha=10, min_b=8))
```

### Comparison of Available Strategies

| Class                | Growth Behavior                      | Best For                                      | Stateful?          |
|----------------------|--------------------------------------|-----------------------------------------------|--------------------|
| `FixedB` / `ConstantB` | Constant                            | Baseline, classic LMSR                        | No                 |
| `LinearVolumeB`      | Linear in total shares               | General purpose, most common choice           | No                 |
| `SqrtVolumeB`        | Square root of total shares          | Slower growth than linear                     | No                 |
| `LogVolumeB`         | Logarithmic (very slow)              | Long-running or high-volume markets           | No                 |
| `BoundedB`           | Wrapper that clips any strategy      | Production use (prevent extremes)             | No                 |
| `TradeCountB`        | Linear in number of trades           | When participation matters more than size     | Yes (use `.step()`) |

### Recommended Strategies

- `LinearVolumeB` — Most common. Good default for many experiments.
- `LogVolumeB` — Grows very slowly. Excellent for long-running markets.
- `BoundedB(...)` — Wrap any strategy to enforce hard min/max bounds (highly recommended for real use).

See `src/lmsr/adaptive.py` for the full list, detailed documentation, and more examples.

---

## Project Structure

```
.
├── app.py                      # Streamlit demo
├── src/lmsr/
│   ├── market.py               # Core LMSR engine (numerically stable)
│   ├── scoring.py              # Brier, Log score, Murphy decomposition
│   └── simulator.py            # Multi-market system + User/Trade/Payout/Score models
├── examples/
│   ├── trade_histories/        # Ready-made histories (including Kelly + rug pulls)
│   └── replay_history.py       # Tools to explore different b values
├── tests/
├── DESIGN.md                   # Primary design source (detailed math + architecture)
├── AGENTS.md                   # Project steering guidelines
└── README.md
```

---

## License & Ownership

This project is maintained by **Robert Thijs Kozma** in a personal capacity.  
It is licensed under the [MIT License](LICENSE).

The repository lives under a personal GitHub account and is not owned by any company.

---

Built as an educational and research tool following the design in `DESIGN.md`.