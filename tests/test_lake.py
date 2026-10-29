"""Unit tests for src/load/lake.py (temp directories only, no database)."""
import json

import pandas as pd
import pytest

from src.load import lake


def _curated_df(rows):
    return pd.DataFrame(rows, columns=["ticker", "date", "close", "daily_return", "is_outlier"])


def test_land_raw_keeps_everything_as_strings(tmp_path):
    raw = pd.DataFrame({"ticker": ["AAPL"], "date": ["2026-10-01"], "close": ["225.5"], "volume": [None]})
    path = lake.land_raw(raw, tmp_path, "RUN1")

    assert path == tmp_path / "raw" / "market_prices" / "run_id=RUN1" / "data.parquet"
    back = pd.read_parquet(path)
    assert list(back.columns) == ["ticker", "date", "close", "volume"]
    assert back.loc[0, "close"] == "225.5"          # not coerced to a float
    assert pd.isna(back.loc[0, "volume"])


def test_land_raw_runs_do_not_overwrite_each_other(tmp_path):
    raw = pd.DataFrame({"ticker": ["AAPL"], "close": ["1"]})
    a = lake.land_raw(raw, tmp_path, "RUN1")
    b = lake.land_raw(raw, tmp_path, "RUN2")
    assert a != b and a.exists() and b.exists()


def test_write_curated_one_file_per_ticker(tmp_path):
    df = _curated_df([
        ["AAPL", "2026-10-01", 10.0, None, False],
        ["AAPL", "2026-10-02", 11.0, 0.1, False],
        ["MSFT", "2026-10-01", 20.0, None, False],
    ])
    paths = lake.write_curated(df, tmp_path)

    assert sorted(p.parent.name for p in paths) == ["ticker=AAPL", "ticker=MSFT"]
    back = lake.read_curated(tmp_path)
    assert back.groupby("ticker").size().to_dict() == {"AAPL": 2, "MSFT": 1}


def test_write_curated_is_idempotent(tmp_path):
    df = _curated_df([["AAPL", "2026-10-01", 10.0, None, False], ["AAPL", "2026-10-02", 11.0, 0.1, False]])
    lake.write_curated(df, tmp_path)
    lake.write_curated(df, tmp_path)
    assert len(lake.read_curated(tmp_path, "AAPL")) == 2


def test_write_curated_merges_history_and_newest_wins(tmp_path):
    lake.write_curated(_curated_df([
        ["AAPL", "2026-10-01", 10.0, None, False],
        ["AAPL", "2026-10-02", 11.0, 0.1, False],
    ]), tmp_path)
    # Later run: overlaps 10-02 with a corrected close, adds 10-03.
    lake.write_curated(_curated_df([
        ["AAPL", "2026-10-02", 99.0, 8.0, True],
        ["AAPL", "2026-10-03", 12.0, 0.1, False],
    ]), tmp_path)

    back = lake.read_curated(tmp_path, "AAPL").set_index(pd.to_datetime(lake.read_curated(tmp_path, "AAPL")["date"]))
    assert len(back) == 3
    assert back.loc["2026-10-01", "close"] == 10.0     # history kept
    assert back.loc["2026-10-02", "close"] == 99.0     # newest wins
    assert bool(back.loc["2026-10-02", "is_outlier"]) is True
    assert list(back.index) == sorted(back.index)       # stored in date order


def test_read_curated_filters_by_ticker_and_handles_empty(tmp_path):
    assert lake.read_curated(tmp_path).empty
    lake.write_curated(_curated_df([["AAPL", "2026-10-01", 1.0, None, False], ["MSFT", "2026-10-01", 2.0, None, False]]), tmp_path)
    assert set(lake.read_curated(tmp_path, "MSFT")["ticker"]) == {"MSFT"}
    assert lake.read_curated(tmp_path, "NOPE").empty


def test_write_manifest_is_valid_json_and_stringifies_odd_types(tmp_path):
    from pathlib import Path
    odd = Path("/x/y")  # json cannot serialise a Path, so the manifest stores str(odd)
    path = lake.write_manifest({"rows": 3, "where": odd, "failures": ["a"]}, tmp_path, "RUN1")
    assert path == tmp_path / "manifests" / "RUN1.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data == {"failures": ["a"], "rows": 3, "where": str(odd)}


def test_new_run_id_is_sortable_and_filesystem_safe():
    rid = lake.new_run_id()
    assert len(rid) == 16 and rid.endswith("Z") and rid[8] == "T"
    assert all(c not in rid for c in ":/ ")
