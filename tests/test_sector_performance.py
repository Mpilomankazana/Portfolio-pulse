"""Unit tests for src/analytics/sector_performance.py."""
import numpy as np
import pandas as pd
import pytest

from src.analytics.sector_performance import (
    calculate_sector_dividends_vs_gains,
    calculate_sector_exposure,
)


class TestCalculateSectorDividendsVsGains:
    def test_sector_with_dividends_and_gains(self):
        dividends = pd.DataFrame([
            {"asset_id": 1, "sector": "Technology", "dividend_amount": 500.0,
             "payment_date": "2026-06-01"},
        ])
        holdings = pd.DataFrame([
            {"asset_id": 1, "sector": "Technology", "unrealized_gain_loss": 2500.0},
        ])
        result = calculate_sector_dividends_vs_gains(
            dividends, holdings, as_of="2026-08-01"
        )
        row = result[result["sector"] == "Technology"].iloc[0]
        assert row["annual_dividends"] == 500.0
        assert row["total_unrealized_gain_loss"] == 2500.0
        assert row["dividend_to_gain_ratio"] == pytest.approx(500.0 / 2500.0)

    def test_sector_with_dividends_but_a_loss(self):
        # Negative denominator: dividend income sitting on an unrealized loss.
        dividends = pd.DataFrame([
            {"asset_id": 2, "sector": "Energy", "dividend_amount": 300.0,
             "payment_date": "2026-05-01"},
        ])
        holdings = pd.DataFrame([
            {"asset_id": 2, "sector": "Energy", "unrealized_gain_loss": -1500.0},
        ])
        result = calculate_sector_dividends_vs_gains(
            dividends, holdings, as_of="2026-08-01"
        )
        row = result[result["sector"] == "Energy"].iloc[0]
        assert row["dividend_to_gain_ratio"] == pytest.approx(300.0 / -1500.0)
        assert row["dividend_to_gain_ratio"] < 0

    def test_sector_present_only_in_dividends(self):
        dividends = pd.DataFrame([
            {"asset_id": 3, "sector": "Healthcare", "dividend_amount": 100.0,
             "payment_date": "2026-07-01"},
        ])
        holdings = pd.DataFrame(columns=["asset_id", "sector", "unrealized_gain_loss"])
        result = calculate_sector_dividends_vs_gains(
            dividends, holdings, as_of="2026-08-01"
        )
        row = result[result["sector"] == "Healthcare"].iloc[0]
        assert row["annual_dividends"] == 100.0
        assert row["total_unrealized_gain_loss"] == 0.0
        assert pd.isna(row["dividend_to_gain_ratio"])

    def test_sector_present_only_in_holdings(self):
        dividends = pd.DataFrame(columns=["asset_id", "sector", "dividend_amount", "payment_date"])
        holdings = pd.DataFrame([
            {"asset_id": 4, "sector": "Financials", "unrealized_gain_loss": 800.0},
        ])
        result = calculate_sector_dividends_vs_gains(
            dividends, holdings, as_of="2026-08-01"
        )
        row = result[result["sector"] == "Financials"].iloc[0]
        assert row["annual_dividends"] == 0.0
        assert row["total_unrealized_gain_loss"] == 800.0

    def test_missing_dividend_payouts_defaults_to_zero(self):
        # Empty dividends_df entirely — e.g. no dividend data ingested yet.
        dividends = pd.DataFrame(columns=["asset_id", "sector", "dividend_amount", "payment_date"])
        holdings = pd.DataFrame([
            {"asset_id": 5, "sector": "Entertainment", "unrealized_gain_loss": 400.0},
        ])
        result = calculate_sector_dividends_vs_gains(dividends, holdings)
        row = result[result["sector"] == "Entertainment"].iloc[0]
        assert row["annual_dividends"] == 0.0
        assert row["dividend_to_gain_ratio"] == pytest.approx(0.0)

    def test_dividend_outside_trailing_12_months_excluded(self):
        dividends = pd.DataFrame([
            {"asset_id": 6, "sector": "Consumer Electronics", "dividend_amount": 200.0,
             "payment_date": "2024-01-01"},  # more than a year before as_of
        ])
        holdings = pd.DataFrame([
            {"asset_id": 6, "sector": "Consumer Electronics", "unrealized_gain_loss": 1000.0},
        ])
        result = calculate_sector_dividends_vs_gains(
            dividends, holdings, as_of="2026-08-01"
        )
        row = result[result["sector"] == "Consumer Electronics"].iloc[0]
        assert row["annual_dividends"] == 0.0

    def test_both_inputs_empty_returns_empty_result(self):
        dividends = pd.DataFrame(columns=["asset_id", "sector", "dividend_amount", "payment_date"])
        holdings = pd.DataFrame(columns=["asset_id", "sector", "unrealized_gain_loss"])
        result = calculate_sector_dividends_vs_gains(dividends, holdings)
        assert len(result) == 0
        assert list(result.columns) == [
            "sector", "annual_dividends", "total_unrealized_gain_loss", "dividend_to_gain_ratio"
        ]


class TestCalculateSectorExposure:
    def test_sector_percentages_sum_to_100_per_portfolio(self):
        holdings = pd.DataFrame([
            {"portfolio_id": 1, "sector": "Technology", "market_value": 6000.0},
            {"portfolio_id": 1, "sector": "Healthcare", "market_value": 4000.0},
        ])
        result = calculate_sector_exposure(holdings)
        total_pct = result[result["portfolio_id"] == 1]["sector_pct"].sum()
        assert total_pct == pytest.approx(100.0)

        tech_pct = result[
            (result["portfolio_id"] == 1) & (result["sector"] == "Technology")
        ].iloc[0]["sector_pct"]
        assert tech_pct == pytest.approx(60.0)

    def test_zero_holdings_returns_empty_dataframe(self):
        holdings = pd.DataFrame(columns=["portfolio_id", "sector", "market_value"])
        result = calculate_sector_exposure(holdings)
        assert len(result) == 0
        assert list(result.columns) == ["portfolio_id", "sector", "sector_pct"]

    def test_null_sector_maps_to_unclassified(self):
        holdings = pd.DataFrame([
            {"portfolio_id": 2, "sector": None, "market_value": 500.0},
            {"portfolio_id": 2, "sector": "Financials", "market_value": 500.0},
        ])
        result = calculate_sector_exposure(holdings)
        sectors = set(result[result["portfolio_id"] == 2]["sector"])
        assert "Unclassified" in sectors
        unclassified_pct = result[
            (result["portfolio_id"] == 2) & (result["sector"] == "Unclassified")
        ].iloc[0]["sector_pct"]
        assert unclassified_pct == pytest.approx(50.0)

    def test_multiple_portfolios_are_independent(self):
        holdings = pd.DataFrame([
            {"portfolio_id": 1, "sector": "Technology", "market_value": 1000.0},
            {"portfolio_id": 2, "sector": "Technology", "market_value": 300.0},
            {"portfolio_id": 2, "sector": "Energy", "market_value": 700.0},
        ])
        result = calculate_sector_exposure(holdings)
        p1_tech = result[
            (result["portfolio_id"] == 1) & (result["sector"] == "Technology")
        ].iloc[0]["sector_pct"]
        p2_tech = result[
            (result["portfolio_id"] == 2) & (result["sector"] == "Technology")
        ].iloc[0]["sector_pct"]
        assert p1_tech == pytest.approx(100.0)
        assert p2_tech == pytest.approx(30.0)
