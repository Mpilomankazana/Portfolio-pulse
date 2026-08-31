"""Unit tests for src/analytics/valuation.py."""
import numpy as np
import pandas as pd
import pytest

from src.analytics.valuation import calculate_daily_drawdown, calculate_portfolio_valuation


class TestCalculatePortfolioValuation:
    def test_two_asset_portfolio_hand_computed_totals(self):
        holdings = pd.DataFrame([
            {"portfolio_id": 1, "asset_id": 1, "quantity": 10},
            {"portfolio_id": 1, "asset_id": 2, "quantity": 5},
        ])
        prices = pd.DataFrame([
            {"asset_id": 1, "date": "2026-01-01", "close": 100.0},
            {"asset_id": 2, "date": "2026-01-01", "close": 50.0},
            {"asset_id": 1, "date": "2026-01-02", "close": 105.0},
            {"asset_id": 2, "date": "2026-01-02", "close": 52.0},
        ])
        result = calculate_portfolio_valuation(holdings, prices)

        day1 = result[result["date"] == "2026-01-01"].iloc[0]
        day2 = result[result["date"] == "2026-01-02"].iloc[0]
        # day1: 10*100 + 5*50 = 1250
        assert day1["portfolio_value"] == pytest.approx(1250.0)
        # day2: 10*105 + 5*52 = 1310
        assert day2["portfolio_value"] == pytest.approx(1310.0)

    def test_missing_price_for_one_asset_excludes_it_from_that_day(self):
        holdings = pd.DataFrame([
            {"portfolio_id": 1, "asset_id": 1, "quantity": 10},
            {"portfolio_id": 1, "asset_id": 2, "quantity": 5},
        ])
        # asset_id 2 has no price on 2026-01-02 at all.
        prices = pd.DataFrame([
            {"asset_id": 1, "date": "2026-01-01", "close": 100.0},
            {"asset_id": 2, "date": "2026-01-01", "close": 50.0},
            {"asset_id": 1, "date": "2026-01-02", "close": 105.0},
        ])
        result = calculate_portfolio_valuation(holdings, prices)
        day2 = result[result["date"] == "2026-01-02"].iloc[0]
        # Only asset_id 1 counted: 10*105 = 1050 (asset_id 2 excluded, not forward-filled)
        assert day2["portfolio_value"] == pytest.approx(1050.0)

    def test_multiple_portfolios_are_independent(self):
        holdings = pd.DataFrame([
            {"portfolio_id": 1, "asset_id": 1, "quantity": 10},
            {"portfolio_id": 2, "asset_id": 1, "quantity": 2},
        ])
        prices = pd.DataFrame([
            {"asset_id": 1, "date": "2026-01-01", "close": 100.0},
        ])
        result = calculate_portfolio_valuation(holdings, prices)
        p1 = result[result["portfolio_id"] == 1].iloc[0]
        p2 = result[result["portfolio_id"] == 2].iloc[0]
        assert p1["portfolio_value"] == pytest.approx(1000.0)
        assert p2["portfolio_value"] == pytest.approx(200.0)

    def test_result_sorted_by_portfolio_and_date(self):
        holdings = pd.DataFrame([{"portfolio_id": 1, "asset_id": 1, "quantity": 1}])
        prices = pd.DataFrame([
            {"asset_id": 1, "date": "2026-01-03", "close": 10.0},
            {"asset_id": 1, "date": "2026-01-01", "close": 10.0},
            {"asset_id": 1, "date": "2026-01-02", "close": 10.0},
        ])
        result = calculate_portfolio_valuation(holdings, prices)
        assert list(result["date"]) == ["2026-01-01", "2026-01-02", "2026-01-03"]

    def test_empty_holdings_returns_empty_with_expected_columns(self):
        holdings = pd.DataFrame(columns=["portfolio_id", "asset_id", "quantity"])
        prices = pd.DataFrame(columns=["asset_id", "date", "close"])
        result = calculate_portfolio_valuation(holdings, prices)
        assert len(result) == 0
        assert list(result.columns) == ["portfolio_id", "date", "portfolio_value"]


class TestCalculateDailyDrawdown:
    def test_monotonically_rising_portfolio_has_zero_drawdown_always(self):
        valuation = pd.DataFrame([
            {"portfolio_id": 1, "date": "2026-01-01", "portfolio_value": 1000.0},
            {"portfolio_id": 1, "date": "2026-01-02", "portfolio_value": 1100.0},
            {"portfolio_id": 1, "date": "2026-01-03", "portfolio_value": 1250.0},
        ])
        result = calculate_daily_drawdown(valuation)
        assert (result["drawdown_pct"] == 0.0).all()

    def test_peak_then_decline_hand_calculated_trough(self):
        valuation = pd.DataFrame([
            {"portfolio_id": 1, "date": "2026-01-01", "portfolio_value": 1000.0},
            {"portfolio_id": 1, "date": "2026-01-02", "portfolio_value": 1200.0},  # peak
            {"portfolio_id": 1, "date": "2026-01-03", "portfolio_value": 900.0},   # trough
            {"portfolio_id": 1, "date": "2026-01-04", "portfolio_value": 1000.0},  # partial recovery
        ])
        result = calculate_daily_drawdown(valuation)
        trough = result[result["date"] == "2026-01-03"].iloc[0]
        assert trough["running_peak"] == pytest.approx(1200.0)
        # (900 - 1200) / 1200 = -0.25
        assert trough["drawdown_pct"] == pytest.approx(-0.25)

        recovery = result[result["date"] == "2026-01-04"].iloc[0]
        assert recovery["running_peak"] == pytest.approx(1200.0)  # peak still holds
        assert recovery["drawdown_pct"] == pytest.approx((1000.0 - 1200.0) / 1200.0)

    def test_new_high_resets_drawdown_to_zero(self):
        valuation = pd.DataFrame([
            {"portfolio_id": 1, "date": "2026-01-01", "portfolio_value": 1000.0},
            {"portfolio_id": 1, "date": "2026-01-02", "portfolio_value": 800.0},
            {"portfolio_id": 1, "date": "2026-01-03", "portfolio_value": 1500.0},  # new high
        ])
        result = calculate_daily_drawdown(valuation)
        new_high = result[result["date"] == "2026-01-03"].iloc[0]
        assert new_high["drawdown_pct"] == 0.0
        assert new_high["running_peak"] == pytest.approx(1500.0)

    def test_multiple_portfolios_computed_independently(self):
        valuation = pd.DataFrame([
            {"portfolio_id": 1, "date": "2026-01-01", "portfolio_value": 1000.0},
            {"portfolio_id": 1, "date": "2026-01-02", "portfolio_value": 500.0},
            {"portfolio_id": 2, "date": "2026-01-01", "portfolio_value": 200.0},
            {"portfolio_id": 2, "date": "2026-01-02", "portfolio_value": 300.0},
        ])
        result = calculate_daily_drawdown(valuation)
        p1_day2 = result[(result["portfolio_id"] == 1) & (result["date"] == "2026-01-02")].iloc[0]
        p2_day2 = result[(result["portfolio_id"] == 2) & (result["date"] == "2026-01-02")].iloc[0]
        assert p1_day2["drawdown_pct"] == pytest.approx(-0.5)
        assert p2_day2["drawdown_pct"] == 0.0  # p2 rose, so still at its peak

    def test_zero_running_peak_gives_nan_not_error(self):
        valuation = pd.DataFrame([
            {"portfolio_id": 1, "date": "2026-01-01", "portfolio_value": 0.0},
        ])
        result = calculate_daily_drawdown(valuation)
        assert pd.isna(result.iloc[0]["drawdown_pct"])

    def test_empty_input_returns_empty_with_expected_columns(self):
        valuation = pd.DataFrame(columns=["portfolio_id", "date", "portfolio_value"])
        result = calculate_daily_drawdown(valuation)
        assert len(result) == 0
        for col in ("portfolio_id", "date", "portfolio_value", "running_peak", "drawdown_pct"):
            assert col in result.columns
