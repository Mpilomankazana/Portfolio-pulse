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
