"""Scheduler entrypoint: runs the pipeline on the PIPELINE_SCHEDULE cron.

Usage:
    python -m src.orchestration.scheduler             # block and run on schedule
    python -m src.orchestration.scheduler --run-now   # one immediate run, then schedule

Design notes:
  * BlockingScheduler: this process exists only to run the scheduler, so
    there is no need for a background thread.
  * max_instances=1 + coalesce=True: if a run overruns into the next slot,
    or the process was asleep through several slots, we run once, not N times.
  * A failed run is logged and the scheduler keeps going. run_pipeline.run()
    already logs the traceback and re-raises; APScheduler catches it, and the
    listener below adds a one-line summary so failures are easy to grep.
  * The cron is interpreted in SCHEDULER_TIMEZONE (default Africa/Johannesburg),
    matching the "18:00 SAST" default documented in config.py.
"""
import argparse
import logging
import sys

from apscheduler.events import EVENT_JOB_ERROR, EVENT_JOB_EXECUTED, EVENT_JOB_MISSED
from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger

# Importing config first: loads .env, validates DATABASE_URL, configures logging.
from src.orchestration import config
from src.orchestration.run_pipeline import run as run_pipeline

logger = logging.getLogger(__name__)

JOB_ID = "portfolio_pulse_daily_run"

# Tolerate up to 1 hour of lateness (host asleep, container restarting)
# before a slot is treated as missed.
MISFIRE_GRACE_SECONDS = 3600


_CRON_DOW = {"0": "sun", "1": "mon", "2": "tue", "3": "wed", "4": "thu", "5": "fri", "6": "sat", "7": "sun"}


def _translate_day_of_week(field: str) -> str:
    """Convert standard-cron weekday numbers (0/7=Sun, 1=Mon) to APScheduler names.

    APScheduler's from_crontab passes numeric weekdays through unchanged, but
    APScheduler counts 0 as Monday, so a standard "1-5" would silently mean
    Tue-Sat. Named days are unambiguous in both systems.
    """
    out, token, after_step = [], "", False
    for ch in field + "\0":
        if ch.isdigit():
            token += ch
            continue
        if token:
            if after_step:  # a "/N" step size is a count, not a weekday
                out.append(token)
            elif token in _CRON_DOW:
                out.append(_CRON_DOW[token])
            else:
                raise ValueError(f"day_of_week value out of range: {token}")
            token = ""
        after_step = ch == "/"
        if ch != "\0":
            out.append(ch)
    return "".join(out)


def build_trigger(cron_expr: str, timezone: str) -> CronTrigger:
    """Parse a standard 5-field crontab string. Raises ValueError if malformed."""
    fields = cron_expr.split()
    if len(fields) != 5:
        raise ValueError(f"Wrong number of fields; got {len(fields)}, expected 5")
    minute, hour, day, month, dow = fields
    return CronTrigger(
        minute=minute,
        hour=hour,
        day=day,
        month=month,
        day_of_week=_translate_day_of_week(dow),
        timezone=timezone,
    )


def _on_job_event(event) -> None:
    if event.code == EVENT_JOB_ERROR:
        logger.error("Scheduled run FAILED: %s", event.exception)
    elif event.code == EVENT_JOB_MISSED:
        logger.warning("Scheduled run MISSED (scheduler was down or busy): %s", event.scheduled_run_time)
    elif event.code == EVENT_JOB_EXECUTED:
        logger.info("Scheduled run completed successfully")


def build_scheduler(cron_expr: str | None = None, timezone: str | None = None) -> BlockingScheduler:
    """Create (but do not start) a scheduler with the pipeline job registered."""
    cron_expr = cron_expr or config.PIPELINE_SCHEDULE
    timezone = timezone or config.SCHEDULER_TIMEZONE

    scheduler = BlockingScheduler(timezone=timezone)
    scheduler.add_job(
        run_pipeline,
        trigger=build_trigger(cron_expr, timezone),
        id=JOB_ID,
        name="PortfolioPulse daily ETL run",
        max_instances=1,
        coalesce=True,
        misfire_grace_time=MISFIRE_GRACE_SECONDS,
        replace_existing=True,
    )
    scheduler.add_listener(_on_job_event, EVENT_JOB_EXECUTED | EVENT_JOB_ERROR | EVENT_JOB_MISSED)
    return scheduler


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the PortfolioPulse pipeline on a schedule.")
    parser.add_argument(
        "--run-now",
        action="store_true",
        help="Run the pipeline once immediately before waiting for the first scheduled slot.",
    )
    args = parser.parse_args(argv)

    try:
        scheduler = build_scheduler()
    except ValueError as exc:
        logger.error("Invalid PIPELINE_SCHEDULE %r: %s", config.PIPELINE_SCHEDULE, exc)
        return 2

    logger.info(
        "Scheduler starting: cron=%r timezone=%s", config.PIPELINE_SCHEDULE, config.SCHEDULER_TIMEZONE
    )

    if args.run_now:
        logger.info("--run-now given: running pipeline once before scheduling")
        try:
            run_pipeline()
        except Exception:  # noqa: BLE001 — already logged by run(); don't block the schedule
            logger.error("Immediate run failed; continuing to scheduled runs")

    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        logger.info("Scheduler stopped")
    return 0


if __name__ == "__main__":
    sys.exit(main())