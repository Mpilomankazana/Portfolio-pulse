"""Pipeline entrypoint — wires extract -> (land raw) -> transform -> load.

Order: extract (CSV or API) -> land raw Parquet -> clean_market_prices ->
validate_ohlcv -> calculate_daily_returns -> detect_price_outliers ->
write curated Parquet -> ticker->asset_id lookup -> upsert_market_prices ->
write run manifest.

Source is chosen by config.DATA_SOURCE: "csv" reads config.CSV_SOURCES
(default data/sample_prices.csv); "api" calls Alpha Vantage once per ticker
in config.API_TICKERS. Both extractors return the same columns, so
everything after extraction is identical.

Tickers must exist in the `assets` table first; run
`python -m src.orchestration.seed` on a fresh database.

Lake writes (src/load/lake.py) are best-effort: a failure there is logged
and recorded in the manifest, but never fails the database load.
"""
import logging
import sys
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pandas as pd

# Importing config first: it loads .env, validates settings, and
# configures logging, before anything below can go wrong.
from src.orchestration import config
from src.extract.market_data import extract_from_api, extract_from_csv
from src.transform.clean import (
    calculate_daily_returns,
    clean_market_prices,
    detect_price_outliers,
    validate_ohlcv,
)
from src.load import lake
from src.load.loader import get_ticker_to_asset_id, upsert_market_prices

logger = logging.getLogger(__name__)

EXPECTED_COLUMNS = ["ticker", "date", "open", "high", "low", "close", "volume"]


def _empty_raw() -> pd.DataFrame:
    return pd.DataFrame(columns=EXPECTED_COLUMNS)


def _today() -> date:
    return datetime.now(timezone.utc).date()


def _extract_all(sources: list[Path]) -> tuple[pd.DataFrame, list[str]]:
    """Extract from each CSV, continuing past a single bad source.

    Returns the concatenated raw DataFrame and a list of failure messages
    (one per source that couldn't be read) so one bad file doesn't abort
    the whole run.
    """
    frames = []
    failures: list[str] = []

    for source in sources:
        try:
            df = extract_from_csv(str(source))
            logger.info("Extracted %d rows from %s", len(df), source)
            frames.append(df)
        except Exception as exc:  # noqa: BLE001 — deliberately broad: log and continue
            msg = f"{source}: {exc}"
            logger.error("Extraction failed for %s", msg)
            failures.append(msg)

    if not frames:
        return _empty_raw(), failures

    return pd.concat(frames, ignore_index=True), failures


def _extract_api_all(tickers: list[str], lookback_days: int, pause_seconds: float) -> tuple[pd.DataFrame, list[str]]:
    """Extract each ticker from the API, continuing past a single bad ticker.

    A ticker that raises, or comes back empty, is recorded as a failure.
    Empty matters: Alpha Vantage answers rate-limit and quota problems with
    HTTP 200 and no price data, which extract_from_api returns as an empty
    frame, so "no rows" is treated as a failure instead of a silent success.
    """
    end = _today()
    start = end - timedelta(days=lookback_days)
    frames = []
    failures: list[str] = []

    for i, ticker in enumerate(tickers):
        if i and pause_seconds > 0:
            time.sleep(pause_seconds)
        try:
            df = extract_from_api(ticker, start.isoformat(), end.isoformat())
        except Exception as exc:  # noqa: BLE001
            msg = f"{ticker}: {exc}"
            logger.error("API extraction failed for %s", msg)
            failures.append(msg)
            continue
        if df.empty:
            msg = f"{ticker}: API returned no rows for {start} to {end} (rate limit, quota, or no data)"
            logger.warning(msg)
            failures.append(msg)
            continue
        logger.info("Extracted %d rows for %s from API", len(df), ticker)
        frames.append(df)

    if not frames:
        return _empty_raw(), failures
    return pd.concat(frames, ignore_index=True), failures


def _extract() -> tuple[pd.DataFrame, list[str]]:
    if config.DATA_SOURCE == "api":
        return _extract_api_all(config.API_TICKERS, config.API_LOOKBACK_DAYS, config.API_PAUSE_SECONDS)
    return _extract_all(config.CSV_SOURCES)


def _lake_step(summary: dict, label: str, fn, *args):
    """Run one lake write; on failure log it, note it in the summary, carry on."""
    if not config.LAKE_ENABLED:
        return None
    try:
        return fn(*args)
    except Exception as exc:  # noqa: BLE001 — lake is best-effort by design
        logger.warning("Lake step '%s' failed (database load unaffected): %s", label, exc)
        summary["lake_errors"].append(f"{label}: {exc}")
        return None


def run() -> dict:
    """Run the pipeline once. Returns the run summary (also written as the manifest)."""
    run_id = lake.new_run_id()
    started = datetime.now(timezone.utc)
    summary: dict = {
        "run_id": run_id,
        "source": config.DATA_SOURCE,
        "started_at": started.isoformat(),
        "rows_extracted": 0,
        "rows_after_cleaning": 0,
        "rows_outliers": 0,
        "rows_upserted": 0,
        "unmapped_tickers": [],
        "source_failures": [],
        "lake_errors": [],
        "lake_paths": {},
        "status": "failed",
    }

    try:
        # 1. Extract
        raw_df, extract_failures = _extract()
        summary["rows_extracted"] = len(raw_df)
        summary["source_failures"] = extract_failures
        if extract_failures:
            logger.warning("%d source(s) failed to extract: %s", len(extract_failures), extract_failures)
        if raw_df.empty:
            logger.warning("No rows extracted from any source — nothing to process.")
            summary["status"] = "no_data"
            return summary

        # 1b. Land raw data untouched, before any transformation.
        raw_path = _lake_step(summary, "land_raw", lake.land_raw, raw_df, config.LAKE_DIR, run_id)
        if raw_path:
            summary["lake_paths"]["raw"] = str(raw_path)

        # 2. Transform: clean -> validate -> returns -> outliers, in that order.
        cleaned_df = clean_market_prices(raw_df)
        summary["rows_after_cleaning"] = len(cleaned_df)
        logger.info(
            "Cleaned %d -> %d rows (%d dropped)",
            summary["rows_extracted"],
            summary["rows_after_cleaning"],
            summary["rows_extracted"] - summary["rows_after_cleaning"],
        )

        validated_df = validate_ohlcv(cleaned_df)
        returns_df = calculate_daily_returns(validated_df)
        outliers_df = detect_price_outliers(returns_df)
        summary["rows_outliers"] = int(outliers_df["is_outlier"].sum()) if "is_outlier" in outliers_df else 0
        if summary["rows_outliers"]:
            logger.warning("%d row(s) flagged as price outliers", summary["rows_outliers"])

        curated_paths = _lake_step(summary, "write_curated", lake.write_curated, outliers_df, config.LAKE_DIR)
        if curated_paths:
            summary["lake_paths"]["curated"] = [str(p) for p in curated_paths]

        # 3. Load: map ticker -> asset_id, then upsert.
        ticker_to_asset_id = get_ticker_to_asset_id()
        outliers_df = outliers_df.copy()
        outliers_df["asset_id"] = outliers_df["ticker"].map(ticker_to_asset_id)

        unmapped = outliers_df[outliers_df["asset_id"].isna()]["ticker"].unique().tolist()
        summary["unmapped_tickers"] = unmapped
        if unmapped:
            logger.warning(
                "%d ticker(s) have no matching asset_id and will be skipped: %s",
                len(unmapped),
                unmapped,
            )

        loadable_df = outliers_df.dropna(subset=["asset_id"])
        records = [
            {
                "asset_id": int(row.asset_id),
                "price_date": row.date.date() if hasattr(row.date, "date") else row.date,
                "open": row.open,
                "high": row.high,
                "low": row.low,
                "close": row.close,
                "volume": row.volume,
            }
            for row in loadable_df.itertuples(index=False)
        ]

        upsert_market_prices(records)
        summary["rows_upserted"] = len(records)
        summary["status"] = "success" if not extract_failures else "partial"
        logger.info("Upserted %d rows into market_prices", summary["rows_upserted"])
        return summary

    except Exception:
        logger.exception("Pipeline run failed")
        raise
    finally:
        summary["finished_at"] = datetime.now(timezone.utc).isoformat()
        logger.info(
            "Run summary: status=%s source=%s extracted=%d after_cleaning=%d outliers_flagged=%d upserted=%d source_failures=%d",
            summary["status"],
            summary["source"],
            summary["rows_extracted"],
            summary["rows_after_cleaning"],
            summary["rows_outliers"],
            summary["rows_upserted"],
            len(summary["source_failures"]),
        )
        manifest_path = _lake_step(summary, "write_manifest", lake.write_manifest, summary, config.LAKE_DIR, run_id)
        if manifest_path:
            logger.info("Run manifest written to %s", manifest_path)


class NoDataError(RuntimeError):
    """The run finished without loading anything (every source failed or returned no rows)."""


def check_summary(summary: dict) -> dict:
    """Turn a finished run's summary into a verdict callers can act on.

    "no_data" raises NoDataError: nothing was loaded, which is a failure even
    though no exception happened inside run() (an API quota or rate limit
    comes back as an empty answer, not an error). "partial" and lake errors
    only warn, because the database load itself did succeed.
    """
    status = summary.get("status")
    if status == "no_data":
        raise NoDataError(
            f"run {summary.get('run_id')} loaded no data from source '{summary.get('source')}': "
            f"{summary.get('source_failures') or 'sources returned no rows'}"
        )
    if status == "partial":
        logger.warning(
            "Run %s was PARTIAL: %d source(s) failed: %s",
            summary.get("run_id"), len(summary["source_failures"]), summary["source_failures"],
        )
    if summary.get("lake_errors"):
        logger.warning("Run %s had lake errors (database load unaffected): %s", summary.get("run_id"), summary["lake_errors"])
    return summary


def main() -> int:
    """Command-line entry: exit 0 on success or partial, 1 when nothing was loaded."""
    try:
        check_summary(run())
    except NoDataError as exc:
        logger.error("%s", exc)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
