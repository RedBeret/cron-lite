"""
cron-lite: Zero-dependency async cron scheduler for Python.

Single-file implementation. Drop it in any project.
Supports standard cron syntax: minute hour dom month dow
"""

from __future__ import annotations

import asyncio
import inspect
import logging
import traceback
from dataclasses import dataclass, field
from datetime import datetime
from typing import Callable, Coroutine, Any

__all__ = ["CronExpression", "CronTask", "CronScheduler", "parse_cron", "cron_matches"]

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Cron expression parsing
# ---------------------------------------------------------------------------

# Field ranges: (min_val, max_val)
_FIELD_RANGES = {
    "minute": (0, 59),
    "hour": (0, 23),
    "dom": (1, 31),
    "month": (1, 12),
    "dow": (0, 7),  # 0 and 7 are both Sunday
}

_FIELD_NAMES = ["minute", "hour", "dom", "month", "dow"]

# Named month/dow aliases
_MONTH_NAMES = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}
_DOW_NAMES = {
    "sun": 0, "mon": 1, "tue": 2, "wed": 3, "thu": 4, "fri": 5, "sat": 6,
}


@dataclass
class CronExpression:
    """Parsed cron expression with pre-computed match sets per field."""
    minute: set[int]
    hour: set[int]
    dom: set[int]
    month: set[int]
    dow: set[int]   # 0-6, where 0 and 7 both map to Sunday (0)
    raw: str = ""


def _resolve_aliases(token: str, field: str) -> str:
    """Replace month/dow name aliases with their numeric equivalents."""
    token_lower = token.lower()
    if field == "month" and token_lower in _MONTH_NAMES:
        return str(_MONTH_NAMES[token_lower])
    if field == "dow" and token_lower in _DOW_NAMES:
        return str(_DOW_NAMES[token_lower])
    return token


def _parse_field(token: str, field: str) -> set[int]:
    """
    Parse a single cron field token into a set of matching integers.

    Supported syntax:
      *          — all values in range
      n          — single value
      n-m        — range
      n,m,k      — list of values
      */s        — every s-th value across full range
      n-m/s      — every s-th value in range n-m
      n,m/s      — NOT standard, raise ValueError
    """
    lo, hi = _FIELD_RANGES[field]
    token = _resolve_aliases(token, field)

    # Handle comma-separated lists first
    if "," in token:
        result: set[int] = set()
        for part in token.split(","):
            result |= _parse_field(part.strip(), field)
        return result

    # Handle step
    step = 1
    if "/" in token:
        parts = token.split("/", 1)
        if len(parts) != 2:
            raise ValueError(f"Invalid step syntax in field '{field}': {token!r}")
        token, step_str = parts
        try:
            step = int(step_str)
        except ValueError:
            raise ValueError(f"Step must be integer in field '{field}': {step_str!r}")
        if step <= 0:
            raise ValueError(f"Step must be positive in field '{field}': {step}")

    # Determine the range
    if token == "*":
        start, end = lo, hi
    elif "-" in token:
        range_parts = token.split("-", 1)
        try:
            start = int(_resolve_aliases(range_parts[0], field))
            end = int(_resolve_aliases(range_parts[1], field))
        except ValueError:
            raise ValueError(f"Invalid range in field '{field}': {token!r}")
        if not (lo <= start <= hi and lo <= end <= hi):
            raise ValueError(
                f"Range {start}-{end} out of bounds [{lo}-{hi}] for field '{field}'"
            )
    else:
        try:
            val = int(token)
        except ValueError:
            raise ValueError(f"Invalid value in field '{field}': {token!r}")
        if not (lo <= val <= hi):
            raise ValueError(
                f"Value {val} out of bounds [{lo}-{hi}] for field '{field}'"
            )
        if step == 1:
            return {val}
        # n/s means n to hi with step s
        start, end = val, hi

    return set(range(start, end + 1, step))


def parse_cron(expression: str) -> CronExpression:
    """
    Parse a 5-field cron expression string.

    Format: ``minute hour dom month dow``

    Examples::

        parse_cron("* * * * *")          # every minute
        parse_cron("0 8 * * 1-5")        # 8 AM weekdays
        parse_cron("*/15 * * * *")       # every 15 minutes
        parse_cron("0 9,17 * * *")       # 9 AM and 5 PM daily
        parse_cron("30 7 * * MON-FRI")   # 7:30 AM weekdays

    Raises:
        ValueError: If the expression is invalid.
    """
    parts = expression.split()
    if len(parts) != 5:
        raise ValueError(
            f"Cron expression must have exactly 5 fields, got {len(parts)}: {expression!r}"
        )

    minute_tok, hour_tok, dom_tok, month_tok, dow_tok = parts
    try:
        minute = _parse_field(minute_tok, "minute")
        hour = _parse_field(hour_tok, "hour")
        dom = _parse_field(dom_tok, "dom")
        month = _parse_field(month_tok, "month")
        dow_raw = _parse_field(dow_tok, "dow")
    except ValueError as exc:
        raise ValueError(f"Invalid cron expression {expression!r}: {exc}") from exc

    # Normalize day-of-week: map 7 -> 0 (both mean Sunday)
    dow = {d % 7 for d in dow_raw}

    return CronExpression(
        minute=minute,
        hour=hour,
        dom=dom,
        month=month,
        dow=dow,
        raw=expression,
    )


def cron_matches(expr: CronExpression, dt: datetime) -> bool:
    """
    Return True if the given datetime matches the cron expression.

    Day-of-week uses 0=Monday ... 6=Sunday per Python's ``datetime.weekday()``,
    but we store Sunday as 0 in the expression (cron convention). We map accordingly.
    """
    if dt.month not in expr.month:
        return False
    if dt.hour not in expr.hour:
        return False
    if dt.minute not in expr.minute:
        return False
    if dt.day not in expr.dom:
        return False

    # Python weekday(): 0=Monday ... 6=Sunday
    # Cron dow: 0=Sunday, 1=Monday ... 6=Saturday
    py_dow = dt.weekday()           # 0=Mon ... 6=Sun
    cron_dow = (py_dow + 1) % 7    # 0=Sun, 1=Mon ... 6=Sat
    if cron_dow not in expr.dow:
        return False

    return True


# ---------------------------------------------------------------------------
# Scheduler
# ---------------------------------------------------------------------------

@dataclass
class CronTask:
    """A registered cron task."""
    name: str
    expression: CronExpression
    func: Callable
    is_async: bool
    last_run: datetime | None = None
    run_count: int = 0
    error_count: int = 0


class CronScheduler:
    """
    Async cron scheduler with decorator and imperative registration.

    Usage::

        import asyncio
        from cron_lite import CronScheduler

        scheduler = CronScheduler()

        @scheduler.cron("*/5 * * * *")
        async def every_five_minutes():
            print("tick")

        asyncio.run(scheduler.run())

    The scheduler checks every 30 seconds and fires tasks once per matching minute.
    """

    def __init__(self) -> None:
        self._tasks: list[CronTask] = []
        self._running = False

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------

    def cron(self, expression: str, *, name: str | None = None):
        """Decorator to register a function as a cron task.

        Args:
            expression: Standard 5-field cron expression.
            name: Optional human-readable task name. Defaults to function name.

        Example::

            @scheduler.cron("0 8 * * 1-5")
            async def morning_briefing():
                ...
        """
        def decorator(func: Callable) -> Callable:
            self.add_task(expression, func, name=name)
            return func
        return decorator

    def add_task(
        self,
        expression: str,
        func: Callable,
        *,
        name: str | None = None,
    ) -> CronTask:
        """Register a function as a cron task imperatively.

        Args:
            expression: Standard 5-field cron expression.
            func: Callable (sync or async) to invoke.
            name: Optional task name.

        Returns:
            The created :class:`CronTask`.
        """
        parsed = parse_cron(expression)
        task = CronTask(
            name=name or getattr(func, "__name__", str(func)),
            expression=parsed,
            func=func,
            is_async=inspect.iscoroutinefunction(func),
        )
        self._tasks.append(task)
        logger.debug("Registered task %r with expression %r", task.name, expression)
        return task

    # ------------------------------------------------------------------
    # Execution
    # ------------------------------------------------------------------

    async def _run_task(self, task: CronTask) -> None:
        """Execute a single task, catching and logging any exception."""
        try:
            logger.debug("Running task %r", task.name)
            if task.is_async:
                await task.func()
            else:
                loop = asyncio.get_event_loop()
                await loop.run_in_executor(None, task.func)
            task.last_run = datetime.now()
            task.run_count += 1
            logger.debug("Task %r completed (run #%d)", task.name, task.run_count)
        except Exception:
            task.error_count += 1
            logger.error(
                "Task %r raised an exception (error #%d):\n%s",
                task.name,
                task.error_count,
                traceback.format_exc(),
            )

    async def run(self) -> None:
        """Start the scheduler loop. Runs until :meth:`stop` is called.

        Checks once every 30 seconds. Tasks fire at most once per minute
        boundary to avoid duplicate runs.
        """
        self._running = True
        last_minute: int = -1
        logger.info("CronScheduler started with %d task(s)", len(self._tasks))

        while self._running:
            now = datetime.now()
            current_minute = now.hour * 60 + now.minute

            if current_minute != last_minute:
                last_minute = current_minute
                for task in self._tasks:
                    if cron_matches(task.expression, now):
                        asyncio.create_task(self._run_task(task))

            await asyncio.sleep(30)

        logger.info("CronScheduler stopped")

    def stop(self) -> None:
        """Signal the scheduler to stop after the current sleep cycle."""
        self._running = False

    # ------------------------------------------------------------------
    # Introspection
    # ------------------------------------------------------------------

    @property
    def tasks(self) -> list[CronTask]:
        """Return a copy of the registered task list."""
        return list(self._tasks)

    def status(self) -> list[dict]:
        """Return task status as a list of dicts (useful for monitoring)."""
        return [
            {
                "name": t.name,
                "expression": t.expression.raw,
                "is_async": t.is_async,
                "run_count": t.run_count,
                "error_count": t.error_count,
                "last_run": t.last_run.isoformat() if t.last_run else None,
            }
            for t in self._tasks
        ]
