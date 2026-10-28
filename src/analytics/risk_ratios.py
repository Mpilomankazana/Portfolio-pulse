"""Risk-adjusted performance ratios.

Depends on calculate_quarterly_returns / a per-manager daily return
series (see src/analytics/manager_performance.py) as upstream input —
this module takes return series as given rather than deriving them.
"""
import numpy as np
import pandas as pd


def calculate_sharpe_ratio(
    daily_returns_df: pd.DataFrame,
    risk_free_rate: float = 0.0,
    trading_days_per_year: int = 252,
) -> pd.DataFrame:
    """Compute the annualized Sharpe ratio per manager from daily returns.

    Params:
        daily_returns_df: columns manager_id, date, daily_return (same
            shape consumed by calculate_quarterly_returns).
        risk_free_rate: ANNUAL risk-free rate as a decimal (e.g. 0.05
            for 5%), not a daily rate — it's converted to a daily rate
            internally by dividing by trading_days_per_year. Defaults
            to 0, i.e. plain excess-of-zero Sharpe.
        trading_days_per_year: used both to de-annualize risk_free_rate
            and to annualize the ratio itself (the sqrt(N) scaling
            below). Defaults to 252, the standard US trading-day count.

    Returns: columns manager_id, sharpe_ratio, one row per manager_id
    present in the input, sorted by manager_id.

    Sharpe ratio = mean(daily_excess_return) / std(daily_excess_return)
    * sqrt(trading_days_per_year), where daily_excess_return is
    daily_return minus the de-annualized risk_free_rate. The sqrt(N)
    factor annualizes a ratio computed from daily data, which is the
    standard convention — comparing an un-annualized daily ratio
    against, say, an annual benchmark figure would be meaningless.

    Standard deviation uses ddof=1 (sample std, pandas' default), not
    the population std, since a manager's observed daily returns are a
    sample of their return-generating process, not its entirety.

    A manager with zero return variance (std == 0 — e.g. only one
    observation, or every day identical) has sharpe_ratio NaN rather
    than raising or returning +/-inf: the ratio is undefined when
    there's no variance to normalize by, not infinitely good or bad.
    A NaN daily_return is treated the same way calculate_quarterly_returns
    treats it (fillna(0.0)) before computing the ratio, for consistency
    with the rest of this project's return-handling convention.
    """
    if daily_returns_df.empty:
        return pd.DataFrame(columns=["manager_id", "sharpe_ratio"])

    df = daily_returns_df.copy()
    df["daily_return"] = df["daily_return"].fillna(0.0)

    daily_risk_free = risk_free_rate / trading_days_per_year
    df["excess_return"] = df["daily_return"] - daily_risk_free

    grouped = df.groupby("manager_id")["excess_return"]
    mean_excess = grouped.mean()
    std_excess = grouped.std(ddof=1)

    safe_std = std_excess.replace(0.0, np.nan)
    sharpe = (mean_excess / safe_std) * np.sqrt(trading_days_per_year)

    result = sharpe.reset_index(name="sharpe_ratio")
    return result.sort_values("manager_id").reset_index(drop=True)


def calculate_sortino_ratio(
    daily_returns_df: pd.DataFrame,
    risk_free_rate: float = 0.0,
    trading_days_per_year: int = 252,
) -> pd.DataFrame:
    """Compute the annualized Sortino ratio per manager from daily returns.

    Params: same shape/meaning as calculate_sharpe_ratio's — see that
    docstring for daily_returns_df, risk_free_rate and
    trading_days_per_year.

    Returns: columns manager_id, sortino_ratio, one row per manager_id
    present in the input, sorted by manager_id.

    Sortino ratio = mean(daily_excess_return) / downside_deviation
    * sqrt(trading_days_per_year), where downside_deviation is the
    ddof=1 sample standard deviation of ONLY the excess returns that
    fall below the target (0 — i.e. negative excess returns), not all
    excess returns. This is the key difference from Sharpe: Sortino
    doesn't penalize upside volatility, on the view that a manager
    swinging to big gains isn't "risk" in the same sense that swinging
    to big losses is.

    A manager with no observations below the target (every excess
    return >= 0) has no downside deviation to compute. That manager's
    sortino_ratio is NaN rather than 0 or +inf: there's no downside
    data to normalize by, so the ratio is undefined, not literally
    infinite upside-only performance. The same applies to a manager
    whose below-target excess returns are all identical (downside
    deviation == 0) — also NaN, for the same zero-variance reasoning
    as calculate_sharpe_ratio.

    A NaN daily_return is fillna(0.0) first, matching this project's
    return-handling convention (see calculate_sharpe_ratio).
    """
    if daily_returns_df.empty:
        return pd.DataFrame(columns=["manager_id", "sortino_ratio"])

    df = daily_returns_df.copy()
    df["daily_return"] = df["daily_return"].fillna(0.0)

    daily_risk_free = risk_free_rate / trading_days_per_year
    df["excess_return"] = df["daily_return"] - daily_risk_free

    mean_excess = df.groupby("manager_id")["excess_return"].mean()

    downside = df[df["excess_return"] < 0]
    downside_deviation = downside.groupby("manager_id")["excess_return"].std(ddof=1)
    # Reindex onto the full set of manager_ids so a manager with zero
    # downside observations still gets a row (of NaN) rather than being
    # dropped from the result entirely.
    downside_deviation = downside_deviation.reindex(mean_excess.index)

    safe_downside_deviation = downside_deviation.replace(0.0, np.nan)
    sortino = (mean_excess / safe_downside_deviation) * np.sqrt(trading_days_per_year)

    result = sortino.reset_index(name="sortino_ratio")
    return result.sort_values("manager_id").reset_index(drop=True)