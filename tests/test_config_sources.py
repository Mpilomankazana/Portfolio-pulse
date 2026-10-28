"""Tests for CSV_SOURCES parsing in src/orchestration/config.py."""
from pathlib import Path

from src.orchestration import config


def test_unset_falls_back_to_sample_file():
    assert config._parse_csv_sources(None) == [config.PROJECT_ROOT / "data" / "sample_prices.csv"]
    assert config._parse_csv_sources("") == config._parse_csv_sources(None)
    assert config._parse_csv_sources(" , ,") == config._parse_csv_sources(None)


def test_comma_separated_relative_paths_resolve_against_project_root():
    result = config._parse_csv_sources("data/a.csv, data/b.csv")
    assert result == [config.PROJECT_ROOT / "data" / "a.csv", config.PROJECT_ROOT / "data" / "b.csv"]


def test_absolute_paths_are_kept_as_is():
    abs_path = Path("/srv/feeds/prices.csv")
    assert config._parse_csv_sources(str(abs_path)) == [abs_path]


import pytest


def test_parse_tickers_uppercases_strips_and_dedupes_in_order():
    assert config._parse_tickers(" aapl, MSFT ,,aapl,jpm ") == ["AAPL", "MSFT", "JPM"]
    assert config._parse_tickers(None) == []
    assert config._parse_tickers("") == []


def test_csv_source_needs_no_api_settings():
    config.check_data_source("csv", [], None)  # must not raise


def test_api_source_requires_tickers_and_key():
    with pytest.raises(RuntimeError, match="API_TICKERS"):
        config.check_data_source("api", [], "key")
    with pytest.raises(RuntimeError, match="MARKET_API_KEY"):
        config.check_data_source("api", ["AAPL"], None)
    config.check_data_source("api", ["AAPL"], "key")  # fully configured: fine


def test_unknown_data_source_is_rejected():
    with pytest.raises(RuntimeError, match="DATA_SOURCE"):
        config.check_data_source("kafka", [], None)
