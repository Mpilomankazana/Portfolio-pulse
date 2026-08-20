"""Environment configuration and logging setup for the pipeline.

# TODO: implement, covering:
#   1. Load environment variables via python-dotenv's load_dotenv() (already
#      a dependency — see requirements.txt), so a local .env file works the
#      same way it does for src/db.py.
#   2. Centralize config here rather than scattering os.getenv() calls:
#      - DATABASE_URL (already read in src/db.py — consider importing from
#        there instead of duplicating, to keep one source of truth)
#      - MARKET_API_KEY (for extract_from_api once implemented)
#      - LOG_LEVEL (default "INFO")
#      - PIPELINE_SCHEDULE (e.g. a cron string for APScheduler, default
#        daily at a specific time — check what time the source market
#        closes/data is available before picking a default)
#   3. Fail fast and loud: if a required variable (e.g. DATABASE_URL) is
#      missing and there's no sane default, raise a clear error at import
#      time rather than letting the pipeline fail deep inside a DB call.
#   4. Set up logging (Python's logging module): a basicConfig call with
#      LOG_LEVEL and a format that includes timestamp + module name, so
#      run_pipeline.py and the extract/transform/load modules can just
#      `import logging; logger = logging.getLogger(__name__)` and get
#      consistent output.
#   5. Write a small test (tests/test_config.py) confirming a missing
#      DATABASE_URL raises, and that LOG_LEVEL defaults sensibly when unset.
"""
raise NotImplementedError("TODO: implement config/logging setup")
