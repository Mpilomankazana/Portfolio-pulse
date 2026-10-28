"""Idempotent load logic into PostgreSQL (ON CONFLICT DO UPDATE)."""
from sqlalchemy import text
from src.db import engine


def upsert_market_prices(records: list[dict]) -> None:
    """Batch upsert into market_prices, keyed on (asset_id, price_date).

    Each record is a dict with keys: asset_id, price_date, open, high,
    low, close, volume. Uses ON CONFLICT (asset_id, price_date) DO UPDATE
    so reruns of the same day's ingestion overwrite rather than duplicate.
    Runs inside a single transaction — engine.begin() commits on success
    and rolls back automatically if any statement raises.
    """
    if not records:
        return

    stmt = text(
        """
        INSERT INTO market_prices (asset_id, price_date, open, high, low, close, volume)
        VALUES (:asset_id, :price_date, :open, :high, :low, :close, :volume)
        ON CONFLICT (asset_id, price_date) DO UPDATE SET
            open = EXCLUDED.open,
            high = EXCLUDED.high,
            low = EXCLUDED.low,
            close = EXCLUDED.close,
            volume = EXCLUDED.volume
        """
    )

    with engine.begin() as conn:
        conn.execute(stmt, records)


def get_ticker_to_asset_id() -> dict[str, int]:
    """Map ticker -> asset_id from the assets table.

    A ticker with no row here is a data-setup problem (the asset must exist
    before prices for it can be loaded); the caller decides whether to skip
    or fail on rows that don't map.
    """
    with engine.connect() as conn:
        rows = conn.execute(text("SELECT asset_id, ticker FROM assets")).fetchall()
    return {ticker: asset_id for asset_id, ticker in rows}
