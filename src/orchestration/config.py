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

# --- Logging ----------------------------------------------------------
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()

# --- Scheduling ---------------------------------------------------------
# Cron string for APScheduler. Default: 18:00 SAST on weekdays — after the
# JSE close (17:00 SAST) and most US-listed feeds' end-of-day settlement,
# so a same-day run has final prices to ingest. Override via env if your
# managers' sources publish on a different schedule.
PIPELINE_SCHEDULE = os.getenv("PIPELINE_SCHEDULE", "0 18 * * 1-5")


def _validate() -> None:
    """Fail fast and loud at import time rather than deep inside a DB call."""
    if not DATABASE_URL:
        raise RuntimeError(
            "DATABASE_URL is not set and has no default. "
            "Set it in your .env file or environment before running the pipeline."
        )


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
