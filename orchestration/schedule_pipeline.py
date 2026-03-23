"""
orchestration/schedule_pipeline.py
====================================
Lightweight local scheduler (kept as a fallback alternative).

NOTE — Kestra is now the RECOMMENDED orchestration approach.
       See the `kestra/` directory and DEPLOYMENT.md §7 for setup instructions.
       Kestra provides a web UI, run history, retries, and a dedicated backfill
       flow.  Use this script only if you want a zero-dependency local scheduler
       without Docker.

Uses the `schedule` library to run pipeline.py on a configurable day/time
(default: every Monday at 03:00 local time).

Usage:
    # Run on schedule – blocks until stopped with Ctrl+C
    python orchestration/schedule_pipeline.py

    # Production BigQuery target
    python orchestration/schedule_pipeline.py --target prod

    # Run once immediately, then exit (useful for quick manual trigger)
    python orchestration/schedule_pipeline.py --run-now --target prod

    # Custom schedule (e.g. every day at 06:00)
    python orchestration/schedule_pipeline.py --time "06:00" --every day

Deployment alternatives:
    Windows Task Scheduler:
        1. Create a .bat wrapper:
               call C:\\path\\to\\.venv\\Scripts\\activate.bat
               python C:\\path\\to\\orchestration\\pipeline.py --target prod >> pipeline.log 2>&1
        2. Open Task Scheduler → Create Basic Task → Weekly, Monday 03:00, point to .bat

    Linux / macOS cron:
        0 3 * * 1  /path/to/.venv/bin/python /path/to/orchestration/pipeline.py --target prod >> pipeline.log 2>&1
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import time
from pathlib import Path

import schedule
from loguru import logger

PIPELINE_SCRIPT = Path(__file__).resolve().parent / "pipeline.py"


def run_pipeline(target: str) -> None:
    """Invoke pipeline.py as a subprocess."""
    logger.info("Starting scheduled pipeline run (target={})", target)
    result = subprocess.run(
        [sys.executable, str(PIPELINE_SCRIPT), "--target", target],
        cwd=PIPELINE_SCRIPT.parent.parent,
    )
    if result.returncode == 0:
        logger.success("Scheduled pipeline run completed successfully.")
    else:
        logger.error(
            "Scheduled pipeline run FAILED (exit code {}).", result.returncode
        )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="London Cycling Safety – Pipeline Scheduler"
    )
    parser.add_argument(
        "--target",
        default="dev",
        choices=["dev", "prod"],
        help="dbt target passed to pipeline.py: 'dev' (DuckDB) or 'prod' (BigQuery). Default: dev",
    )
    parser.add_argument(
        "--time",
        default="03:00",
        metavar="HH:MM",
        help="Time-of-day to run the pipeline (24-hour local time). Default: 03:00",
    )
    parser.add_argument(
        "--every",
        default="monday",
        choices=["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday", "day"],
        help="Frequency: day of week or 'day' for daily. Default: monday",
    )
    parser.add_argument(
        "--run-now",
        action="store_true",
        help="Run the pipeline once immediately, then exit (ignores --time / --every)",
    )
    args = parser.parse_args()

    # ── Immediate single run ───────────────────────────────────────────────────
    if args.run_now:
        run_pipeline(args.target)
        return

    # ── Schedule setup ────────────────────────────────────────────────────────
    freq_map = {
        "monday":    schedule.every().monday,
        "tuesday":   schedule.every().tuesday,
        "wednesday": schedule.every().wednesday,
        "thursday":  schedule.every().thursday,
        "friday":    schedule.every().friday,
        "saturday":  schedule.every().saturday,
        "sunday":    schedule.every().sunday,
        "day":       schedule.every().day,
    }
    job = freq_map[args.every].at(args.time)
    job.do(run_pipeline, target=args.target)

    logger.info(
        "Scheduler active — will run every {} at {} (target={}). Press Ctrl+C to stop.",
        args.every,
        args.time,
        args.target,
    )

    try:
        while True:
            schedule.run_pending()
            time.sleep(60)
    except KeyboardInterrupt:
        logger.info("Scheduler stopped.")


if __name__ == "__main__":
    main()
