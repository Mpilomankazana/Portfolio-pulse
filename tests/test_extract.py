"""Unit tests for src/extract/market_data.py."""
import pandas as pd
import pytest

from src.extract.market_data import extract_from_csv, extract_from_api


class TestExtractFromCsv:
    def test_returns_dataframe(self, raw_csv_path):
        df = extract_from_csv(raw_csv_path)
        assert isinstance(df, pd.DataFrame)

    def test_has_expected_columns(self, raw_csv_path):
        df = extract_from_csv(raw_csv_path)
        expected = {"ticker", "date", "open", "high", "low", "close", "volume"}
        assert expected.issubset(set(df.columns))

    def test_row_count_matches_source(self, raw_csv_path):
        df = extract_from_csv(raw_csv_path)
        assert len(df) == 4

    def test_no_cleaning_applied_yet(self, raw_csv_path):
        # extract_from_csv is documented as returning *raw* data — values should
        # come through untouched (e.g. no forward-filling, no dtype coercion beyond
        # what pandas.read_csv infers by default).
        df = extract_from_csv(raw_csv_path)
        assert df.loc[0, "ticker"] == "AAPL"
        assert df.loc[0, "close"] == pytest.approx(181.2)

    def test_missing_file_raises(self, tmp_path):
        missing_path = tmp_path / "does_not_exist.csv"
        with pytest.raises(FileNotFoundError):
            extract_from_csv(str(missing_path))


class TestExtractFromApi:
    def test_not_yet_implemented(self):
        # Phase 2 stub — flip this test around (assert on real return shape) once
        # the API extractor is implemented.
        with pytest.raises(NotImplementedError):
            extract_from_api("AAPL", "2026-01-01", "2026-01-31")
