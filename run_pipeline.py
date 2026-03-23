"""
run_pipeline.py – Single entry point for the full pipeline
============================================================
Delegates to orchestration/pipeline.py for all pipeline stages.
Use this script for local development; the orchestration script is the
production entry point.

Usage:
    python run_pipeline.py                   # full run (DuckDB dev target)
    python run_pipeline.py --skip-ingest     # transforms + dbt only
    python run_pipeline.py --dashboard       # launch dashboard after pipeline
    python run_pipeline.py --dashboard-only  # skip pipeline, open dashboard
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

from dotenv import load_dotenv
from loguru import logger

PROJECT_ROOT = Path(__file__).resolve().parent
load_dotenv(PROJECT_ROOT / ".env")


def step_launch_dashboard() -> None:
    dashboard_path = PROJECT_ROOT / "dashboard" / "app.py"
    port = os.getenv("STREAMLIT_PORT", "8501")
    cmd = [
        sys.executable, "-m", "streamlit", "run",
        str(dashboard_path),
        "--server.port", port,
        "--server.headless", "false",
    ]
    logger.info("Launching dashboard: {}", " ".join(cmd))
    subprocess.run(cmd, cwd=PROJECT_ROOT)


def main() -> None:
    parser = argparse.ArgumentParser(description="London Cycling Safety – Pipeline Runner")
    parser.add_argument("--skip-ingest",    action="store_true", help="Skip dlt ingestion steps")
    parser.add_argument("--dashboard",      action="store_true", help="Launch dashboard after pipeline")
    parser.add_argument("--dashboard-only", action="store_true", help="Skip pipeline, open dashboard")
    args = parser.parse_args()

    if args.dashboard_only:
        step_launch_dashboard()
        return

    # Delegate to orchestration/pipeline.py (dev/DuckDB target)
    cmd = [sys.executable, str(PROJECT_ROOT / "orchestration" / "pipeline.py")]
    if args.skip_ingest:
        cmd.append("--skip-ingest")

    result = subprocess.run(cmd, cwd=PROJECT_ROOT)
    pipeline_ok = (result.returncode == 0)

    if args.dashboard and pipeline_ok:
        step_launch_dashboard()
    elif args.dashboard:
        logger.warning("Dashboard not launched because pipeline had failures.")

    if not pipeline_ok:
        sys.exit(1)


if __name__ == "__main__":
    main()

