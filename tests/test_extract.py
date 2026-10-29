"""Unit tests for src/extract/market_data.py.

extract_from_csv is implemented, so it's tested directly against the
raw_csv_path fixture. extract_from_api talks to the Alpha Vantage API,
so these tests mock requests.get (and time.sleep, for the retry path)
rather than requiring a live network call or a real API key — same
approach test_loader.py takes for mocking the DB engine.
"""
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from datetime import date

from src.extract import market_data
from src.extract.market_data import extract_from_csv, extract_from_api, choose_outputsize


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


def _alpha_vantage_payload(*day_rows):
    """Build a Time Series (Daily) payload from (date, o, h, l, c, v) tuples."""
    return {
        "Meta Data": {"2. Symbol": "AAPL"},
        "Time Series (Daily)": {
            date_str: {
                "1. open": str(o),
                "2. high": str(h),
                "3. low": str(l),
                "4. close": str(c),
                "5. volume": str(v),
            }
            for date_str, o, h, l, c, v in day_rows
        },
    }


def _mock_response(status_code=200, json_data=None, headers=None, text=""):
    response = MagicMock()
    response.status_code = status_code
    response.json.return_value = json_data or {}
    response.headers = headers or {}
    response.text = text
    return response


class TestExtractFromApi:
    def test_missing_api_key_raises_clear_error(self, monkeypatch):
        monkeypatch.delenv("MARKET_API_KEY", raising=False)
        with pytest.raises(RuntimeError, match="MARKET_API_KEY"):
            extract_from_api("AAPL", "2026-01-01", "2026-01-31")

    def test_returns_a_dataframe_with_expected_columns(self, monkeypatch):
        monkeypatch.setenv("MARKET_API_KEY", "fake-key")
        payload = _alpha_vantage_payload(
            ("2026-01-05", 180.0, 182.5, 179.0, 181.2, 1000000),
        )
        with patch("src.extract.market_data.requests.get", return_value=_mock_response(200, payload)):
            df = extract_from_api("AAPL", "2026-01-01", "2026-01-31")
        assert isinstance(df, pd.DataFrame)
        assert list(df.columns) == ["ticker", "date", "open", "high", "low", "close", "volume"]

    def test_maps_fields_and_does_not_coerce_dtypes(self, monkeypatch):
        # Raw passthrough, same as extract_from_csv's "no cleaning here"
        # contract — values come back exactly as the API sent them
        # (strings), with no float/int coercion applied in this layer.
        monkeypatch.setenv("MARKET_API_KEY", "fake-key")
        payload = _alpha_vantage_payload(
            ("2026-01-05", 180.0, 182.5, 179.0, 181.2, 1000000),
        )
        with patch("src.extract.market_data.requests.get", return_value=_mock_response(200, payload)):
            df = extract_from_api("AAPL", "2026-01-01", "2026-01-31")
        row = df.iloc[0]
        assert row["ticker"] == "AAPL"
        assert row["date"] == "2026-01-05"
        assert row["open"] == "180.0"
        assert row["close"] == "181.2"
        assert row["volume"] == "1000000"

    def test_filters_to_requested_date_range(self, monkeypatch):
        monkeypatch.setenv("MARKET_API_KEY", "fake-key")
        payload = _alpha_vantage_payload(
            ("2025-12-31", 1, 1, 1, 1, 1),  # before range
            ("2026-01-15", 2, 2, 2, 2, 2),  # in range
            ("2026-02-01", 3, 3, 3, 3, 3),  # after range
        )
        with patch("src.extract.market_data.requests.get", return_value=_mock_response(200, payload)):
            df = extract_from_api("AAPL", "2026-01-01", "2026-01-31")
        assert df["date"].tolist() == ["2026-01-15"]

    def test_no_data_in_range_returns_empty_dataframe_with_expected_columns(self, monkeypatch):
        monkeypatch.setenv("MARKET_API_KEY", "fake-key")
        payload = _alpha_vantage_payload(("2025-01-01", 1, 1, 1, 1, 1))  # outside range
        with patch("src.extract.market_data.requests.get", return_value=_mock_response(200, payload)):
            df = extract_from_api("AAPL", "2026-01-01", "2026-01-31")
        assert len(df) == 0
        assert list(df.columns) == ["ticker", "date", "open", "high", "low", "close", "volume"]

    def test_empty_time_series_in_response_returns_empty_dataframe(self, monkeypatch):
        monkeypatch.setenv("MARKET_API_KEY", "fake-key")
        payload = {"Meta Data": {}, "Time Series (Daily)": {}}
        with patch("src.extract.market_data.requests.get", return_value=_mock_response(200, payload)):
            df = extract_from_api("DELISTEDCO", "2026-01-01", "2026-01-31")
        assert len(df) == 0
        assert list(df.columns) == ["ticker", "date", "open", "high", "low", "close", "volume"]

    def test_non_200_response_raises_with_ticker_and_status_code(self, monkeypatch):
        monkeypatch.setenv("MARKET_API_KEY", "fake-key")
        with patch(
            "src.extract.market_data.requests.get",
            return_value=_mock_response(404, text="Not Found"),
        ):
            with pytest.raises(RuntimeError, match="AAPL") as exc_info:
                extract_from_api("AAPL", "2026-01-01", "2026-01-31")
        assert "404" in str(exc_info.value)

    def test_429_retries_and_succeeds_using_retry_after_header(self, monkeypatch):
        monkeypatch.setenv("MARKET_API_KEY", "fake-key")
        payload = _alpha_vantage_payload(("2026-01-05", 1, 1, 1, 1, 1))
        rate_limited = _mock_response(429, headers={"Retry-After": "3"})
        success = _mock_response(200, payload)

        with patch(
            "src.extract.market_data.requests.get", side_effect=[rate_limited, success]
        ) as mock_get, patch("src.extract.market_data.time.sleep") as mock_sleep:
            df = extract_from_api("AAPL", "2026-01-01", "2026-01-31")

        assert mock_get.call_count == 2
        mock_sleep.assert_called_once_with(3.0)
        assert len(df) == 1

    def test_429_without_retry_after_backs_off_exponentially(self, monkeypatch):
        monkeypatch.setenv("MARKET_API_KEY", "fake-key")
        payload = _alpha_vantage_payload(("2026-01-05", 1, 1, 1, 1, 1))
        rate_limited = _mock_response(429)  # no Retry-After header
        success = _mock_response(200, payload)

        with patch(
            "src.extract.market_data.requests.get", side_effect=[rate_limited, success]
        ), patch("src.extract.market_data.time.sleep") as mock_sleep:
            extract_from_api("AAPL", "2026-01-01", "2026-01-31")

        mock_sleep.assert_called_once_with(1)  # 2**0 on the first retry

    def test_429_exceeding_max_retries_raises(self, monkeypatch):
        monkeypatch.setenv("MARKET_API_KEY", "fake-key")
        always_rate_limited = _mock_response(429)

        with patch(
            "src.extract.market_data.requests.get", return_value=always_rate_limited
        ), patch("src.extract.market_data.time.sleep"):
            with pytest.raises(RuntimeError, match="429"):
                extract_from_api("AAPL", "2026-01-01", "2026-01-31")

    def test_request_uses_timeout(self, monkeypatch):
        monkeypatch.setenv("MARKET_API_KEY", "fake-key")
        payload = _alpha_vantage_payload(("2026-01-05", 1, 1, 1, 1, 1))
        with patch(
            "src.extract.market_data.requests.get", return_value=_mock_response(200, payload)
        ) as mock_get:
            extract_from_api("AAPL", "2026-01-01", "2026-01-31")
        assert mock_get.call_args.kwargs["timeout"] == 10

class TestOutputsize:
    """compact works on a free Alpha Vantage key; full may not, so only ask for it when needed."""

    @pytest.fixture(autouse=True)
    def fixed_today(self, monkeypatch):
        monkeypatch.setattr(market_data, "_today", lambda: date(2026, 10, 28))

    def test_recent_start_uses_compact(self):
        assert choose_outputsize("2026-09-28") == "compact"  # 30 days back

    def test_boundary_is_inclusive(self):
        assert choose_outputsize("2026-06-30") == "compact"  # exactly 120 days
        assert choose_outputsize("2026-06-29") == "full"     # 121 days

    def test_old_start_uses_full(self):
        assert choose_outputsize("2025-01-01") == "full"

    def test_request_sends_the_chosen_outputsize(self, monkeypatch):
        monkeypatch.setenv("MARKET_API_KEY", "fake-key")
        payload = _alpha_vantage_payload(("2026-10-20", 1, 1, 1, 1, 1))
        with patch("src.extract.market_data.requests.get", return_value=_mock_response(200, payload)) as get:
            extract_from_api("AAPL", "2026-10-01", "2026-10-28")
        assert get.call_args.kwargs["params"]["outputsize"] == "compact"

    def test_explicit_outputsize_wins(self, monkeypatch):
        monkeypatch.setenv("MARKET_API_KEY", "fake-key")
        payload = _alpha_vantage_payload(("2026-10-20", 1, 1, 1, 1, 1))
        with patch("src.extract.market_data.requests.get", return_value=_mock_response(200, payload)) as get:
            extract_from_api("AAPL", "2026-10-01", "2026-10-28", outputsize="full")
        assert get.call_args.kwargs["params"]["outputsize"] == "full"


class TestProviderMessages:
    @pytest.mark.parametrize("key", ["Information", "Note", "Error Message"])
    def test_provider_explanation_is_logged_and_result_is_empty(self, monkeypatch, caplog, key):
        monkeypatch.setenv("MARKET_API_KEY", "fake-key")
        payload = {key: "daily quota reached"}
        with patch("src.extract.market_data.requests.get", return_value=_mock_response(200, payload)):
            with caplog.at_level("WARNING"):
                df = extract_from_api("AAPL", "2026-10-01", "2026-10-28")
        assert df.empty
        assert "daily quota reached" in caplog.text and "AAPL" in caplog.text

    def test_plain_empty_response_logs_nothing(self, monkeypatch, caplog):
        monkeypatch.setenv("MARKET_API_KEY", "fake-key")
        with patch("src.extract.market_data.requests.get", return_value=_mock_response(200, {"Time Series (Daily)": {}})):
            with caplog.at_level("WARNING"):
                extract_from_api("AAPL", "2026-10-01", "2026-10-28")
        assert caplog.text == ""
