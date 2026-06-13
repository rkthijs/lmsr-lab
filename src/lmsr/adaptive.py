"""
Adaptive / Dynamic Liquidity Strategies for Binary LMSR.

These strategies allow `b` (the liquidity parameter) to change over time
based on the current market state (typically outstanding shares or trade count).
This helps address the "thin market problem" where early trading causes
excessive price impact.

## Available Strategies

| Class                | Growth Behavior                     | Best For                              | Stateful?          |
|----------------------|-------------------------------------|---------------------------------------|--------------------|
| `FixedB` / `ConstantB` | Constant                           | Baseline, classic LMSR                | No                 |
| `LinearVolumeB`      | Linear in total shares              | General purpose, most common choice   | No                 |
| `SqrtVolumeB`        | Square root of total shares         | Slower growth than linear             | No                 |
| `LogVolumeB`         | Logarithmic (very slow)             | Long-running or high-volume markets   | No                 |
| `BoundedB`           | Wrapper that clips any strategy     | Production use (prevent extremes)     | No                 |
| `TradeCountB`        | Linear in number of trades          | When participation matters more than size | Yes (use `.step()`) |

## Quick Examples

```python
from src.lmsr import BinaryLMSRMarket
from src.lmsr.adaptive import (
    LinearVolumeB, LogVolumeB, BoundedB, TradeCountB
)

# Classic fixed liquidity
m1 = BinaryLMSRMarket(b=50)

# Liquidity grows with volume, but hard-capped
adaptive = BoundedB(
    LinearVolumeB(alpha=0.06, min_b=8),
    min_b=8,
    max_b=400
)
m2 = BinaryLMSRMarket(b=adaptive)

# Very slow growth — good for long histories
m3 = BinaryLMSRMarket(b=LogVolumeB(alpha=12.0, min_b=10, max_b=500))

# Growth based on trade count (not share volume)
tc = TradeCountB(alpha=2.5, min_b=10, max_b=300)
m4 = BinaryLMSRMarket(b=tc)
# ... after each successful trade:
tc.step()
```

## References

- Othman, Pennock, Reeves, Sandholm (2013).  
  *"Practical Liquidity-Sensitive Automated Market Making"*.
- Robin Hanson (2002). Logarithmic Market Scoring Rules.

See `BinaryLMSRMarket` for how to pass these strategies as the `b` parameter.
"""

from __future__ import annotations

from typing import Protocol

import numpy as np
import numpy.typing as npt


class AdaptiveBStrategy(Protocol):
    """Protocol for adaptive b functions."""

    def __call__(self, q: npt.NDArray[np.floating]) -> float: ...


class FixedB:
    """Wrapper for a constant b (useful for explicitness when mixing strategies)."""

    def __init__(self, b: float):
        if b <= 0:
            raise ValueError("b must be positive")
        self.b = float(b)

    def __call__(self, q: npt.NDArray[np.floating]) -> float:
        return self.b

    def __repr__(self) -> str:
        return f"FixedB(b={self.b})"


class LinearVolumeB:
    """
    Linear volume-based adaptive liquidity.

    b(q) = clamp(alpha * total_outstanding_shares, min_b, max_b)

    This is one of the simplest and most commonly discussed adaptive rules
    (see Othman et al. 2013). Liquidity grows proportionally with trading
    activity.

    Parameters
    ----------
    alpha : float
        Scaling factor. Typical values: 0.01 – 0.1.
    min_b : float
        Minimum liquidity floor.
    max_b : float or None
        Optional upper bound on liquidity. If provided, b will never
        exceed this value.
    """

    def __init__(self, alpha: float = 0.05, min_b: float = 5.0, max_b: float | None = None):
        if alpha <= 0:
            raise ValueError("alpha must be positive")
        if min_b <= 0:
            raise ValueError("min_b must be positive")
        if max_b is not None and max_b <= min_b:
            raise ValueError("max_b must be greater than min_b")
        self.alpha = float(alpha)
        self.min_b = float(min_b)
        self.max_b = float(max_b) if max_b is not None else None

    def __call__(self, q: npt.NDArray[np.floating]) -> float:
        total_shares = float(np.sum(np.abs(q)))
        raw = self.alpha * total_shares
        if self.max_b is not None:
            return max(self.min_b, min(self.max_b, raw))
        return max(self.min_b, raw)

    def __repr__(self) -> str:
        parts = [f"alpha={self.alpha}", f"min_b={self.min_b}"]
        if self.max_b is not None:
            parts.append(f"max_b={self.max_b}")
        return f"LinearVolumeB({', '.join(parts)})"


class SqrtVolumeB:
    """
    Square-root volume adaptive liquidity.

    b(q) = clamp(alpha * sqrt(total_outstanding_shares), min_b, max_b)

    Grows more slowly than linear volume. Useful when you want
    diminishing returns to additional trading activity.
    """

    def __init__(self, alpha: float = 2.0, min_b: float = 5.0, max_b: float | None = None):
        if alpha <= 0:
            raise ValueError("alpha must be positive")
        if min_b <= 0:
            raise ValueError("min_b must be positive")
        if max_b is not None and max_b <= min_b:
            raise ValueError("max_b must be greater than min_b")
        self.alpha = float(alpha)
        self.min_b = float(min_b)
        self.max_b = float(max_b) if max_b is not None else None

    def __call__(self, q: npt.NDArray[np.floating]) -> float:
        total_shares = float(np.sum(np.abs(q)))
        raw = self.alpha * np.sqrt(total_shares)
        if self.max_b is not None:
            return max(self.min_b, min(self.max_b, raw))
        return max(self.min_b, raw)

    def __repr__(self) -> str:
        parts = [f"alpha={self.alpha}", f"min_b={self.min_b}"]
        if self.max_b is not None:
            parts.append(f"max_b={self.max_b}")
        return f"SqrtVolumeB({', '.join(parts)})"


# Convenience aliases
ConstantB = FixedB


class LogVolumeB:
    """
    Logarithmic volume-based adaptive liquidity.

    b(q) = clamp(alpha * log(1 + total_outstanding_shares), min_b, max_b)

    Liquidity grows very slowly. This is often desirable for long-running
    or high-volume markets because it prevents b from becoming excessively
    large while still providing some protection against thin markets early on.

    Parameters
    ----------
    alpha : float
        Scaling factor. Typical values: 5.0 – 30.0.
    min_b : float
        Minimum liquidity floor.
    max_b : float or None
        Optional upper bound.
    """

    def __init__(self, alpha: float = 10.0, min_b: float = 5.0, max_b: float | None = None):
        if alpha <= 0:
            raise ValueError("alpha must be positive")
        if min_b <= 0:
            raise ValueError("min_b must be positive")
        if max_b is not None and max_b <= min_b:
            raise ValueError("max_b must be greater than min_b")
        self.alpha = float(alpha)
        self.min_b = float(min_b)
        self.max_b = float(max_b) if max_b is not None else None

    def __call__(self, q: npt.NDArray[np.floating]) -> float:
        total_shares = float(np.sum(np.abs(q)))
        raw = self.alpha * np.log1p(total_shares)
        if self.max_b is not None:
            return max(self.min_b, min(self.max_b, raw))
        return max(self.min_b, raw)

    def __repr__(self) -> str:
        parts = [f"alpha={self.alpha}", f"min_b={self.min_b}"]
        if self.max_b is not None:
            parts.append(f"max_b={self.max_b}")
        return f"LogVolumeB({', '.join(parts)})"


class BoundedB:
    """
    Wrapper that clips the output of any adaptive strategy between a min and max.

    This is extremely useful in practice to prevent liquidity from becoming
    either too low (early volatility) or too high (market becomes unresponsive).

    Example
    -------
    >>> from src.lmsr.adaptive import LinearVolumeB, BoundedB
    >>> bounded = BoundedB(LinearVolumeB(alpha=0.1), min_b=10, max_b=400)
    """

    def __init__(self, strategy: AdaptiveBStrategy, min_b: float, max_b: float):
        if min_b <= 0:
            raise ValueError("min_b must be positive")
        if max_b <= min_b:
            raise ValueError("max_b must be greater than min_b")
        self.strategy = strategy
        self.min_b = float(min_b)
        self.max_b = float(max_b)

    def __call__(self, q: npt.NDArray[np.floating]) -> float:
        raw = self.strategy(q)
        return max(self.min_b, min(self.max_b, raw))

    def __repr__(self) -> str:
        return f"BoundedB(strategy={self.strategy}, min_b={self.min_b}, max_b={self.max_b})"


class TradeCountB:
    """
    Adaptive liquidity based on the number of trades rather than share volume.

    b(trade_count) = clamp(alpha * trade_count, min_b, max_b)

    This strategy is **stateful**. Because `BinaryLMSRMarket` may evaluate the
    b function multiple times per trade (for pricing, costing, etc.), this
    class only increments its internal counter when you explicitly call
    `.step()` after a successful trade.

    Recommended usage pattern:

        strat = TradeCountB(alpha=2.0, min_b=10)
        market = BinaryLMSRMarket(b=strat)
        ...
        result = market.trade(...)
        strat.step()   # advance after each completed trade
    """

    def __init__(self, alpha: float = 1.0, min_b: float = 5.0, max_b: float | None = None):
        if alpha <= 0:
            raise ValueError("alpha must be positive")
        if min_b <= 0:
            raise ValueError("min_b must be positive")
        if max_b is not None and max_b <= min_b:
            raise ValueError("max_b must be greater than min_b")
        self.alpha = float(alpha)
        self.min_b = float(min_b)
        self.max_b = float(max_b) if max_b is not None else None
        self._trade_count = 0

    def __call__(self, q: npt.NDArray[np.floating]) -> float:
        # Do NOT increment here — see class docstring
        raw = self.min_b + self.alpha * self._trade_count
        if self.max_b is not None:
            return min(raw, self.max_b)
        return raw

    def step(self, count: int = 1) -> None:
        """Advance the internal trade counter by `count` (call after each trade)."""
        self._trade_count += count

    def reset(self) -> None:
        """Reset the internal trade counter."""
        self._trade_count = 0

    def __repr__(self) -> str:
        parts = [f"alpha={self.alpha}", f"min_b={self.min_b}"]
        if self.max_b is not None:
            parts.append(f"max_b={self.max_b}")
        return f"TradeCountB({', '.join(parts)})"
