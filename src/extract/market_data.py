"""Extractors for asset price data (CSV batch files or market APIs).

Phase 2 target: modular extractors, one function per source, each
returning a raw pandas DataFrame with no cleaning applied yet.
"""
import logging
import os
import time
from datetime import date

import pandas as pd
import requests

logger = logging.getLogger(__name__)

API_BASE_URL = "https://www.alphavantage.co/query"
REQUEST_TIMEOUT_SECONDS = 10
MAX_RETRIES = 3

# Alpha Vantage's "compact" output is the latest 100 trading days (about 140
# calendar days) and works on a free key; "full" is the whole history and may
# be restricted to premium keys. A start date this close to today fits compact.
# 120 calendar days leaves a margin for weekends and holidays.
COMPACT_MAX_CALENDAR_DAYS = 120

# Keys Alpha Vantage uses to say "no data, and here is why" while still
# answering HTTP 200 (rate limit, daily quota, premium-only parameter, bad symbol).
_PROVIDER_MESSAGE_KEYS = ("Error Message", "Information", "Note")

EXPECTED_COLUMNS = ["ticker", "date", "open", "high", "low", "close", "volume"]

# Alpha Vantage's daily OHLCV field names -> this project's schema.
_FIELD_MAP = {
    "1. open": "open",
    "2. high": "high",
    "3. low": "low",
    "4. close": "close",
    "5. volume": "volume",
}


def extract_from_csv(path: str) -> pd.DataFrame:
    """Load a raw market price CSV. Expected columns:
    ticker, date, open, high, low, close, volume
    """
    return pd.read_csv(path)


def _today() -> date:
    return date.today()


def choose_outputsize(start: str) -> str:
    """Pick compact if `start` is within the latest-100-days window, otherwise full."""
    age_days = (_today() - date.fromisoformat(start)).days
    return "compact" if age_days <= COMPACT_MAX_CALENDAR_DAYS else "full"


def extract_from_api(ticker: str, start: str, end: str, outputsize: str | None = None) -> pd.DataFrame:
    """Pull daily OHLCV data for one ticker from Alpha Vantage.

    Params:
        ticker: single ticker symbol, e.g. "AAPL".
        start, end: ISO date strings ("YYYY-MM-DD"), inclusive range.
        outputsize: "compact" or "full". Left as None, it is chosen from
            `start` (see choose_outputsize), so a short recent lookback
            uses "compact" and works on a free Alpha Vantage key.

    Returns: DataFrame with the same columns as extract_from_csv
    (ticker, date, open, high, low, close, volume) so callers can treat
    both extractors interchangeably before handing off to
    clean_market_prices. Values are returned exactly as the API sends
    them (strings) — no dtype coercion or cleaning happens here, same
    as extract_from_csv; that's clean_market_prices's job.

    Requires the MARKET_API_KEY environment variable (an Alpha Vantage
    API key). Raises RuntimeError immediately if it's unset, rather
    than letting a later request fail with an unauthenticated error
    that's harder to trace back to a missing env var.

    On a non-200 response (other than a retried 429), raises
    RuntimeError naming both the ticker and the HTTP status code, so a
    failure for one ticker in a larger pipeline run is traceable in
    logs. A 429 (rate limited) is retried up to MAX_RETRIES times,
    honoring the Retry-After header when the provider sends one and
    otherwise backing off exponentially (1s, 2s, 4s, ...); exceeding
    MAX_RETRIES on 429s raises the same RuntimeError as any other
    non-200 status.

    The endpoint takes no date range, so the response is filtered down to
    [start, end] client-side. "compact" covers only the latest 100 trading
    days, so a start date further back than that needs "full", which is
    chosen automatically (or pass outputsize explicitly).

    If the provider has no data in [start, end] for this ticker (e.g.
    a delisted ticker, or a range entirely inside a market holiday
    gap), returns an empty DataFrame with the expected columns rather
    than raising, so downstream code can treat "no data" the same way
    regardless of source. When the provider answers 200 with an explanation
    instead of prices (rate limit, daily quota, premium-only request), that
    message is logged as a warning so the cause is visible, and the result
    is still the empty frame.
    """
    api_key = os.getenv("MARKET_API_KEY")
    if not api_key:
        raise RuntimeError(
            "MARKET_API_KEY environment variable is not set. Set it to a "
            "valid Alpha Vantage API key before calling extract_from_api."
        )

    params = {
        "function": "TIME_SERIES_DAILY",
        "symbol": ticker,
        "outputsize": outputsize or choose_outputsize(start),
        "apikey": api_key,
    }

    response = _get_with_retries(ticker, params)
    payload = response.json()
    time_series = payload.get("Time Series (Daily)", {})

    if not time_series:
        for key in _PROVIDER_MESSAGE_KEYS:
            if payload.get(key):
                logger.warning("Alpha Vantage returned no prices for %s: %s: %s", ticker, key, str(payload[key])[:300])
                break
        return pd.DataFrame(columns=EXPECTED_COLUMNS)

    records = [
        {
            "ticker": ticker,
            "date": date_str,
            **{dest: values.get(src) for src, dest in _FIELD_MAP.items()},
        }
        for date_str, values in time_series.items()
        if start <= date_str <= end
    ]

    if not records:
        return pd.DataFrame(columns=EXPECTED_COLUMNS)

    return pd.DataFrame(records, columns=EXPECTED_COLUMNS)


def _get_with_retries(ticker: str, params: dict) -> requests.Response:
    """GET API_BASE_URL with params, retrying 429s up to MAX_RETRIES times.

    Any other non-200 status raises immediately (no retry). Exceeding
    MAX_RETRIES on repeated 429s falls through to the same error.
    """
    attempt = 0
    while True:
        response = requests.get(
            API_BASE_URL, params=params, timeout=REQUEST_TIMEOUT_SECONDS
        )

        if response.status_code == 200:
            return response

        if response.status_code == 429 and attempt < MAX_RETRIES:
            retry_after = response.headers.get("Retry-After")
            try:
                wait_seconds = float(retry_after) if retry_after is not None else None
            except ValueError:
                wait_seconds = None
            if wait_seconds is None:
                wait_seconds = 2 ** attempt  # exponential backoff: 1s, 2s, 4s, ...
            time.sleep(wait_seconds)
            attempt += 1
            continue

        raise RuntimeError(
            f"Market data API request for ticker {ticker!r} failed with "
            f"status {response.status_code}: {response.text[:500]}"
        )