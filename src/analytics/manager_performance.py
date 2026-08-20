"""Manager-level performance ranking across quarterly returns.

Nothing here exists yet. Depends on calculate_daily_returns (already
implemented in src/transform/clean.py) as its input building block.
"""
import pandas as pd


def calculate_quarterly_returns(daily_returns_df: pd.DataFrame) -> pd.DataFrame:
    """Compound daily returns into a return per manager per quarter.

    Params:
        daily_returns_df: expected columns — manager_id, date, daily_return
            (this requires joining calculate_daily_returns's per-ticker
            output up through portfolio_holdings -> portfolios -> managers
            to get a per-manager daily return series — decide whether that
            aggregation is weighted by holding size or a simple mean, and
            document the choice here, since it changes the result).

    Returns: columns manager_id, year, quarter, quarterly_return.

    # TODO: implement:
    #   1. Add a `quarter` column: pd.PeriodIndex(daily_returns_df["date"],
    #      freq="Q") or (df["date"].dt.year, df["date"].dt.quarter).
    #   2. Compound (not sum) daily returns within each (manager_id,
    #      quarter) group: (1 + daily_return).prod() - 1. Summing daily
    #      returns instead of compounding is a common bug — a test should
    #      catch it by asserting against a hand-computed compounded value.
    #   3. Handle NaN daily_return values (e.g. a manager's first day in
    #      the dataset) — decide whether to treat as 0% for that day
    #      (fillna(0) before compounding) or exclude the day, and document
    #      the choice.
    #   4. Tests: a manager with a known, hand-calculated sequence of daily
    #      returns compounding to a specific quarterly figure; a manager
    #      with a leading NaN day.
    """
    raise NotImplementedError("TODO: implement quarterly return compounding")


def rank_managers_by_performance(quarterly_returns_df: pd.DataFrame) -> pd.DataFrame:
    """Rank managers within each quarter by quarterly_return, descending.

    Params:
        quarterly_returns_df: output of calculate_quarterly_returns.

    Returns: quarterly_returns_df with an added `rank` column (1 = best
    performer that quarter), ranked independently within each quarter.

    # TODO: implement:
    #   1. Group by quarter (year, quarter), rank quarterly_return
    #      descending within each group: .rank(ascending=False, method="min").
    #      Use method="min" (not the pandas default "average") so ties get
    #      whole-number ranks appropriate for a leaderboard display, and
    #      document that choice.
    #   2. Tests: a quarter with a clear ranking, and a quarter with a tie
    #      between two managers to confirm the tie-handling method behaves
    #      as documented.
    """
    raise NotImplementedError("TODO: implement manager ranking")
