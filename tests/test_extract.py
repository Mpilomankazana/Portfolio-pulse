"""Unit tests for src/extract/market_data.py.

extract_from_csv is implemented, so it's tested directly against the
raw_csv_path fixture. extract_from_api is still a Phase 2 stub, so its
test is skipped until it's implemented.
"""
import pandas as pd
import pytest

from src.extract.market_data import extract_from_csv, extract_from_api


class TestExtractFromCsv:
    def test_returns_a_dataframe(self, raw_csv_path):
        df = extract_from_csv(raw_csv_path)
        assert isinstance(df, pd.DataFrame)

    def test_has_expected_columns(self, raw_csv_path):
        df = extract_from_csv(raw_csv_path)
        expected = {"ticker", "date", "open", "high", "low", "close", "volume"}
        assert expected.issubset(set(df.columns))

    def test_row_count_matches_source_csv(self, raw_csv_path):
        df = extract_from_csv(raw_csv_path)
        assert len(df) == 4  # 2 AAPL rows + 2 MSFT rows

    def test_does_not_apply_any_cleaning(self, raw_csv_path):
        # extract stays raw — no type coercion, filtering, or normalization here.
        # That's clean_market_prices's job (see test_clean.py).
        df = extract_from_csv(raw_csv_path)
        assert df["ticker"].tolist() == ["AAPL", "AAPL", "MSFT", "MSFT"]


class TestExtractFromApi:
    def test_not_yet_implemented(self):
        pytest.skip("Phase 2: implement extract_from_api, then replace this test")

    def test_raises_until_implemented(self):
        with pytest.raises(NotImplementedError):
            extract_from_api("AAPL", "2026-01-01", "2026-01-31")
