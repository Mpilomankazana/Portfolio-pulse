"""Unit tests for src/transform/clean.py — written before implementation (TDD).

These encode one reasonable reading of the docstrings in clean.py:
  - clean_market_prices: drop rows with no close price (can't analyze a price-less
    row), impute missing volume as 0, normalize ticker to upper/stripped, and
    coerce `date` to a real datetime dtype.
  - calculate_daily_returns: pct_change() of `close`, computed per ticker, with
    each ticker's first day having a NaN return (nothing to compare it to).

If you intend different behaviour (e.g. forward-filling instead of dropping),
adjust the assertions below to match your spec, then implement clean.py to
make them pass.
"""
import numpy as np
import pandas as pd
import pytest

from src.transform.clean import clean_market_prices, calculate_daily_returns


class TestCleanMarketPrices:
    def test_drops_rows_with_missing_close(self, raw_prices_df):
        cleaned = clean_market_prices(raw_prices_df)
        assert cleaned["close"].isna().sum() == 0
        assert len(cleaned) == 3  # the MSFT row with close=None is dropped

    def test_imputes_missing_volume_to_zero(self, raw_prices_df):
        cleaned = clean_market_prices(raw_prices_df)
        assert cleaned["volume"].isna().sum() == 0
        aapl_jan2 = cleaned[(cleaned["ticker"] == "AAPL") & (cleaned["date"] == "2026-01-02")]
        assert aapl_jan2.iloc[0]["volume"] == 0

    def test_normalizes_ticker_case_and_whitespace(self, raw_prices_df):
        cleaned = clean_market_prices(raw_prices_df)
        assert set(cleaned["ticker"].unique()) == {"AAPL", "MSFT"}

    def test_date_column_is_datetime_dtype(self, raw_prices_df):
        cleaned = clean_market_prices(raw_prices_df)
        assert pd.api.types.is_datetime64_any_dtype(cleaned["date"])

    def test_price_columns_are_numeric(self, raw_prices_df):
        cleaned = clean_market_prices(raw_prices_df)
        for col in ("open", "high", "low", "close"):
            assert pd.api.types.is_numeric_dtype(cleaned[col])

    def test_empty_input_returns_empty_dataframe(self):
        empty = pd.DataFrame(columns=["ticker", "date", "open", "high", "low", "close", "volume"])
        cleaned = clean_market_prices(empty)
        assert len(cleaned) == 0


class TestCalculateDailyReturns:
    def test_adds_daily_return_column(self, clean_prices_df):
        result = calculate_daily_returns(clean_prices_df)
        assert "daily_return" in result.columns

    def test_first_day_per_ticker_has_no_return(self, clean_prices_df):
        result = calculate_daily_returns(clean_prices_df)
        first_aapl = result[result["ticker"] == "AAPL"].sort_values("date").iloc[0]
        assert pd.isna(first_aapl["daily_return"])

    def test_return_calculation_is_correct(self, clean_prices_df):
        result = calculate_daily_returns(clean_prices_df)
        aapl = result[result["ticker"] == "AAPL"].sort_values("date").reset_index(drop=True)
        # close goes 180.0 -> 189.0 -> 180.0
        assert aapl.loc[1, "daily_return"] == pytest.approx((189.0 - 180.0) / 180.0)
        assert aapl.loc[2, "daily_return"] == pytest.approx((180.0 - 189.0) / 189.0)

    def test_returns_are_calculated_independently_per_ticker(self, clean_prices_df):
        # MSFT's first-day return must not be computed against AAPL's last close —
        # this is the main bug TDD here is meant to catch (a naive df-wide pct_change
        # without a groupby("ticker") would leak across tickers).
        result = calculate_daily_returns(clean_prices_df)
        first_msft = result[result["ticker"] == "MSFT"].sort_values("date").iloc[0]
        assert pd.isna(first_msft["daily_return"])

    def test_no_infinite_returns_from_zero_close(self):
        df = pd.DataFrame(
            [
                {"ticker": "X", "date": pd.Timestamp("2026-01-01"), "close": 0.0},
                {"ticker": "X", "date": pd.Timestamp("2026-01-02"), "close": 10.0},
            ]
        )
        result = calculate_daily_returns(df)
        assert not np.isinf(result["daily_return"]).any()
