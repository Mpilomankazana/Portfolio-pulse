"""Orchestration tests for src/orchestration/run_pipeline.py.

Every collaborator that touches the outside world (CSV/API extractors, the
database loader, the lake directory) is replaced, so these test only the
wiring: which source is used, what gets passed on, and how failures are
handled.
"""
import json
from datetime import date

import pandas as pd
import pytest

from src.orchestration import run_pipeline as rp


def _raw(tickers=("AAPL",), days=("2026-10-01", "2026-10-02", "2026-10-05")):
    rows = []
    for t in tickers:
        for i, d in enumerate(days):
            c = 100 + i
            rows.append({"ticker": t, "date": d, "open": str(c), "high": str(c + 1),
                         "low": str(c - 1), "close": str(c), "volume": "1000"})
    return pd.DataFrame(rows)


@pytest.fixture
def env(monkeypatch, tmp_path):
    """Neutral config + recording fakes. Returns a namespace the tests inspect."""
    class Env:
        upserts: list = []
        api_calls: list = []

    e = Env()
    e.upserts, e.api_calls = [], []
    monkeypatch.setattr(rp.config, "DATA_SOURCE", "csv")
    monkeypatch.setattr(rp.config, "LAKE_ENABLED", True)
    monkeypatch.setattr(rp.config, "LAKE_DIR", tmp_path / "lake")
    monkeypatch.setattr(rp.config, "API_TICKERS", ["AAPL", "MSFT"])
    monkeypatch.setattr(rp.config, "API_LOOKBACK_DAYS", 30)
    monkeypatch.setattr(rp.config, "API_PAUSE_SECONDS", 0)
    monkeypatch.setattr(rp, "_today", lambda: date(2026, 10, 26))
    monkeypatch.setattr(rp, "get_ticker_to_asset_id", lambda: {"AAPL": 1, "MSFT": 2})
    monkeypatch.setattr(rp, "upsert_market_prices", lambda records: e.upserts.extend(records))
    monkeypatch.setattr(rp, "extract_from_csv", lambda path: _raw())

    def fake_api(ticker, start, end):
        e.api_calls.append((ticker, start, end))
        return _raw((ticker,))
    monkeypatch.setattr(rp, "extract_from_api", fake_api)
    e.lake = tmp_path / "lake"
    return e


def test_csv_source_loads_rows_and_writes_lake_and_manifest(env):
    summary = rp.run()

    assert summary["status"] == "success"
    assert summary["source"] == "csv"
    assert summary["rows_extracted"] == summary["rows_upserted"] == len(env.upserts) == 3
    assert {r["asset_id"] for r in env.upserts} == {1}
    assert env.api_calls == []                                  # CSV mode never calls the API

    assert (env.lake / "raw" / "market_prices").exists()
    assert (env.lake / "curated" / "market_prices" / "ticker=AAPL" / "data.parquet").exists()
    manifests = list((env.lake / "manifests").glob("*.json"))
    assert len(manifests) == 1
    on_disk = json.loads(manifests[0].read_text())
    assert on_disk["status"] == "success" and on_disk["rows_upserted"] == 3


def test_api_source_calls_extractor_per_ticker_with_date_range(env, monkeypatch):
    monkeypatch.setattr(rp.config, "DATA_SOURCE", "api")
    monkeypatch.setattr(rp, "extract_from_csv", lambda path: pytest.fail("CSV extractor must not run in api mode"))

    summary = rp.run()

    assert env.api_calls == [("AAPL", "2026-09-26", "2026-10-26"), ("MSFT", "2026-09-26", "2026-10-26")]
    assert summary["source"] == "api" and summary["status"] == "success"
    assert {r["asset_id"] for r in env.upserts} == {1, 2}


def test_api_failure_for_one_ticker_does_not_stop_the_others(env, monkeypatch):
    monkeypatch.setattr(rp.config, "DATA_SOURCE", "api")

    def flaky(ticker, start, end):
        if ticker == "AAPL":
            raise RuntimeError("HTTP 500")
        return _raw((ticker,))
    monkeypatch.setattr(rp, "extract_from_api", flaky)

    summary = rp.run()

    assert summary["status"] == "partial"
    assert len(summary["source_failures"]) == 1 and "AAPL" in summary["source_failures"][0]
    assert {r["asset_id"] for r in env.upserts} == {2}


def test_empty_api_response_counts_as_a_failure_not_silent_success(env, monkeypatch):
    """Alpha Vantage answers rate limits with HTTP 200 and no data."""
    monkeypatch.setattr(rp.config, "DATA_SOURCE", "api")
    monkeypatch.setattr(rp, "extract_from_api", lambda t, s, e: pd.DataFrame(columns=rp.EXPECTED_COLUMNS))

    summary = rp.run()

    assert summary["status"] == "no_data"
    assert len(summary["source_failures"]) == 2
    assert "no rows" in summary["source_failures"][0]
    assert env.upserts == []
    # A no_data run still leaves a manifest explaining why.
    assert json.loads(next((env.lake / "manifests").glob("*.json")).read_text())["status"] == "no_data"


def test_pauses_between_api_tickers_but_not_after_the_last(env, monkeypatch):
    monkeypatch.setattr(rp.config, "DATA_SOURCE", "api")
    monkeypatch.setattr(rp.config, "API_TICKERS", ["AAPL", "MSFT", "JPM"])
    monkeypatch.setattr(rp.config, "API_PAUSE_SECONDS", 7)
    sleeps = []
    monkeypatch.setattr(rp.time, "sleep", sleeps.append)

    rp.run()

    assert sleeps == [7, 7]


def test_lake_failure_never_blocks_the_database_load(env, monkeypatch):
    def boom(*a, **k):
        raise PermissionError("read-only filesystem")
    monkeypatch.setattr(rp.lake, "land_raw", boom)
    monkeypatch.setattr(rp.lake, "write_curated", boom)

    summary = rp.run()

    assert summary["rows_upserted"] == 3 and summary["status"] == "success"
    assert any("land_raw" in e for e in summary["lake_errors"])
    assert any("write_curated" in e for e in summary["lake_errors"])


def test_lake_disabled_writes_nothing(env, monkeypatch):
    monkeypatch.setattr(rp.config, "LAKE_ENABLED", False)
    rp.run()
    assert not env.lake.exists()
    assert len(env.upserts) == 3


def test_unmapped_tickers_are_skipped_and_reported(env, monkeypatch):
    monkeypatch.setattr(rp, "extract_from_csv", lambda path: _raw(("AAPL", "ZZZZ")))
    summary = rp.run()
    assert summary["unmapped_tickers"] == ["ZZZZ"]
    assert {r["asset_id"] for r in env.upserts} == {1}


def test_loader_failure_propagates_and_manifest_records_failed(env, monkeypatch):
    def db_down(records):
        raise RuntimeError("connection refused")
    monkeypatch.setattr(rp, "upsert_market_prices", db_down)

    with pytest.raises(RuntimeError, match="connection refused"):
        rp.run()

    manifest = json.loads(next((env.lake / "manifests").glob("*.json")).read_text())
    assert manifest["status"] == "failed"
    assert manifest["rows_upserted"] == 0
