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

from src.transform.clean import (
    calculate_daily_returns,
    clean_market_prices,
    detect_price_outliers,
    validate_ohlcv,
)


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


class TestValidateOhlcv:
    def _valid_row(self, **overrides):
        row = {
            "ticker": "AAPL", "date": pd.Timestamp("2026-01-02"),
            "open": 180.0, "high": 182.5, "low": 179.0, "close": 181.2, "volume": 1000000,
        }
        row.update(overrides)
        return row

    def test_valid_row_passes_through_unchanged(self):
        df = pd.DataFrame([self._valid_row()])
        result = validate_ohlcv(df)
        assert len(result) == 1

    def test_drops_row_where_high_below_low(self):
        df = pd.DataFrame([self._valid_row(high=170.0, low=179.0)])
        result = validate_ohlcv(df)
        assert len(result) == 0

    def test_drops_row_where_high_below_open_or_close(self):
        df = pd.DataFrame([self._valid_row(high=180.5, close=181.2)])  # close > high
        result = validate_ohlcv(df)
        assert len(result) == 0

    def test_drops_row_with_negative_price(self):
        df = pd.DataFrame([self._valid_row(open=-5.0)])
        result = validate_ohlcv(df)
        assert len(result) == 0

    def test_drops_row_with_zero_price(self):
        df = pd.DataFrame([self._valid_row(close=0.0)])
        result = validate_ohlcv(df)
        assert len(result) == 0

    def test_drops_row_with_negative_volume(self):
        df = pd.DataFrame([self._valid_row(volume=-100)])
        result = validate_ohlcv(df)
        assert len(result) == 0

    def test_keeps_valid_rows_and_drops_invalid_in_mixed_input(self):
        df = pd.DataFrame([self._valid_row(), self._valid_row(high=100.0, low=179.0)])
        result = validate_ohlcv(df)
        assert len(result) == 1

    def test_empty_input_returns_empty_dataframe(self):
        empty = pd.DataFrame(columns=["ticker", "date", "open", "high", "low", "close", "volume"])
        result = validate_ohlcv(empty)
        assert len(result) == 0


class TestDetectPriceOutliers:
    def _flat_series(self, ticker="AAPL", n=25, start_price=100.0):
        dates = pd.date_range("2026-01-01", periods=n, freq="D")
        return pd.DataFrame({"ticker": ticker, "date": dates, "close": start_price})

    def test_planted_outlier_is_flagged(self):
        df = self._flat_series(n=25)
        # Plant a 50% jump on the last day.
        df.loc[df.index[-1], "close"] = 150.0
        returns_df = calculate_daily_returns(df)
        result = detect_price_outliers(returns_df)
        assert result.iloc[-1]["is_outlier"] == True  # noqa: E712

    def test_normal_noise_is_not_flagged(self):
        df = self._flat_series(n=25)
        # Small realistic day-to-day noise, no big jumps.
        noise = [0, 1, -1, 0.5, -0.5] * 5
        df["close"] = df["close"] + noise
        returns_df = calculate_daily_returns(df)
        result = detect_price_outliers(returns_df)
        assert result["is_outlier"].sum() == 0

    def test_insufficient_history_is_not_flagged(self):
        # Fewer than min_periods observations for this ticker — should not
        # be flagged even with an extreme move, since there's no baseline yet.
        df = pd.DataFrame({
            "ticker": "NEW",
            "date": pd.date_range("2026-01-01", periods=3, freq="D"),
            "close": [100.0, 100.0, 200.0],
        })
        returns_df = calculate_daily_returns(df)
        result = detect_price_outliers(returns_df)
        assert result["is_outlier"].sum() == 0

    def test_flat_series_zero_std_is_not_flagged(self):
        df = self._flat_series(n=25)  # perfectly flat, rolling_std == 0
        returns_df = calculate_daily_returns(df)
        result = detect_price_outliers(returns_df)
        assert result["is_outlier"].sum() == 0

    def test_empty_input_returns_empty_with_is_outlier_column(self):
        empty = pd.DataFrame(columns=["ticker", "date", "close", "daily_return"])
        result = detect_price_outliers(empty)
        assert "is_outlier" in result.columns
        assert len(result) == 0