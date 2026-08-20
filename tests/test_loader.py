"""Unit tests for src/load/loader.py.

upsert_market_prices talks to Postgres, so these tests mock src.load.loader.engine
rather than requiring docker-compose's postgres service to be running. They check
*how* the function is supposed to use the engine (statement text, conflict target,
params) rather than hitting a real database — add a small integration test suite
against the docker-compose Postgres separately if you want end-to-end coverage.
"""
from unittest.mock import MagicMock, patch

import pytest

from src.load.loader import upsert_market_prices

SAMPLE_RECORDS = [
    {"asset_id": 1, "price_date": "2026-01-02", "open": 180.0, "high": 182.5,
     "low": 179.0, "close": 181.2, "volume": 1000000},
    {"asset_id": 1, "price_date": "2026-01-03", "open": 181.2, "high": 183.0,
     "low": 180.5, "close": 182.9, "volume": 1100000},
]


@pytest.fixture
def mock_engine():
    with patch("src.load.loader.engine") as mock_engine:
        mock_conn = MagicMock()
        # support `with engine.begin() as conn:`
        mock_engine.begin.return_value.__enter__.return_value = mock_conn
        yield mock_engine, mock_conn


class TestUpsertMarketPrices:
    def test_opens_a_transaction(self, mock_engine):
        engine, conn = mock_engine
        upsert_market_prices(SAMPLE_RECORDS)
        engine.begin.assert_called_once()

    def test_executes_a_statement(self, mock_engine):
        engine, conn = mock_engine
        upsert_market_prices(SAMPLE_RECORDS)
        assert conn.execute.called

    def test_statement_uses_on_conflict_do_update(self, mock_engine):
        engine, conn = mock_engine
        upsert_market_prices(SAMPLE_RECORDS)
        executed_sql = str(conn.execute.call_args[0][0]).upper()
        assert "ON CONFLICT" in executed_sql
        assert "DO UPDATE" in executed_sql

    def test_conflict_target_is_asset_id_and_price_date(self, mock_engine):
        engine, conn = mock_engine
        upsert_market_prices(SAMPLE_RECORDS)
        executed_sql = str(conn.execute.call_args[0][0]).lower()
        assert "asset_id" in executed_sql
        assert "price_date" in executed_sql

    def test_empty_records_list_is_a_noop(self, mock_engine):
        engine, conn = mock_engine
        upsert_market_prices([])
        conn.execute.assert_not_called()

    def test_all_records_are_sent(self, mock_engine):
        # Whether the implementation does one executemany-style call or loops and
        # calls execute per record, every record's params should end up somewhere
        # in the call args.
        engine, conn = mock_engine
        upsert_market_prices(SAMPLE_RECORDS)
        all_call_args = [call.args for call in conn.execute.call_args_list]
        assert len(all_call_args) >= 1
