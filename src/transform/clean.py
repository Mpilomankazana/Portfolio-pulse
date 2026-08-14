"""Cleaning and transformation logic for raw market price data.

Phase 2 target: handle missing prices, null stock splits, timezone
conversion to SAST/UTC, and derived portfolio metrics (daily returns,
weighted return, allocation drift). Write pytest cases for each
function before implementing (TDD requirement).
"""
import pandas as pd


def clean_market_prices(df: pd.DataFrame) -> pd.DataFrame:
    """Drop/impute missing rows and enforce dtypes. Stub for Phase 2."""
    raise NotImplementedError("Phase 2: implement cleaning logic")


def calculate_daily_returns(df: pd.DataFrame) -> pd.DataFrame:
    """Compute daily return per asset from close prices. Stub for Phase 2."""
    raise NotImplementedError("Phase 2: implement return calculation")
