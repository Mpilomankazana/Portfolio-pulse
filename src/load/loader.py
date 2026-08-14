"""Idempotent load logic into PostgreSQL (ON CONFLICT DO UPDATE)."""
from sqlalchemy import text
from src.db import engine


def upsert_market_prices(records: list[dict]) -> None:
    """Batch upsert into market_prices, keyed on (asset_id, price_date).

    Stub for Phase 2 — implement with an executemany-style upsert using
    PostgreSQL's ON CONFLICT DO UPDATE to avoid duplicate rows on rerun.
    """
    raise NotImplementedError("Phase 2: implement idempotent upsert")
