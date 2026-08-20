"""Pipeline entrypoint — wires extract -> transform -> load.

Phase 3 target: wrap this in an APScheduler job for daily runs, and
add data quality checks (e.g. alert on negative/missing close prices).
"""


def run() -> None:
    # TODO: wire the end-to-end pipeline, in this order:
    #   1. from src.orchestration.config import ... (once config.py is
    #      implemented) to get logging configured before anything else runs.
    #   2. Extract: call extract_from_csv (or extract_from_api once built)
    #      for each configured ticker/source. Log how many rows came back
    #      per source, and continue past a single failed ticker rather than
    #      aborting the whole run — collect failures and report them at
    #      the end so one bad source doesn't block everyone else's data.
    #   3. Transform: run clean_market_prices, then validate_ohlcv, then
    #      calculate_daily_returns, then detect_price_outliers (once those
    #      are implemented) in that order — each expects the previous
    #      step's output shape.
    #   4. Load: map cleaned rows to the market_prices schema (ticker ->
    #      asset_id lookup against the assets table — decide where that
    #      lookup lives) and call upsert_market_prices.
    #   5. Log a run summary: rows extracted, rows dropped in cleaning,
    #      outliers flagged, rows upserted, and any per-ticker failures.
    #   6. Wrap step 2-4 in a try/except that logs the failure and re-raises
    #      (or exits non-zero) so a scheduler (APScheduler/cron) or CI can
    #      detect a failed run rather than silently doing nothing.
    print("Pipeline stub — implement extract/transform/load calls here.")


if __name__ == "__main__":
    run()
