"""Portfolio-level time-series valuation and drawdown metrics.

Portfolio exposure vs. target benchmark (allocation drift) is already
stubbed as calculate_portfolio_allocation_drift in
src/transform/clean.py — not duplicated here.
"""
import pandas as pd


def calculate_portfolio_valuation(
    holdings_df: pd.DataFrame, prices_df: pd.DataFrame
) -> pd.DataFrame:
    """Compute total portfolio market value per day, as a time series.

    Params:
        holdings_df: columns portfolio_id, asset_id, quantity (assumed
            static over the period — if quantities change over time,
            this needs a date-aware holdings history instead; decide
            which case applies to this project's data and document it).
        prices_df: columns asset_id, date, close.

    Returns: columns portfolio_id, date, portfolio_value.

    # TODO: implement:
    #   1. Merge holdings_df with prices_df on asset_id (this produces one
    #      row per holding per date).
    #   2. position_value = quantity * close.
    #   3. Group by (portfolio_id, date), sum position_value ->
    #      portfolio_value.
    #   4. Sort the result by (portfolio_id, date) so it's ready for
    #      calculate_daily_drawdown to consume without re-sorting.
    #   5. Handle an asset_id in holdings_df with no matching price on a
    #      given date (e.g. a gap in market_prices) — decide: forward-fill
    #      the last known price, or exclude that asset from that day's
    #      total (which understates the true value). Document the choice,
    #      since it affects every downstream drawdown/valuation number.
    #   6. Tests: a two-asset portfolio over a few days with hand-computed
    #      expected totals; a day with a missing price for one asset.
    """
    raise NotImplementedError("TODO: implement portfolio valuation time series")


def calculate_daily_drawdown(valuation_df: pd.DataFrame) -> pd.DataFrame:
    """Compute daily drawdown from each portfolio's running peak value.

    Params:
        valuation_df: output of calculate_portfolio_valuation — columns
            portfolio_id, date, portfolio_value, sorted by date within
            each portfolio_id.

    Returns: valuation_df with added columns running_peak, drawdown_pct
    (negative or zero; 0 means at a new high).

    # TODO: implement:
    #   1. Per portfolio_id, compute a running max of portfolio_value:
    #      df.groupby("portfolio_id")["portfolio_value"].cummax() ->
    #      running_peak.
    #   2. drawdown_pct = (portfolio_value - running_peak) / running_peak.
    #      This is <= 0 by construction; a fresh peak day has drawdown_pct
    #      == 0.
    #   3. Guard against running_peak == 0 if a portfolio can legitimately
    #      have zero value at some point (division by zero) — decide
    #      whether that's a real case for this project's data.
    #   4. Tests: a portfolio that rises monotonically (drawdown always 0),
    #      one with a known peak-then-decline sequence with a
    #      hand-calculated expected drawdown at the trough.
    """
    raise NotImplementedError("TODO: implement daily drawdown calculation")
