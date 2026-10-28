"""Environment configuration and logging setup for the pipeline.

Centralizes settings so run_pipeline.py and the extract/transform/load
modules import from one place instead of scattering os.getenv() calls.
Importing this module has two side effects, both intentional:
  1. It loads .env (via python-dotenv) if present.
  2. It calls logging.basicConfig(), so any module that does
     `import logging; logger = logging.getLogger(__name__)` after this
     module has been imported gets consistent formatting for free.
"""
import logging
import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

# --- Database -----------------------------------------------------------
# src/db.py already defines DATABASE_URL with the same local-dev default.
# Import from there instead of duplicating the fallback, so there's a
# single source of truth if the default ever changes.
from src.db import DATABASE_URL  # noqa: E402  (import after load_dotenv on purpose)

# --- Market data API ------------------------------------------------------
# No sane default for a secret — required only once extract_from_api is
# implemented (Phase 2). Left as None here rather than raised eagerly, so
# importing config.py doesn't crash CSV-only runs that never touch the API.
MARKET_API_KEY = os.getenv("MARKET_API_KEY")

# --- Data sources -------------------------------------------------------
# Repo root, so relative paths below resolve the same whether the pipeline
# is started from the repo root, from a scheduler, or inside the container.
PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _parse_csv_sources(raw: str | None) -> list[Path]:
    """Comma-separated paths -> list of Paths. Relative paths are taken
    relative to PROJECT_ROOT. Empty/unset falls back to the sample file."""
    entries = [e.strip() for e in (raw or "").split(",") if e.strip()]
    if not entries:
        entries = ["data/sample_prices.csv"]
    return [p if p.is_absolute() else PROJECT_ROOT / p for p in map(Path, entries)]


# Override with e.g. CSV_SOURCES=data/a.csv,data/b.csv
CSV_SOURCES = _parse_csv_sources(os.getenv("CSV_SOURCES"))

# Where prices come from: "csv" (CSV_SOURCES above) or "api" (Alpha Vantage,
# needs MARKET_API_KEY and API_TICKERS). Default stays csv so a fresh clone
# and the Docker demo work with no key.
DATA_SOURCE = os.getenv("DATA_SOURCE", "csv").strip().lower()


def _parse_tickers(raw: str | None) -> list[str]:
    """Comma-separated tickers -> upper-cased list, blanks dropped, order kept, dupes removed."""
    seen: list[str] = []
    for t in (raw or "").split(","):
        t = t.strip().upper()
        if t and t not in seen:
            seen.append(t)
    return seen


API_TICKERS = _parse_tickers(os.getenv("API_TICKERS"))
# Days of history requested per run, ending today (UTC).
API_LOOKBACK_DAYS = int(os.getenv("API_LOOKBACK_DAYS", "30"))
# Pause between per-ticker API calls. Alpha Vantage's free tier allows about
# 5 requests/minute, so 12s keeps a multi-ticker run under it.
API_PAUSE_SECONDS = float(os.getenv("API_PAUSE_SECONDS", "12"))

# --- Data lake ----------------------------------------------------------
# File-based landing zone next to the database: raw Parquet per run,
# curated Parquet per ticker, and a JSON manifest per run. Best-effort:
# a lake write failure is logged but never fails the database load.
LAKE_ENABLED = os.getenv("LAKE_ENABLED", "true").strip().lower() in ("1", "true", "yes")
LAKE_DIR = Path(os.getenv("LAKE_DIR") or PROJECT_ROOT / "lake")

# --- Logging ----------------------------------------------------------
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()

# --- Scheduling ---------------------------------------------------------
# Cron string for APScheduler. Default: 18:00 SAST on weekdays — after the
# JSE close (17:00 SAST) and most US-listed feeds' end-of-day settlement,
# so a same-day run has final prices to ingest. Override via env if your
# managers' sources publish on a different schedule.
PIPELINE_SCHEDULE = os.getenv("PIPELINE_SCHEDULE", "0 18 * * 1-5")

# Timezone the cron above is interpreted in (IANA name).
SCHEDULER_TIMEZONE = os.getenv("SCHEDULER_TIMEZONE", "Africa/Johannesburg")


def check_data_source(source: str, tickers: list[str], api_key: str | None) -> None:
    """Raise RuntimeError if the data-source settings can't work together."""
    if source not in ("csv", "api"):
        raise RuntimeError(f"DATA_SOURCE must be 'csv' or 'api', got {source!r}")
    if source == "api":
        if not tickers:
            raise RuntimeError("DATA_SOURCE=api needs API_TICKERS (comma-separated, e.g. AAPL,MSFT)")
        if not api_key:
            raise RuntimeError("DATA_SOURCE=api needs MARKET_API_KEY (an Alpha Vantage key)")


def _validate() -> None:
    """Fail fast and loud at import time rather than deep inside a DB call."""
    if not DATABASE_URL:
        raise RuntimeError(
            "DATABASE_URL is not set and has no default. "
            "Set it in your .env file or environment before running the pipeline."
        )
    check_data_source(DATA_SOURCE, API_TICKERS, MARKET_API_KEY)


_validate()

logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
)

logger = logging.getLogger(__name__)
logger.debug(
    "Config loaded: LOG_LEVEL=%s, PIPELINE_SCHEDULE=%s, MARKET_API_KEY=%s",
    LOG_LEVEL,
    PIPELINE_SCHEDULE,
    "set" if MARKET_API_KEY else "unset",
)
