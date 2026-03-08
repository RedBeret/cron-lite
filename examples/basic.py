"""
basic.py — cron-lite quickstart example

Run this to see the scheduler in action:

    pip install cron-lite
    python examples/basic.py

The scheduler prints a heartbeat every minute and a morning report at 8 AM
on weekdays. Press Ctrl+C to stop.
"""

import asyncio
import signal
import sys
from datetime import datetime

from cron_lite import CronScheduler

scheduler = CronScheduler()


@scheduler.cron("* * * * *")          # every minute
async def heartbeat():
    print(f"[{datetime.now().strftime('%H:%M:%S')}] heartbeat")


@scheduler.cron("0 8 * * 1-5")        # weekdays at 8 AM
def morning_report():
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Good morning! Starting daily report...")


@scheduler.cron("*/5 * * * *")        # every 5 minutes
async def periodic_cleanup():
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Running cleanup...")


@scheduler.cron("0 9,17 * * *")       # 9 AM and 5 PM daily
async def shift_boundary():
    hour = datetime.now().hour
    label = "start" if hour == 9 else "end"
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Shift {label}")


def _handle_shutdown(signum, frame):
    print("\nShutting down...")
    scheduler.stop()
    sys.exit(0)


def main():
    signal.signal(signal.SIGINT, _handle_shutdown)
    signal.signal(signal.SIGTERM, _handle_shutdown)

    print("cron-lite scheduler started.")
    print(f"Registered {len(scheduler.tasks)} task(s):")
    for task in scheduler.tasks:
        print(f"  {task.expression.raw!r:20}  →  {task.name}")
    print("\nWaiting for the next minute boundary... (Ctrl+C to stop)\n")

    asyncio.run(scheduler.run())


if __name__ == "__main__":
    main()
