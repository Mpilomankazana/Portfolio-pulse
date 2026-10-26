"""Risk and benchmark-relative analytics on return series.

Pure functions over pandas Series of periodic simple returns (e.g. the
daily_return column from calculate_daily_returns, aggregated to one
series per portfolio upstream). No database access here.
"""
from statistics import NormalDist

import numpy as np
import pandas as pd

TRADING_DAYS_PER_YEAR = 252


def _clean(returns: pd.Series) -> pd.Series:
    s = pd.Series(returns, dtype="float64").replace([np.inf, -np.inf], np.nan).dropna()
    if s.empty:
        raise ValueError("returns contains no usable (finite, non-NaN) observations")
    return s


def _check_confidence(confidence: float) -> None:
    if not 0.0 < confidence < 1.0:
        raise ValueError(f"confidence must be strictly between 0 and 1, got {confidence}")


def calculate_var(returns: pd.Series, confidence: float = 0.95, method: str = "historical") -> float:
    """One-period Value at Risk, returned as a POSITIVE loss fraction.

    A result of 0.021 at 95% means: on 95% of periods the loss was no worse
    than 2.1%.

    method:
      "historical"  empirical (1 - confidence) quantile of the returns; makes
                    no distributional assumption.
      "parametric"  normal approximation, mean + z * std (sample std, ddof=1).
                    Needs at least 2 observations. Understates tail risk when
                    returns are fat-tailed.

    A negative VaR (every observed return was a gain at that quantile) is
    clamped to 0.0: "no loss at this confidence level".

    Raises ValueError for confidence outside (0, 1), an unknown method, or no
    usable observations.
    """
    _check_confidence(confidence)
    s = _clean(returns)

    if method == "historical":
        cutoff = float(np.quantile(s, 1.0 - confidence))
    elif method == "parametric":
        if len(s) < 2:
            raise ValueError("parametric VaR needs at least 2 observations")
        z = NormalDist().inv_cdf(1.0 - confidence)
        cutoff = float(s.mean() + z * s.std(ddof=1))
    else:
        raise ValueError(f"unknown method {method!r}; use 'historical' or 'parametric'")

    return max(0.0, -cutoff)


def calculate_cvar(returns: pd.Series, confidence: float = 0.95) -> float:
    """Historical Conditional VaR (expected shortfall): the average loss on the
    periods at or beyond the VaR cutoff, as a POSITIVE loss fraction.

    Always >= calculate_var(..., method="historical"). Clamped at 0.0.
    """
    _check_confidence(confidence)
    s = _clean(returns)
    cutoff = float(np.quantile(s, 1.0 - confidence))
    tail = s[s <= cutoff]
    return max(0.0, -float(tail.mean()))


def compare_to_benchmark(
    portfolio_returns: pd.Series,
    benchmark_returns: pd.Series,
    periods_per_year: int = TRADING_DAYS_PER_YEAR,
    risk_free_rate: float = 0.0,
) -> dict:
    """Benchmark-relative statistics for a portfolio.

    Both inputs are periodic simple returns indexed by date. They are aligned
    on the index (inner join) and any period missing from either side is
    dropped; at least 2 shared periods are required.

    Returns a dict:
      excess_return_annualized  (mean portfolio - mean benchmark) * periods_per_year
      tracking_error            std(portfolio - benchmark, ddof=1) * sqrt(periods_per_year)
      information_ratio         excess_return_annualized / tracking_error
                                (NaN if tracking_error is 0)
      beta                      cov(p, b) / var(b)  (NaN if var(b) is 0)
      alpha_annualized          Jensen's alpha: ((mean_p - rf) - beta * (mean_b - rf))
                                * periods_per_year, rf = risk_free_rate / periods_per_year
                                (NaN if beta is NaN)
      correlation               Pearson correlation (NaN if either side is flat)
      n_periods                 number of aligned periods used

    risk_free_rate is an ANNUAL rate (0.07 = 7%). Annualization is arithmetic
    (mean * periods), the usual convention for these ratios.
    """
    if periods_per_year <= 0:
        raise ValueError("periods_per_year must be positive")

    aligned = pd.concat(
        [pd.Series(portfolio_returns, dtype="float64"), pd.Series(benchmark_returns, dtype="float64")],
        axis=1,
        join="inner",
        keys=["p", "b"],
    ).replace([np.inf, -np.inf], np.nan).dropna()

    if len(aligned) < 2:
        raise ValueError("need at least 2 aligned periods to compare against the benchmark")

    p, b = aligned["p"], aligned["b"]
    active = p - b

    excess = float((p.mean() - b.mean()) * periods_per_year)
    tracking_error = float(active.std(ddof=1) * np.sqrt(periods_per_year))
    info_ratio = excess / tracking_error if tracking_error > 0 else float("nan")

    var_b = float(b.var(ddof=1))
    if var_b > 0:
        beta = float(p.cov(b) / var_b)
        rf = risk_free_rate / periods_per_year
        alpha = float(((p.mean() - rf) - beta * (b.mean() - rf)) * periods_per_year)
    else:
        beta = alpha = float("nan")

    correlation = float(p.corr(b)) if p.std(ddof=1) > 0 and b.std(ddof=1) > 0 else float("nan")

    return {
        "excess_return_annualized": excess,
        "tracking_error": tracking_error,
        "information_ratio": info_ratio,
        "beta": beta,
        "alpha_annualized": alpha,
        "correlation": correlation,
        "n_periods": int(len(aligned)),
    }