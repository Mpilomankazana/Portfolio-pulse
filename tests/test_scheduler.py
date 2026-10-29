"""Unit tests for src/orchestration/scheduler.py. No database or real clock needed."""
from datetime import datetime
from unittest.mock import MagicMock

import pytest
from apscheduler.events import EVENT_JOB_ERROR
from zoneinfo import ZoneInfo

from src.orchestration import scheduler as sched_mod
from src.orchestration.run_pipeline import NoDataError


def test_build_trigger_rejects_malformed_cron():
    with pytest.raises(ValueError):
        sched_mod.build_trigger("not a cron", "Africa/Johannesburg")


def test_default_schedule_fires_weekdays_at_1800_sast():
    trigger = sched_mod.build_trigger("0 18 * * 1-5", "Africa/Johannesburg")
    tz = ZoneInfo("Africa/Johannesburg")

    # Friday 2026-10-23 19:00 -> next fire is Monday 2026-10-26 18:00 (skips the weekend).
    after_friday = datetime(2026, 10, 23, 19, 0, tzinfo=tz)
    nxt = trigger.get_next_fire_time(None, after_friday)
    assert (nxt.year, nxt.month, nxt.day, nxt.hour, nxt.minute) == (2026, 10, 26, 18, 0)

    # Saturday 2026-10-24 12:00 -> still Monday.
    saturday = datetime(2026, 10, 24, 12, 0, tzinfo=tz)
    nxt = trigger.get_next_fire_time(None, saturday)
    assert nxt.day == 26 and nxt.hour == 18


def test_build_scheduler_registers_single_safe_job():
    scheduler = sched_mod.build_scheduler("0 18 * * 1-5", "Africa/Johannesburg")
    jobs = scheduler.get_jobs()

    assert len(jobs) == 1
    job = jobs[0]
    assert job.id == sched_mod.JOB_ID
    assert job.func is sched_mod.run_scheduled
    assert job.max_instances == 1
    assert job.coalesce is True
    assert job.misfire_grace_time == sched_mod.MISFIRE_GRACE_SECONDS


def test_main_returns_2_on_invalid_schedule(monkeypatch):
    monkeypatch.setattr(sched_mod.config, "PIPELINE_SCHEDULE", "garbage")
    assert sched_mod.main([]) == 2


def test_main_run_now_survives_failed_run_and_still_starts_scheduler(monkeypatch):
    fake_scheduler = MagicMock()
    monkeypatch.setattr(sched_mod, "build_scheduler", lambda: fake_scheduler)
    boom = MagicMock(side_effect=RuntimeError("db down"))
    monkeypatch.setattr(sched_mod, "run_pipeline", boom)

    assert sched_mod.main(["--run-now"]) == 0

    boom.assert_called_once()
    fake_scheduler.start.assert_called_once()


def test_main_without_run_now_does_not_run_immediately(monkeypatch):
    fake_scheduler = MagicMock()
    monkeypatch.setattr(sched_mod, "build_scheduler", lambda: fake_scheduler)
    runner = MagicMock()
    monkeypatch.setattr(sched_mod, "run_pipeline", runner)

    assert sched_mod.main([]) == 0

    runner.assert_not_called()
    fake_scheduler.start.assert_called_once()


def test_main_exits_cleanly_on_keyboard_interrupt(monkeypatch):
    fake_scheduler = MagicMock()
    fake_scheduler.start.side_effect = KeyboardInterrupt
    monkeypatch.setattr(sched_mod, "build_scheduler", lambda: fake_scheduler)

    assert sched_mod.main([]) == 0


def test_error_listener_logs_failure(caplog):
    event = MagicMock(code=EVENT_JOB_ERROR, exception=RuntimeError("boom"))
    with caplog.at_level("ERROR"):
        sched_mod._on_job_event(event)
    assert "FAILED" in caplog.text


@pytest.mark.parametrize(
    "dow, expected",
    [("1-5", "mon-fri"), ("0", "sun"), ("7", "sun"), ("1,3,5", "mon,wed,fri"), ("*", "*"), ("*/2", "*/2"), ("mon-fri", "mon-fri")],
)
def test_translate_day_of_week(dow, expected):
    assert sched_mod._translate_day_of_week(dow) == expected


def test_translate_day_of_week_rejects_out_of_range():
    with pytest.raises(ValueError):
        sched_mod._translate_day_of_week("8")

class TestRunScheduled:
    """A run that loads nothing must not be reported as a success."""

    def _summary(self, status, **extra):
        return {"run_id": "r1", "source": "api", "status": status,
                "source_failures": extra.pop("source_failures", []), "lake_errors": [], **extra}

    def test_success_passes_the_summary_through(self, monkeypatch):
        monkeypatch.setattr(sched_mod, "run_pipeline", lambda: self._summary("success"))
        assert sched_mod.run_scheduled()["status"] == "success"

    def test_no_data_raises_so_the_listener_logs_failed(self, monkeypatch):
        monkeypatch.setattr(sched_mod, "run_pipeline", lambda: self._summary(
            "no_data", source_failures=["AAPL: API returned no rows"]))
        with pytest.raises(NoDataError, match="AAPL"):
            sched_mod.run_scheduled()

    def test_partial_warns_but_does_not_raise(self, monkeypatch, caplog):
        monkeypatch.setattr(sched_mod, "run_pipeline", lambda: self._summary(
            "partial", source_failures=["MSFT: boom"]))
        with caplog.at_level("WARNING"):
            assert sched_mod.run_scheduled()["status"] == "partial"
        assert "PARTIAL" in caplog.text and "MSFT" in caplog.text

    def test_lake_errors_warn(self, monkeypatch, caplog):
        monkeypatch.setattr(sched_mod, "run_pipeline", lambda: self._summary("success", lake_errors=["land_raw: disk full"]))
        with caplog.at_level("WARNING"):
            sched_mod.run_scheduled()
        assert "disk full" in caplog.text

    def test_listener_reports_a_no_data_run_as_failed(self, caplog):
        event = MagicMock(code=EVENT_JOB_ERROR, exception=RuntimeError("loaded no data"))
        with caplog.at_level("ERROR"):
            sched_mod._on_job_event(event)
        assert "FAILED" in caplog.text and "loaded no data" in caplog.text
