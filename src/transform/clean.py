"""Cleaning and transformation logic for raw market price data.

Phase 2 target: handle missing prices, null stock splits, timezone
conversion to SAST/UTC, and derived portfolio metrics (daily returns,
weighted return, allocation drift). Write pytest cases for each
function before implementing (TDD requirement).
"""
import logging

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


def clean_market_prices(df: pd.DataFrame) -> pd.DataFrame:
    """Drop/impute missing rows and enforce dtypes."""
    df = df.copy()

    if df.empty:
        return df

    # Normalize ticker first so downstream grouping/filtering is consistent.
    df["ticker"] = df["ticker"].astype(str).str.strip().str.upper()

    # Can't analyze a price-less row — drop rows with no close.
    df = df.dropna(subset=["close"])

    # Missing volume is treated as "no reported volume", not unknown -> 0.
    df["volume"] = df["volume"].fillna(0)

    # Enforce dtypes.
    df["date"] = pd.to_datetime(df["date"])
    for col in ("open", "high", "low", "close", "volume"):
        df[col] = pd.to_numeric(df[col])

    return df.reset_index(drop=True)


def calculate_daily_returns(df: pd.DataFrame) -> pd.DataFrame:
    """Compute daily return per asset from close prices."""
    df = df.copy()
    df = df.sort_values(["ticker", "date"])

    # groupby("ticker") is required here — a bare df["close"].pct_change()
    # would leak the last close of one ticker into the first return of the
    # next when the frame is sorted by ticker then date.
    df["daily_return"] = df.groupby("ticker")["close"].pct_change()

    # A close of 0 would otherwise produce +inf on the next day's return.
    # Use np.nan (not pd.NA) so the column stays float64 — pd.NA would
    # upcast it to object dtype and break downstream np.isinf/numeric checks.
    df["daily_return"] = df["daily_return"].replace([np.inf, -np.inf], np.nan)

    return df.reset_index(drop=True)


def validate_ohlcv(df: pd.DataFrame) -> pd.DataFrame:
    """Reject rows with structurally invalid OHLCV data.

    Expects a cleaned DataFrame (post clean_market_prices) with columns:
    ticker, date, open, high, low, close, volume.

    Policy: DROP invalid rows (mirrors clean_market_prices's drop-on-
    missing-close approach) rather than flag-and-pass-through, so a
    structurally impossible row (e.g. high < low) never reaches
    calculate_daily_returns or the loader. Dropped-row counts are logged
    here so a bad source is visible in the pipeline run summary rather
    than silently disappearing.

    A row is valid iff all of:
      - high >= low
      - high >= max(open, close) and low <= min(open, close)
      - open, high, low, close are all > 0
      - volume >= 0
    """
    df = df.copy()

    if df.empty:
        return df

    is_valid = (
        (df["high"] >= df["low"])
        & (df["high"] >= df[["open", "close"]].max(axis=1))
        & (df["low"] <= df[["open", "close"]].min(axis=1))
        & (df["open"] > 0)
        & (df["high"] > 0)
        & (df["low"] > 0)
        & (df["close"] > 0)
        & (df["volume"] >= 0)
    )

    dropped = int((~is_valid).sum())
    if dropped:
        logger.warning(
            "validate_ohlcv: dropping %d structurally invalid row(s) out of %d",
            dropped,
            len(df),
        )

    return df[is_valid].reset_index(drop=True)


def detect_price_outliers(df: pd.DataFrame, threshold: float = 3.0) -> pd.DataFrame:
    """Flag rows where a day's price move looks anomalous vs. recent history.

    Expects df to already have a `daily_return` column (i.e. run this
    after calculate_daily_returns).

    Policy: FLAG-ONLY. Outliers are marked via an `is_outlier` column but
    never dropped here — a real 20%+ move on genuine news is exactly the
    kind of data an analyst needs to see, not lose. Downstream reporting
    (the pipeline run summary) surfaces the flagged count; deciding what
    to do about a specific flagged row is a human/analyst call, not this
    function's.

    Per ticker, a rolling 20-day mean/std of daily_return is used to
    compute a z-score; a row within the first `min_periods` observations
    for its ticker (not enough history yet) is left unflagged rather than
    guessed at, and a flat series (rolling_std == 0) is treated as not
    an outlier rather than raising a division-by-zero.
    """
    df = df.copy()

    if df.empty:
        df["is_outlier"] = pd.Series(dtype=bool)
        return df

    df = df.sort_values(["ticker", "date"])

    window, min_periods = 20, 5
    grouped_return = df.groupby("ticker")["daily_return"]
    rolling_mean = grouped_return.transform(
        lambda s: s.rolling(window=window, min_periods=min_periods).mean()
    )
    rolling_std = grouped_return.transform(
        lambda s: s.rolling(window=window, min_periods=min_periods).std()
    )

    z_score = (df["daily_return"] - rolling_mean) / rolling_std
    z_score = z_score.replace([np.inf, -np.inf], np.nan)

    df["is_outlier"] = (z_score.abs() > threshold).fillna(False)

    flagged = int(df["is_outlier"].sum())
    if flagged:
        logger.info("detect_price_outliers: flagged %d anomalous row(s)", flagged)

    return df.reset_index(drop=True)


def calculate_unrealized_gain_loss(
    holdings_df: pd.DataFrame, current_prices_df: pd.DataFrame
) -> pd.DataFrame:
    """Compute unrealized gain/loss per holding: (current_price - cost_basis) * quantity.

    Params:
        holdings_df: columns portfolio_id, asset_id, quantity, cost_basis
            (cost_basis = average purchase price per unit).
        current_prices_df: columns asset_id, close (latest close per asset,
            e.g. the most recent row per asset_id from market_prices).

    Returns: holdings_df with added columns: current_price, unrealized_gain_loss,
    unrealized_gain_loss_pct.

    # TODO: implement:
    #   1. Merge holdings_df with current_prices_df on asset_id (left join —
    #      a holding with no matching price should surface as NaN, not
    #      silently drop the row).
    #   2. unrealized_gain_loss = (current_price - cost_basis) * quantity
    #   3. unrealized_gain_loss_pct = (current_price - cost_basis) / cost_basis
    #      Guard against cost_basis == 0 (division by zero).
    #   4. Handle missing current_price (asset with no recent market data):
    #      leave the gain/loss columns as NaN rather than raising, so one
    #      missing price doesn't break the whole portfolio's report.
    #   5. Write tests covering: a gain, a loss, a zero-cost-basis edge
    #      case, and a holding with no matching price row.
    """
    raise NotImplementedError("TODO: implement unrealized gain/loss calculation")


def calculate_portfolio_allocation_drift(
    holdings_df: pd.DataFrame, target_allocation_df: pd.DataFrame
) -> pd.DataFrame:
    """Compute how far a portfolio's actual asset-class mix has drifted from target.

    Params:
        holdings_df: columns portfolio_id, asset_class, market_value
            (market_value = quantity * current_price, computed upstream).
        target_allocation_df: columns portfolio_id, asset_class, target_pct.

    Returns: DataFrame with columns portfolio_id, asset_class, actual_pct,
    target_pct, drift_pct (actual_pct - target_pct).

    # TODO: implement:
    #   1. Group holdings_df by (portfolio_id, asset_class) and sum
    #      market_value, then compute each group's share of that
    #      portfolio's total market_value -> actual_pct.
    #   2. Merge with target_allocation_df on (portfolio_id, asset_class).
    #      An asset_class present in holdings but absent from the target
    #      (or vice versa) should appear with the other side's pct as 0,
    #      not be silently dropped — a fund holding an off-benchmark asset
    #      class is exactly the kind of drift this function exists to catch.
    #   3. drift_pct = actual_pct - target_pct.
    #   4. Write tests: an on-target portfolio (drift ~0), a portfolio
    #      overweight one asset class, and an asset class missing from
    #      one side of the merge.
    """
    raise NotImplementedError("TODO: implement allocation drift calculation")
