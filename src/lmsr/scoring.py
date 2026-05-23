"""
Calibration Scoring Functions for Prediction Markets

Implements the scoring rules and decomposition discussed in DESIGN.md as the
"most mathematically interesting part for an internal forecasting tool".

These are pure functions that can be used:
- Standalone (for leaderboards, analysis)
- At resolution time to score every trade
- For post-hoc evaluation of forecasters

Key references from the design conversation:
- Brier Score (quadratic)
- Log Score (information-theoretic)
- Murphy (1973) decomposition of the Brier score:
      Brier = Reliability − Resolution + Uncertainty
"""

from __future__ import annotations

from typing import Tuple

import numpy as np


def brier_score(forecasts: np.ndarray, outcomes: np.ndarray) -> np.ndarray:
    """
    Compute Brier scores for a set of probabilistic forecasts.

    BS_i = (p_i - o_i)²

    Lower is better. Ranges from 0 (perfect) to 1 (maximally wrong).

    Parameters
    ----------
    forecasts : array-like
        Forecast probabilities for the positive event (in [0, 1]).
    outcomes : array-like
        Realized outcomes (1 or 0).

    Returns
    -------
    scores : ndarray
        Brier score for each forecast.
    """
    p = np.asarray(forecasts, dtype=float)
    o = np.asarray(outcomes, dtype=float)
    return (p - o) ** 2


def log_score(forecasts: np.ndarray, outcomes: np.ndarray, eps: float = 1e-15) -> np.ndarray:
    """
    Compute logarithmic scores.

    LS_i = o_i * log(p_i) + (1 - o_i) * log(1 - p_i)

    Higher is better (less negative). This is the log-likelihood of the outcome
    under the forecast. It heavily penalizes being confidently wrong.

    Parameters
    ----------
    forecasts : array-like
        Forecast probabilities.
    outcomes : array-like
        Binary outcomes (1 or 0).
    eps : float
        Small value to clip probabilities for numerical stability.

    Returns
    -------
    scores : ndarray
        Log score for each forecast.
    """
    p = np.asarray(forecasts, dtype=float)
    o = np.asarray(outcomes, dtype=float)

    p = np.clip(p, eps, 1 - eps)
    return o * np.log(p) + (1 - o) * np.log(1 - p)


def brier_decomposition(
    forecasts: np.ndarray,
    outcomes: np.ndarray,
    n_bins: int = 10,
) -> dict[str, float]:
    """
    Murphy decomposition of the Brier score.

    Returns:
        {
            "brier": mean Brier score,
            "reliability": Reliability component (lower is better),
            "resolution": Resolution component (higher is better),
            "uncertainty": Uncertainty (base rate variance),
        }

    The decomposition satisfies:
        mean(Brier) = Reliability - Resolution + Uncertainty

    This is extremely useful for diagnosing forecaster behavior:
    - High reliability + low resolution → well calibrated but timid
    - Low reliability + high resolution → bold but miscalibrated
    - Both good → skilled forecaster

    Parameters
    ----------
    forecasts : array-like
        Forecast probabilities in [0, 1].
    outcomes : array-like
        Binary outcomes (1 or 0).
    n_bins : int
        Number of bins to use for the reliability-resolution calculation.

    Returns
    -------
    decomposition : dict
    """
    p = np.asarray(forecasts, dtype=float).ravel()
    o = np.asarray(outcomes, dtype=float).ravel()

    if len(p) != len(o):
        raise ValueError("forecasts and outcomes must have the same length")

    mean_brier = float(np.mean(brier_score(p, o)))

    # Base rate
    base_rate = float(np.mean(o))
    uncertainty = base_rate * (1 - base_rate)

    # Bin the forecasts
    bins = np.linspace(0, 1, n_bins + 1)
    bin_indices = np.digitize(p, bins[1:-1], right=True)  # 0 to n_bins-1

    reliability = 0.0
    resolution = 0.0
    total_weight = 0.0

    for k in range(n_bins):
        mask = bin_indices == k
        if not np.any(mask):
            continue

        weight = np.sum(mask) / len(p)
        bin_forecast = np.mean(p[mask])
        bin_outcome = np.mean(o[mask])

        reliability += weight * (bin_forecast - bin_outcome) ** 2
        resolution += weight * (bin_outcome - base_rate) ** 2
        total_weight += weight

    decomposition = {
        "brier": mean_brier,
        "reliability": float(reliability),
        "resolution": float(resolution),
        "uncertainty": uncertainty,
    }

    # Sanity check: the decomposition should approximately reconstruct mean Brier
    reconstructed = reliability - resolution + uncertainty
    decomposition["reconstruction_error"] = abs(mean_brier - reconstructed)

    return decomposition


def mean_brier_score(forecasts: np.ndarray, outcomes: np.ndarray) -> float:
    """Convenience wrapper returning the mean Brier score."""
    return float(np.mean(brier_score(forecasts, outcomes)))


def mean_log_score(forecasts: np.ndarray, outcomes: np.ndarray) -> float:
    """Convenience wrapper returning the mean log score."""
    return float(np.mean(log_score(forecasts, outcomes)))


# ------------------------------------------------------------------
# Convenience class for tracking a forecaster over time
# ------------------------------------------------------------------

class ForecasterScores:
    """
    Helper to accumulate forecasts and outcomes, then compute scores
    and the full Murphy decomposition on demand.
    """

    def __init__(self):
        self.forecasts: list[float] = []
        self.outcomes: list[float] = []

    def add(self, forecast: float, outcome: int | float):
        """Record one forecast and its eventual outcome."""
        self.forecasts.append(float(forecast))
        self.outcomes.append(float(outcome))

    def compute(self, n_bins: int = 10) -> dict:
        """Return all scoring metrics."""
        f = np.array(self.forecasts)
        o = np.array(self.outcomes)

        return {
            "n": len(f),
            "mean_brier": mean_brier_score(f, o),
            "mean_log_score": mean_log_score(f, o),
            "decomposition": brier_decomposition(f, o, n_bins=n_bins),
        }

    def reset(self):
        self.forecasts.clear()
        self.outcomes.clear()
