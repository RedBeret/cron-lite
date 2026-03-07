# cron-lite

![Zero Dependencies](https://img.shields.io/badge/dependencies-zero-brightgreen)
![Python](https://img.shields.io/badge/python-3.10%2B-blue)
![License](https://img.shields.io/badge/license-MIT-blue)

**A single-file, zero-dependency async cron scheduler for Python.**

Drop it into any project — FastAPI, aiohttp, plain asyncio — and schedule tasks with standard cron syntax. No APScheduler. No Celery. No Redis. Just Python.

```python
from cron_lite import CronScheduler

scheduler = CronScheduler()

@scheduler.cron("*/5 * * * *")
async def every_five_minutes():
    print("tick")

@scheduler.cron("0 8 * * 1-5")
def weekday_morning_report():
    print("Good morning!")

asyncio.run(scheduler.run())
```

## Why cron-lite?

| | cron-lite | APScheduler | Celery |
|---|---|---|---|
| **Dependencies** | **0** | 3–8 | 10+ |
| **Lines of code** | **~260** | ~10,000 | ~50,000 |
| **Async-native** | ✅ | Partial | ❌ |
| **Single-file drop-in** | ✅ | ❌ | ❌ |
| **Cron syntax** | ✅ | ✅ | ✅ |

If you need "run this at 8 AM on weekdays", a 260-line file is the right tool — not a framework with five transitive dependencies.

## Install

```bash
pip install cron-lite
```

Or copy [`src/cron_lite/cron_lite.py`](src/cron_lite/cron_lite.py) directly into your project (it's a single file with no imports outside stdlib).

## Cron syntax

Standard 5-field format: `minute hour day_of_month month day_of_week`

| Field | Range | Special |
|---|---|---|
| minute | 0–59 | `*`, `*/5`, `0,15,30,45`, `0-30/5` |
| hour | 0–23 | same |
| day of month | 1–31 | same |
| month | 1–12 | `jan`–`dec` aliases |
| day of week | 0–7 | 0 and 7 = Sunday, `sun`–`sat` aliases |

**Common expressions:**

```
* * * * *         every minute
0 8 * * *         every day at 8:00 AM
0 8 * * 1-5       weekdays at 8:00 AM
*/15 * * * *      every 15 minutes
0 9,17 * * *      9 AM and 5 PM daily
0 0 1 * *         first of every month at midnight
30 7 * * MON-FRI  weekday mornings at 7:30
```

## API reference

### `parse_cron(expression: str) -> CronExpression`

Parse a cron expression string into a `CronExpression` dataclass.

```python
from cron_lite import parse_cron

expr = parse_cron("0 8 * * 1-5")
print(expr.hour)   # {8}
print(expr.dow)    # {1, 2, 3, 4, 5}
```

### `cron_matches(expr: CronExpression, dt: datetime) -> bool`

Check if a datetime matches a parsed expression.

```python
from cron_lite import parse_cron, cron_matches
from datetime import datetime

expr = parse_cron("0 8 * * *")
cron_matches(expr, datetime(2026, 3, 9, 8, 0))   # True
cron_matches(expr, datetime(2026, 3, 9, 8, 1))   # False
```

### `class CronScheduler`

```python
scheduler = CronScheduler()

# Decorator style
@scheduler.cron("*/5 * * * *", name="poller")
async def poll():
    ...

# Imperative style
scheduler.add_task("0 0 * * *", midnight_cleanup, name="nightly-cleanup")

# Start the loop (blocks until stop() is called)
asyncio.run(scheduler.run())

# Stop (call from another coroutine or signal handler)
scheduler.stop()

# Introspection
scheduler.tasks    # list of CronTask
scheduler.status() # list of dicts with run counts, last run times
```

### `CronTask` fields

| Field | Type | Description |
|---|---|---|
| `name` | `str` | Task name |
| `expression` | `CronExpression` | Parsed cron fields |
| `is_async` | `bool` | True if the function is a coroutine |
| `run_count` | `int` | Successful execution count |
| `error_count` | `int` | Exception count |
| `last_run` | `datetime \| None` | Last successful run |

## FastAPI integration

```python
import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI
from cron_lite import CronScheduler

scheduler = CronScheduler()

@scheduler.cron("*/5 * * * *")
async def cleanup_sessions():
    # runs every 5 minutes while the app is up
    ...

@scheduler.cron("0 3 * * *")
async def nightly_backup():
    ...

@asynccontextmanager
async def lifespan(app: FastAPI):
    task = asyncio.create_task(scheduler.run())
    yield
    scheduler.stop()
    task.cancel()

app = FastAPI(lifespan=lifespan)
```

## Error handling

Exceptions inside tasks are caught, logged, and counted — they never crash the scheduler.

```python
@scheduler.cron("* * * * *")
async def flaky_task():
    raise RuntimeError("oops")

# The scheduler keeps running. Check error_count:
print(scheduler.status())
# [{'name': 'flaky_task', 'error_count': 1, ...}]
```

## How it works

The scheduler checks once every **30 seconds**. At each check, if the current minute differs from the last-checked minute, it evaluates every registered task against the current time and fires matching ones as asyncio tasks. This means tasks run at most once per minute and the scheduler overhead is negligible.

Sync functions run in the default thread executor so they don't block the event loop.

## Development

```bash
git clone https://github.com/RedBeret/cron-lite
cd cron-lite
pip install -e ".[dev]"
pytest -v
```

## License

MIT
