"""
fastapi_integration.py — cron-lite with FastAPI

Demonstrates how to wire cron-lite into FastAPI's lifespan context manager
so the scheduler starts with the app and stops cleanly on shutdown.

Run with:

    pip install cron-lite fastapi uvicorn
    uvicorn examples.fastapi_integration:app --reload

The scheduler runs in the background alongside the FastAPI server.
Visit http://localhost:8000/status to see task run counts.
"""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from datetime import datetime

from cron_lite import CronScheduler

try:
    from fastapi import FastAPI
    from fastapi.responses import JSONResponse
except ImportError:
    raise SystemExit(
        "FastAPI is not installed.\n"
        "Install it with: pip install fastapi uvicorn\n"
        "Then run: uvicorn examples.fastapi_integration:app"
    )

# ---------------------------------------------------------------------------
# Scheduler setup — define tasks at module level
# ---------------------------------------------------------------------------

scheduler = CronScheduler()

_stats: dict[str, int] = {"cleanups": 0, "heartbeats": 0}


@scheduler.cron("*/5 * * * *")
async def cleanup():
    """Run every 5 minutes."""
    _stats["cleanups"] += 1
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Cleanup #{_stats['cleanups']}")


@scheduler.cron("* * * * *")
async def heartbeat():
    """Run every minute."""
    _stats["heartbeats"] += 1
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Heartbeat #{_stats['heartbeats']}")


@scheduler.cron("0 0 * * *")
async def daily_reset():
    """Run at midnight."""
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Daily reset triggered")


# ---------------------------------------------------------------------------
# FastAPI lifespan — start/stop scheduler alongside the app
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: launch scheduler as a background task
    task = asyncio.create_task(scheduler.run())
    print(f"Scheduler started with {len(scheduler.tasks)} task(s)")
    try:
        yield
    finally:
        # Shutdown: stop the scheduler and wait for the task to finish
        scheduler.stop()
        task.cancel()
        try:
            await asyncio.wait_for(task, timeout=2.0)
        except (asyncio.CancelledError, asyncio.TimeoutError):
            pass
        print("Scheduler stopped")


app = FastAPI(
    title="cron-lite FastAPI Example",
    description="Demonstrates background cron scheduling in a FastAPI app.",
    lifespan=lifespan,
)


@app.get("/")
async def root():
    return {"message": "cron-lite is running in the background"}


@app.get("/status")
async def status():
    """Return scheduler task status and run counts."""
    return JSONResponse({
        "tasks": scheduler.status(),
        "stats": _stats,
    })


@app.get("/tasks")
async def list_tasks():
    """List all registered cron tasks."""
    return {
        "count": len(scheduler.tasks),
        "tasks": [
            {
                "name": t.name,
                "expression": t.expression.raw,
                "is_async": t.is_async,
            }
            for t in scheduler.tasks
        ],
    }
