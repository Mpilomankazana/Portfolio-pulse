"""File-based data lake: Parquet for data, JSON for run manifests.

Layout under the lake root:

    raw/market_prices/run_id=<UTC timestamp>/data.parquet
        Exactly what the extractor returned, every column as a string,
        one immutable folder per run. This is the EL half of ELT: land
        first, transform later, and you can always replay a run.

    curated/market_prices/ticker=<TICKER>/data.parquet
        Cleaned, validated rows with daily_return and is_outlier, one file
        per ticker, merged by date on every run (newest wins), so reruns
        are idempotent just like the database upsert.

    manifests/<run_id>.json
        Row counts, source, failures and the paths written for one run.

Pure file I/O: no database access and no config import, so it is easy to
test with a temp directory.
"""
import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

RAW_DATASET = "market_prices"


def new_run_id() -> str:
    """UTC timestamp, sortable and filesystem-safe: 20261026T180000Z."""
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def land_raw(df: pd.DataFrame, root: Path, run_id: str) -> Path:
    """Write the extractor output unchanged (as strings) to the raw zone."""
    path = Path(root) / "raw" / RAW_DATASET / f"run_id={run_id}" / "data.parquet"
    path.parent.mkdir(parents=True, exist_ok=True)
    df.astype("string").to_parquet(path, index=False)
    return path


def write_curated(df: pd.DataFrame, root: Path) -> list[Path]:
    """Upsert cleaned rows into one Parquet file per ticker, keyed on date.

    Existing rows for the same (ticker, date) are replaced by the new ones;
    other dates are kept, so the file accumulates history across runs.
    """
    written: list[Path] = []
    for ticker, part in df.groupby("ticker", sort=True):
        path = Path(root) / "curated" / RAW_DATASET / f"ticker={ticker}" / "data.parquet"
        path.parent.mkdir(parents=True, exist_ok=True)

        new = part.drop(columns=["ticker"]).copy()
        new["date"] = pd.to_datetime(new["date"])
        if path.exists():
            old = pd.read_parquet(path)
            new = pd.concat([old, new], ignore_index=True)
        merged = (
            new.drop_duplicates(subset="date", keep="last")
            .sort_values("date")
            .reset_index(drop=True)
        )
        merged.to_parquet(path, index=False)
        written.append(path)
    return written


def read_curated(root: Path, ticker: str | None = None) -> pd.DataFrame:
    """Read curated rows back (one ticker, or all) with a ticker column."""
    base = Path(root) / "curated" / RAW_DATASET
    frames = []
    for folder in sorted(base.glob("ticker=*")):
        t = folder.name.split("=", 1)[1]
        if ticker is not None and t != ticker:
            continue
        df = pd.read_parquet(folder / "data.parquet")
        df.insert(0, "ticker", t)
        frames.append(df)
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def write_manifest(manifest: dict, root: Path, run_id: str) -> Path:
    """Write the run summary as pretty JSON. Non-JSON types are stringified."""
    path = Path(root) / "manifests" / f"{run_id}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(manifest, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
    return path
