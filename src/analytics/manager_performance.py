"""Manager-level performance ranking across quarterly returns.

Depends on calculate_daily_returns (already implemented in
src/transform/clean.py) as its input building block.
"""
import pandas as pd


def calculate_quarterly_returns(daily_returns_df: pd.DataFrame) -> pd.DataFrame:
    """Compound daily returns into a return per manager per quarter.

    Params:
        daily_returns_df: columns manager_id, date, daily_return (this
            requires joining calculate_daily_returns's per-ticker output
            up through portfolio_holdings -> portfolios -> managers to
            get a per-manager daily return series upstream of this
            function — that join/aggregation is not this function's job).

    Returns: columns manager_id, year, quarter, quarterly_return, sorted
    by (manager_id, year, quarter).

    Returns are COMPOUNDED, not summed, within each (manager_id,
    year, quarter) group: (1 + daily_return).prod() - 1. Summing daily
    returns instead of compounding understates genuine multi-day
    performance and is a common bug this choice avoids.

    A NaN daily_return (e.g. a manager's first day in the dataset, with
    no prior close to compare against) is treated as a 0% day via
    fillna(0) before compounding — it contributes a multiplicative
    factor of 1, leaving the quarter's compounded return unaffected by
    a day with no actual return information, rather than excluding the
    day (which would silently shrink the observation window) or
    propagating NaN through the whole quarter.
    """
    if daily_returns_df.empty:
        return pd.DataFrame(columns=["manager_id", "year", "quarter", "quarterly_return"])

    df = daily_returns_df.copy()
    df["date"] = pd.to_datetime(df["date"])
    df["year"] = df["date"].dt.year
    df["quarter"] = df["date"].dt.quarter
    df["daily_return"] = df["daily_return"].fillna(0.0)

    result = (
        df.groupby(["manager_id", "year", "quarter"])["daily_return"]
        .apply(lambda returns: (1 + returns).prod() - 1)
        .reset_index(name="quarterly_return")
    )

    return result.sort_values(["manager_id", "year", "quarter"]).reset_index(drop=True)


def rank_managers_by_performance(quarterly_returns_df: pd.DataFrame) -> pd.DataFrame:
    """Rank managers within each quarter by quarterly_return, descending.

    Params:
        quarterly_returns_df: output of calculate_quarterly_returns.

    Returns: quarterly_returns_df with an added `rank` column (1 = best
    performer that quarter), ranked independently within each quarter.

    Ties use method="min" rather than pandas' default "average", so two
    managers tied for best both get rank 1 (not 1.5) and the next manager
    gets rank 3 — whole-number ranks suited to a leaderboard display,
    where a fractional rank would be meaningless to show.
    """
    if quarterly_returns_df.empty:
        result = quarterly_returns_df.copy()
        result["rank"] = pd.Series(dtype=int)
        return result

    df = quarterly_returns_df.copy()
    df["rank"] = (
        df.groupby(["year", "quarter"])["quarterly_return"]
        .rank(ascending=False, method="min")
        .astype(int)
    )

    return df.sort_values(["year", "quarter", "rank"]).reset_index(drop=True)