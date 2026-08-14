"""Extractors for asset price data (CSV batch files or market APIs).

Phase 2 target: modular extractors, one function per source, each
returning a raw pandas DataFrame with no cleaning applied yet.
"""
import pandas as pd


def extract_from_csv(path: str) -> pd.DataFrame:
    """Load a raw market price CSV. Expected columns:
    ticker, date, open, high, low, close, volume
    """
    return pd.read_csv(path)


def extract_from_api(ticker: str, start: str, end: str) -> pd.DataFrame:
    """Placeholder for a market API pull (e.g. Alpha Vantage).

    To be implemented in Phase 2 with request handling, rate limiting,
    and response normalization to the same schema as extract_from_csv.
    """
    raise NotImplementedError("Phase 2: implement API extraction")
