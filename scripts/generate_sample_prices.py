"""Generate data/sample_prices.csv: deterministic synthetic daily OHLCV.

Synthetic on purpose: the file exists so the pipeline can run end to end
(and be demoed) without an API key. The random seed is fixed, so rerunning
this script reproduces the same file byte for byte.

Usage:
    python scripts/generate_sample_prices.py
"""
from pathlib import Path

import numpy as np
import pandas as pd

OUTPUT = Path(__file__).resolve().parents[1] / "data" / "sample_prices.csv"

# ticker -> (starting close, daily volatility, typical daily volume)
TICKERS = {
    "AAPL": (225.0, 0.014, 55_000_000),
    "MSFT": (430.0, 0.012, 22_000_000),
    "XOM": (115.0, 0.011, 15_000_000),
    "DIS": (98.0, 0.015, 9_000_000),
    "JPM": (210.0, 0.010, 10_000_000),
    "JNJ": (160.0, 0.008, 7_000_000),
    "AGG": (98.0, 0.002, 6_000_000),
    "BIL": (91.5, 0.0002, 4_000_000),
}

START, END = "2026-08-03", "2026-10-23"  # weekdays only (business days)
SEED = 27


def generate() -> pd.DataFrame:
    rng = np.random.default_rng(SEED)
    dates = pd.bdate_range(START, END)
    rows = []

    for ticker, (start_close, vol, base_volume) in TICKERS.items():
        returns = rng.normal(loc=0.0003, scale=vol, size=len(dates))
        closes = start_close * np.cumprod(1 + returns)
        prev_close = start_close

        for date, close in zip(dates, closes):
            open_ = prev_close * (1 + rng.normal(0, vol / 3))
            # high/low always bracket open and close, so validate_ohlcv passes.
            high = max(open_, close) * (1 + abs(rng.normal(0, vol / 2)))
            low = min(open_, close) * (1 - abs(rng.normal(0, vol / 2)))
            volume = int(base_volume * rng.uniform(0.7, 1.3))
            rows.append(
                {
                    "ticker": ticker,
                    "date": date.strftime("%Y-%m-%d"),
                    "open": round(open_, 4),
                    "high": round(high, 4),
                    "low": round(low, 4),
                    "close": round(close, 4),
                    "volume": volume,
                }
            )
            prev_close = close

    return pd.DataFrame(rows, columns=["ticker", "date", "open", "high", "low", "close", "volume"])


def main() -> None:
    df = generate()
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(OUTPUT, index=False)
    print(f"Wrote {len(df)} rows ({df['ticker'].nunique()} tickers) to {OUTPUT}")


if __name__ == "__main__":
    main()