"""Portfolio-level time-series valuation and drawdown metrics.

Portfolio exposure vs. target benchmark (allocation drift) is already
implemented as calculate_portfolio_allocation_drift in
src/transform/clean.py — not duplicated here.
"""
import logging

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


def calculate_portfolio_valuation(
    holdings_df: pd.DataFrame, prices_df: pd.DataFrame
) -> pd.DataFrame:
    """Compute total portfolio market value per day, as a time series.

    Params:
        holdings_df: columns portfolio_id, asset_id, quantity (assumed
            static over the period — this project does not yet track a
            date-aware holdings history, so a change in quantity over
            time isn't represented here).
        prices_df: columns asset_id, date, close.

    Returns: columns portfolio_id, date, portfolio_value, sorted by
    (portfolio_id, date).

    Policy for a missing price on a given date: EXCLUDE that asset's
    contribution from that day's total rather than forward-filling a
    stale price. This is simpler to reason about and avoids valuing a
    portfolio using a price that may be materially out of date — the
    trade-off is that a day with a genuine data gap for one asset will
    understate the portfolio's true value for that day. Missing
    coverage is logged so it's visible rather than silent.
    """
    if holdings_df.empty or prices_df.empty:
        return pd.DataFrame(columns=["portfolio_id", "date", "portfolio_value"])

    merged = holdings_df.merge(prices_df, on="asset_id", how="inner")

    covered_assets = set(merged["asset_id"].unique())
    held_assets = set(holdings_df["asset_id"].unique())
    uncovered = held_assets - covered_assets
    if uncovered:
        logger.warning(
            "calculate_portfolio_valuation: %d asset_id(s) have no price "
            "data at all and are excluded entirely: %s",
            len(uncovered),
            sorted(uncovered),
        )

    merged["position_value"] = merged["quantity"] * merged["close"]

    valuation = (
        merged.groupby(["portfolio_id", "date"])["position_value"]
        .sum()
        .reset_index()
        .rename(columns={"position_value": "portfolio_value"})
    )

    return valuation.sort_values(["portfolio_id", "date"]).reset_index(drop=True)


def calculate_daily_drawdown(valuation_df: pd.DataFrame) -> pd.DataFrame:
    """Compute daily drawdown from each portfolio's running peak value.

    Params:
        valuation_df: output of calculate_portfolio_valuation — columns
            portfolio_id, date, portfolio_value.

    Returns: valuation_df with added columns running_peak, drawdown_pct
    (<= 0; 0 means at a new high, sitting exactly at the running peak).
    Sorted by (portfolio_id, date) regardless of input order, since the
    running peak is only meaningful in chronological order.

    A running_peak of 0 (a portfolio that was worth nothing at some
    point) makes the percentage undefined rather than a real drawdown —
    that row's drawdown_pct is NaN rather than raising or reporting an
    infinite/misleading value.
    """
    if valuation_df.empty:
        result = valuation_df.copy()
        result["running_peak"] = pd.Series(dtype=float)
        result["drawdown_pct"] = pd.Series(dtype=float)
        return result

    df = valuation_df.sort_values(["portfolio_id", "date"]).copy()

    df["running_peak"] = df.groupby("portfolio_id")["portfolio_value"].cummax()

    safe_peak = df["running_peak"].replace(0, np.nan)
    df["drawdown_pct"] = (df["portfolio_value"] - df["running_peak"]) / safe_peak

    return df.reset_index(drop=True)