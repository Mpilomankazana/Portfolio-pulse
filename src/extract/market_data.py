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
    """Placeholder for a market API pull (e.g. Alpha Vantage, Yahoo Finance).

    Params:
        ticker: single ticker symbol, e.g. "AAPL".
        start, end: ISO date strings ("YYYY-MM-DD"), inclusive range.

    Returns: DataFrame with the same columns as extract_from_csv
    (ticker, date, open, high, low, close, volume) so callers can treat
    both extractors interchangeably before handing off to clean_market_prices.

    # TODO: implement API extraction, in this order:
    #   1. Read the API key from an environment variable (e.g. MARKET_API_KEY)
    #      via os.getenv — never hardcode it. Raise a clear error if it's unset.
    #   2. Build the request URL/params for the chosen provider's daily OHLCV
    #      endpoint, passing ticker, start, end.
    #   3. Call requests.get() with a timeout (e.g. 10s). Handle:
    #      - non-200 responses -> raise a descriptive exception including the
    #        status code and ticker, so pipeline logs show which ticker failed.
    #      - rate-limit responses (commonly 429) -> respect Retry-After if
    #        present, otherwise back off (e.g. exponential) and retry a
    #        bounded number of times before giving up.
    #   4. Parse the JSON response into a DataFrame. Map the provider's field
    #      names to this project's schema: ticker, date, open, high, low,
    #      close, volume. Do NOT do cleaning/dtype coercion here — that's
    #      clean_market_prices's job; this function should return data as
    #      raw as extract_from_csv does.
    #   5. If the provider returns no data for the requested range (e.g.
    #      delisted ticker, market holiday range), return an empty DataFrame
    #      with the expected columns rather than raising, so downstream
    #      code can treat "no data" uniformly whether the source was CSV
    #      or API.
    #   6. Add a unit test in tests/test_extract.py that mocks requests.get
    #      (unittest.mock.patch, similar to how test_loader.py mocks the
    #      DB engine) so this test doesn't require a live network call or
    #      a real API key.
    """
    raise NotImplementedError("Phase 2: implement API extraction")
