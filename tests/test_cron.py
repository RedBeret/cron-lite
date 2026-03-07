"""Tests for cron-lite."""

import asyncio
from datetime import datetime

import pytest

from cron_lite import CronScheduler, parse_cron, cron_matches
from cron_lite.cron_lite import _parse_field


# ---------------------------------------------------------------------------
# parse_cron — expression parsing
# ---------------------------------------------------------------------------

class TestParseCron:
    def test_wildcard_every_field(self):
        expr = parse_cron("* * * * *")
        assert expr.minute == set(range(0, 60))
        assert expr.hour == set(range(0, 24))
        assert expr.dom == set(range(1, 32))
        assert expr.month == set(range(1, 13))
        assert expr.dow == set(range(0, 7))

    def test_specific_values(self):
        expr = parse_cron("0 8 * * *")
        assert 0 in expr.minute
        assert 8 in expr.hour
        assert 1 not in expr.minute
        assert 9 not in expr.hour

    def test_range(self):
        expr = parse_cron("30 7 * * 1-5")
        assert expr.minute == {30}
        assert expr.hour == {7}
        # 1-5 in cron = Mon-Fri (cron convention 0=Sun,1=Mon...6=Sat)
        assert expr.dow == {1, 2, 3, 4, 5}

    def test_step_every_15_minutes(self):
        expr = parse_cron("*/15 * * * *")
        assert expr.minute == {0, 15, 30, 45}

    def test_step_every_hour(self):
        expr = parse_cron("0 */6 * * *")
        assert expr.hour == {0, 6, 12, 18}

    def test_list_hours(self):
        expr = parse_cron("0 9,17 * * *")
        assert expr.minute == {0}
        assert expr.hour == {9, 17}

    def test_first_of_month(self):
        expr = parse_cron("0 0 1 * *")
        assert expr.dom == {1}
        assert expr.hour == {0}
        assert expr.minute == {0}

    def test_leap_day(self):
        expr = parse_cron("0 0 29 2 *")
        assert 29 in expr.dom
        assert expr.month == {2}

    def test_step_range(self):
        # "1-10/2" should produce {1,3,5,7,9}
        result = _parse_field("1-10/2", "minute")
        assert result == {1, 3, 5, 7, 9}

    def test_dow_sunday_as_7_normalised_to_0(self):
        # dow=7 should be treated same as dow=0 (both are Sunday)
        expr = parse_cron("0 0 * * 7")
        assert 0 in expr.dow  # normalised to 0
        assert 7 not in expr.dow

    def test_dow_0_and_7_both_sunday(self):
        expr0 = parse_cron("0 0 * * 0")
        expr7 = parse_cron("0 0 * * 7")
        assert expr0.dow == expr7.dow

    def test_invalid_too_few_fields(self):
        with pytest.raises(ValueError, match="5 fields"):
            parse_cron("* * * *")

    def test_invalid_too_many_fields(self):
        with pytest.raises(ValueError, match="5 fields"):
            parse_cron("* * * * * *")

    def test_invalid_out_of_range_minute(self):
        with pytest.raises(ValueError):
            parse_cron("60 * * * *")

    def test_invalid_out_of_range_hour(self):
        with pytest.raises(ValueError):
            parse_cron("* 24 * * *")

    def test_invalid_step_zero(self):
        with pytest.raises(ValueError):
            parse_cron("*/0 * * * *")

    def test_month_name_aliases(self):
        expr = parse_cron("0 0 1 jan *")
        assert expr.month == {1}

    def test_dow_name_aliases(self):
        expr = parse_cron("0 8 * * mon-fri")
        assert expr.dow == {1, 2, 3, 4, 5}

    def test_raw_expression_preserved(self):
        raw = "30 7 * * 1-5"
        expr = parse_cron(raw)
        assert expr.raw == raw


# ---------------------------------------------------------------------------
# cron_matches — datetime matching
# ---------------------------------------------------------------------------

class TestCronMatches:
    def test_matches_every_minute(self):
        expr = parse_cron("* * * * *")
        assert cron_matches(expr, datetime(2026, 3, 7, 15, 30))  # Saturday
        assert cron_matches(expr, datetime(2026, 1, 1, 0, 0))

    def test_matches_specific_hour_minute(self):
        expr = parse_cron("0 8 * * *")
        assert cron_matches(expr, datetime(2026, 3, 9, 8, 0))
        assert not cron_matches(expr, datetime(2026, 3, 9, 8, 1))
        assert not cron_matches(expr, datetime(2026, 3, 9, 9, 0))

    def test_matches_weekdays_only(self):
        # 7:30 Mon-Fri in cron (dow 1-5)
        expr = parse_cron("30 7 * * 1-5")
        monday = datetime(2026, 3, 9, 7, 30)    # Monday
        saturday = datetime(2026, 3, 7, 7, 30)  # Saturday
        sunday = datetime(2026, 3, 8, 7, 30)    # Sunday
        assert cron_matches(expr, monday)
        assert not cron_matches(expr, saturday)
        assert not cron_matches(expr, sunday)

    def test_matches_every_15_minutes(self):
        expr = parse_cron("*/15 * * * *")
        assert cron_matches(expr, datetime(2026, 3, 7, 10, 0))
        assert cron_matches(expr, datetime(2026, 3, 7, 10, 15))
        assert cron_matches(expr, datetime(2026, 3, 7, 10, 30))
        assert cron_matches(expr, datetime(2026, 3, 7, 10, 45))
        assert not cron_matches(expr, datetime(2026, 3, 7, 10, 1))
        assert not cron_matches(expr, datetime(2026, 3, 7, 10, 14))

    def test_matches_multiple_hours(self):
        expr = parse_cron("0 9,17 * * *")
        assert cron_matches(expr, datetime(2026, 3, 9, 9, 0))
        assert cron_matches(expr, datetime(2026, 3, 9, 17, 0))
        assert not cron_matches(expr, datetime(2026, 3, 9, 10, 0))

    def test_matches_first_of_month(self):
        expr = parse_cron("0 0 1 * *")
        assert cron_matches(expr, datetime(2026, 3, 1, 0, 0))
        assert not cron_matches(expr, datetime(2026, 3, 2, 0, 0))
        assert not cron_matches(expr, datetime(2026, 3, 1, 0, 1))

    def test_matches_leap_day(self):
        expr = parse_cron("0 0 29 2 *")
        assert cron_matches(expr, datetime(2028, 2, 29, 0, 0))  # 2028 is leap year
        assert not cron_matches(expr, datetime(2026, 2, 28, 0, 0))

    def test_sunday_matches_both_0_and_7_expressions(self):
        expr0 = parse_cron("0 0 * * 0")
        expr7 = parse_cron("0 0 * * 7")
        sunday = datetime(2026, 3, 8, 0, 0)   # March 8, 2026 is a Sunday
        assert cron_matches(expr0, sunday)
        assert cron_matches(expr7, sunday)

    def test_wrong_month_no_match(self):
        expr = parse_cron("0 0 1 6 *")  # June 1st only
        assert not cron_matches(expr, datetime(2026, 3, 1, 0, 0))
        assert cron_matches(expr, datetime(2026, 6, 1, 0, 0))


# ---------------------------------------------------------------------------
# CronScheduler — registration and execution
# ---------------------------------------------------------------------------

class TestCronScheduler:
    def test_decorator_registers_task(self):
        scheduler = CronScheduler()

        @scheduler.cron("* * * * *")
        def my_task():
            pass

        assert len(scheduler.tasks) == 1
        assert scheduler.tasks[0].name == "my_task"

    def test_add_task_imperative(self):
        scheduler = CronScheduler()

        def job():
            pass

        task = scheduler.add_task("0 8 * * *", job, name="morning_job")
        assert task.name == "morning_job"
        assert len(scheduler.tasks) == 1

    def test_multiple_tasks_registered(self):
        scheduler = CronScheduler()

        @scheduler.cron("* * * * *")
        async def task_a():
            pass

        @scheduler.cron("0 8 * * *")
        async def task_b():
            pass

        assert len(scheduler.tasks) == 2

    def test_async_task_detected(self):
        scheduler = CronScheduler()

        @scheduler.cron("* * * * *")
        async def async_task():
            pass

        assert scheduler.tasks[0].is_async is True

    def test_sync_task_detected(self):
        scheduler = CronScheduler()

        @scheduler.cron("* * * * *")
        def sync_task():
            pass

        assert scheduler.tasks[0].is_async is False

    def test_status_output(self):
        scheduler = CronScheduler()

        @scheduler.cron("*/5 * * * *", name="poller")
        async def poll():
            pass

        status = scheduler.status()
        assert len(status) == 1
        assert status[0]["name"] == "poller"
        assert status[0]["run_count"] == 0
        assert status[0]["last_run"] is None

    def test_scheduler_runs_async_task(self):
        """Scheduler fires async tasks at matching minute boundaries."""
        call_log = []

        async def run_test():
            scheduler = CronScheduler()

            # Use a fixed "now" by monkeypatching — simpler: just use * * * * *
            @scheduler.cron("* * * * *")
            async def counter():
                call_log.append(1)

            # Manually trigger the dispatch for "now"
            now = datetime.now()
            from cron_lite.cron_lite import cron_matches as cm
            for task in scheduler.tasks:
                if cm(task.expression, now):
                    asyncio.create_task(scheduler._run_task(task))

            await asyncio.sleep(0.1)  # let tasks execute

        asyncio.run(run_test())
        assert len(call_log) == 1

    def test_scheduler_runs_sync_task(self):
        """Scheduler fires sync tasks via executor."""
        call_log = []

        def sync_job():
            call_log.append(1)

        async def run_test():
            scheduler = CronScheduler()
            task = scheduler.add_task("* * * * *", sync_job)
            await scheduler._run_task(task)

        asyncio.run(run_test())
        assert call_log == [1]

    def test_scheduler_catches_exceptions(self):
        """Exceptions in tasks are caught and counted, not propagated."""
        async def run_test():
            scheduler = CronScheduler()

            @scheduler.cron("* * * * *")
            async def boom():
                raise RuntimeError("intentional error")

            task = scheduler.tasks[0]
            await scheduler._run_task(task)
            assert task.error_count == 1
            assert task.run_count == 0  # not incremented on error

        asyncio.run(run_test())

    def test_stop_sets_running_false(self):
        scheduler = CronScheduler()
        scheduler._running = True
        scheduler.stop()
        assert scheduler._running is False
