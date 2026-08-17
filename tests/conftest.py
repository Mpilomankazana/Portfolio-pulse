"""Shared fixtures for the PortfolioPulse test suite."""
import pandas as pd
import pytest


@pytest.fixture
def raw_csv_path(tmp_path):
    """A small, valid raw market-price CSV matching extract_from_csv's expected schema."""
    csv_text = (
        "ticker,date,open,high,low,close,volume\n"
        "AAPL,2026-01-02,180.0,182.5,179.0,181.2,1000000\n"
        "AAPL,2026-01-03,181.2,183.0,180.5,182.9,1100000\n"
        "MSFT,2026-01-02,370.0,372.0,368.5,371.0,800000\n"
        "MSFT,2026-01-03,371.0,375.0,370.0,374.2,850000\n"
    )
    path = tmp_path / "prices.csv"
    path.write_text(csv_text)
    return str(path)


@pytest.fixture
def raw_prices_df():
    """A raw (uncleaned) DataFrame containing the kinds of messiness clean_market_prices
    is expected to handle: a missing close, a missing volume, and an unsorted/mixed-case
    ticker column.
    """
    return pd.DataFrame(
        [
            {"ticker": "aapl", "date": "2026-01-03", "open": 181.2, "high": 183.0,
             "low": 180.5, "close": 182.9, "volume": 1100000},
            {"ticker": " AAPL ", "date": "2026-01-02", "open": 180.0, "high": 182.5,
             "low": 179.0, "close": 181.2, "volume": None},
            {"ticker": "MSFT", "date": "2026-01-02", "open": 370.0, "high": 372.0,
             "low": 368.5, "close": None, "volume": 800000},
            {"ticker": "MSFT", "date": "2026-01-03", "open": 371.0, "high": 375.0,
             "low": 370.0, "close": 374.2, "volume": 850000},
        ]
    )


@pytest.fixture
def clean_prices_df():
    """A DataFrame already in the shape clean_market_prices should produce, used as
    input to calculate_daily_returns so that test isn't coupled to clean's behaviour.
    """
    return pd.DataFrame(
        [
            {"ticker": "AAPL", "date": pd.Timestamp("2026-01-02"), "close": 180.0},
            {"ticker": "AAPL", "date": pd.Timestamp("2026-01-03"), "close": 189.0},
            {"ticker": "AAPL", "date": pd.Timestamp("2026-01-04"), "close": 180.0},
            {"ticker": "MSFT", "date": pd.Timestamp("2026-01-02"), "close": 100.0},
            {"ticker": "MSFT", "date": pd.Timestamp("2026-01-03"), "close": 105.0},
        ]
    )
