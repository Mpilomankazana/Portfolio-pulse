"""Pipeline entrypoint — wires extract -> transform -> load.

Order: extract_from_csv -> clean_market_prices -> validate_ohlcv ->
calculate_daily_returns -> detect_price_outliers -> ticker->asset_id
lookup -> upsert_market_prices.

Note: validate_ohlcv and detect_price_outliers are not yet implemented
in src/transform/clean.py (both still raise NotImplementedError). This
wiring calls them anyway, per the target design — a run against real
data will fail at that step until those two are built. That failure is
expected at this stage, not a bug in this file.
"""
import logging
from pathlib import Path

import pandas as pd
from sqlalchemy import text

# Importing config first: it loads .env, validates DATABASE_URL, and
# configures logging, before anything below can go wrong.
from src.orchestration import config  # noqa: F401
from src.db import engine
from src.extract.market_data import extract_from_csv
from src.transform.clean import (
    calculate_daily_returns,
    clean_market_prices,
    detect_price_outliers,
    validate_ohlcv,
)
from src.load.loader import upsert_market_prices

logger = logging.getLogger(__name__)

# CSVs to ingest per run. Phase 2 note: move this to config.py (or a
# manifest file) once there's more than a couple of sources, rather than
# hardcoding paths here.
CSV_SOURCES = [
    Path("data/sample_prices.csv"),
]


def _load_ticker_to_asset_id() -> dict[str, int]:
    """Map ticker -> asset_id from the assets table.

    A ticker with no matching row here is a data-setup problem (the asset
    needs to exist in `assets` before prices for it can be loaded) — the
    caller decides whether to skip or fail on rows that don't map.
    """
    with engine.connect() as conn:
        rows = conn.execute(text("SELECT asset_id, ticker FROM assets")).fetchall()
    return {ticker: asset_id for asset_id, ticker in rows}


def _extract_all(sources: list[Path]) -> tuple[pd.DataFrame, list[str]]:
    """Extract from each source, continuing past a single bad source.

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
        return pd.DataFrame(columns=["ticker", "date", "open", "high", "low", "close", "volume"]), failures

    return pd.concat(frames, ignore_index=True), failures


def run() -> None:
    rows_extracted = 0
    rows_after_cleaning = 0
    rows_outliers = 0
    rows_upserted = 0
    extract_failures: list[str] = []

    try:
        # 1. Extract
        raw_df, extract_failures = _extract_all(CSV_SOURCES)
        rows_extracted = len(raw_df)
        if extract_failures:
            logger.warning("%d source(s) failed to extract: %s", len(extract_failures), extract_failures)
        if raw_df.empty:
            logger.warning("No rows extracted from any source — nothing to process.")
            return

        # 2. Transform: clean -> validate -> returns -> outliers, in that order.
        cleaned_df = clean_market_prices(raw_df)
        rows_after_cleaning = len(cleaned_df)
        logger.info(
            "Cleaned %d -> %d rows (%d dropped)",
            rows_extracted,
            rows_after_cleaning,
            rows_extracted - rows_after_cleaning,
        )

        validated_df = validate_ohlcv(cleaned_df)
        returns_df = calculate_daily_returns(validated_df)
        outliers_df = detect_price_outliers(returns_df)
        rows_outliers = int(outliers_df["is_outlier"].sum()) if "is_outlier" in outliers_df else 0
        if rows_outliers:
            logger.warning("%d row(s) flagged as price outliers", rows_outliers)

        # 3. Load: map ticker -> asset_id, then upsert.
        ticker_to_asset_id = _load_ticker_to_asset_id()
        outliers_df = outliers_df.copy()
        outliers_df["asset_id"] = outliers_df["ticker"].map(ticker_to_asset_id)

        unmapped = outliers_df[outliers_df["asset_id"].isna()]["ticker"].unique().tolist()
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
        rows_upserted = len(records)
        logger.info("Upserted %d rows into market_prices", rows_upserted)

    except Exception:
        logger.exception("Pipeline run failed")
        raise
    finally:
        logger.info(
            "Run summary: extracted=%d, after_cleaning=%d, outliers_flagged=%d, upserted=%d, source_failures=%d",
            rows_extracted,
            rows_after_cleaning,
            rows_outliers,
            rows_upserted,
            len(extract_failures),
        )


if __name__ == "__main__":
    run()
