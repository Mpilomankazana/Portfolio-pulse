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