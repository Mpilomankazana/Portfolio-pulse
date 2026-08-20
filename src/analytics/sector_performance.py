"""Sector-level performance analytics: dividends vs. unrealized gains/losses.

Sectors in scope per the PortfolioPulse spec: Consumer Electronics, Energy,
Entertainment, Financials, Healthcare, Technology.

Requires the schema additions drafted in sql/schema.sql (assets.sector,
dividends table) to be applied before these functions can run against
real database-sourced data — until then, callers supply DataFrames with
the shapes documented below directly (e.g. from a join done elsewhere).
"""
import numpy as np
import pandas as pd


def calculate_sector_dividends_vs_gains(
    dividends_df: pd.DataFrame,
    holdings_with_gains_df: pd.DataFrame,
    as_of: str | pd.Timestamp | None = None,
) -> pd.DataFrame:
    """Roll up annual dividends collected vs. unrealized gains/losses, by sector.

    Params:
        dividends_df: columns — asset_id, sector, dividend_amount,
            payment_date. One row per dividend payment.
        holdings_with_gains_df: columns — asset_id, sector,
            unrealized_gain_loss (output of
            src.transform.clean.calculate_unrealized_gain_loss, joined with
            each asset's sector).
        as_of: reference date for the trailing-12-month dividend window.
            Defaults to the latest payment_date in dividends_df (or today,
            if dividends_df is empty).

    Returns: DataFrame with columns sector, annual_dividends,
    total_unrealized_gain_loss, dividend_to_gain_ratio. A sector present
    in either input appears in the result, with 0 on whichever side it's
    missing from.

    "Annual" is defined as trailing 12 months from `as_of`, not calendar
    year — a dividend paid exactly 12 months before `as_of` is included;
    anything older is excluded.

    dividend_to_gain_ratio is annual_dividends / total_unrealized_gain_loss.
    When the denominator is 0, the ratio is NaN (undefined, not infinite)
    rather than raising. A negative total_unrealized_gain_loss produces a
    negative ratio — a sector with real dividend income sitting on an
    unrealized loss legitimately reads as a negative ratio here.
    """
    dividends_df = dividends_df.copy()
    holdings_with_gains_df = holdings_with_gains_df.copy()

    if as_of is None:
        if dividends_df.empty:
            as_of = pd.Timestamp.today().normalize()
        else:
            as_of = pd.to_datetime(dividends_df["payment_date"]).max()
    else:
        as_of = pd.to_datetime(as_of)

    window_start = as_of - pd.Timedelta(days=365)

    if not dividends_df.empty:
        dividends_df["payment_date"] = pd.to_datetime(dividends_df["payment_date"])
        trailing = dividends_df[
            (dividends_df["payment_date"] > window_start)
            & (dividends_df["payment_date"] <= as_of)
        ]
    else:
        trailing = dividends_df

    if trailing.empty:
        div_by_sector = pd.DataFrame(columns=["sector", "annual_dividends"])
    else:
        div_by_sector = (
            trailing.groupby("sector")["dividend_amount"]
            .sum()
            .reset_index()
            .rename(columns={"dividend_amount": "annual_dividends"})
        )

    if holdings_with_gains_df.empty:
        gains_by_sector = pd.DataFrame(columns=["sector", "total_unrealized_gain_loss"])
    else:
        gains_by_sector = (
            holdings_with_gains_df.groupby("sector")["unrealized_gain_loss"]
            .sum()
            .reset_index()
            .rename(columns={"unrealized_gain_loss": "total_unrealized_gain_loss"})
        )

    merged = pd.merge(div_by_sector, gains_by_sector, on="sector", how="outer")
    merged["annual_dividends"] = merged["annual_dividends"].fillna(0.0).astype(float)
    merged["total_unrealized_gain_loss"] = (
        merged["total_unrealized_gain_loss"].fillna(0.0).astype(float)
    )

    # Divide by a NaN'd-out denominator rather than 0 directly — dividing
    # by 0.0 in an object-dtype column (which can appear after an outer
    # merge on an all-empty side) raises ZeroDivisionError instead of
    # producing inf/nan, so this sidesteps that rather than relying on
    # float semantics alone.
    safe_denominator = merged["total_unrealized_gain_loss"].replace(0.0, np.nan)
    merged["dividend_to_gain_ratio"] = merged["annual_dividends"] / safe_denominator

    return merged.sort_values("sector").reset_index(drop=True)


def calculate_sector_exposure(holdings_df: pd.DataFrame) -> pd.DataFrame:
    """Compute each sector's share of total portfolio market value.

    Params:
        holdings_df: columns portfolio_id, sector, market_value.

    Returns: columns portfolio_id, sector, sector_pct. A null/missing
    sector is surfaced as an explicit "Unclassified" sector rather than
    being dropped, so its market value still counts toward the total.
    An empty input returns an empty result with the expected columns.
    """
    if holdings_df.empty:
        return pd.DataFrame(columns=["portfolio_id", "sector", "sector_pct"])

    df = holdings_df.copy()
    df["sector"] = df["sector"].fillna("Unclassified")

    sector_sums = (
        df.groupby(["portfolio_id", "sector"])["market_value"].sum().reset_index()
    )
    portfolio_totals = (
        df.groupby("portfolio_id")["market_value"]
        .sum()
        .reset_index()
        .rename(columns={"market_value": "total_market_value"})
    )

    merged = pd.merge(sector_sums, portfolio_totals, on="portfolio_id")
    merged["sector_pct"] = np.where(
        merged["total_market_value"] == 0,
        0.0,
        merged["market_value"] / merged["total_market_value"] * 100,
    )

    return merged[["portfolio_id", "sector", "sector_pct"]].reset_index(drop=True)
