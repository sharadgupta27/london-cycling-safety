"""
orchestration/pipeline.py
==========================
Production pipeline orchestrator

Runs the full London Cycling Safety pipeline in sequence:
  1. Validate environment (GCP credentials check for BigQuery target)
  2. Ingest TFL cycling data via dlt
  3. Ingest UK STATS19 accident data via dlt
  4. Run DuckDB spatial transforms       (dev/DuckDB target only)
  5. dbt deps
  6. dbt build  (seeds → models → tests in dependency order)

Usage:
    # Local DuckDB (default)
    python orchestration/pipeline.py

    # Production BigQuery
    python orchestration/pipeline.py --target prod

    # Skip ingestion, run dbt only
    python orchestration/pipeline.py --skip-ingest
    python orchestration/pipeline.py --skip-ingest --target prod

    # Override data ranges
    python orchestration/pipeline.py --tfl-n-files 24 --accident-years 2021,2022,2023,2024
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
from pathlib import Path

from dotenv import load_dotenv
from loguru import logger

PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env")


# ── Helpers ───────────────────────────────────────────────────────────────────

def run_step(label: str, fn, *args, **kwargs) -> bool:
    """Execute a pipeline step, log timing, return True on success."""
    logger.info("=" * 60)
    logger.info("STEP: {}", label)
    logger.info("=" * 60)
    t0 = time.time()
    try:
        fn(*args, **kwargs)
        elapsed = time.time() - t0
        logger.success("✓ {} completed in {:.1f}s", label, elapsed)
        return True
    except Exception as exc:
        logger.error("✗ {} failed: {}", label, exc)
        return False


def _force_remove_dir(path: Path) -> None:
    """Remove a directory on Windows (handles deeply nested paths > MAX_PATH)."""
    import shutil
    import tempfile

    if not path.exists():
        return
    logger.info("Removing {} ...", path)

    if sys.platform == "win32":
        with tempfile.TemporaryDirectory() as empty_dir:
            subprocess.run(
                [
                    "robocopy", empty_dir, str(path),
                    "/MIR", "/R:1", "/W:0", "/NFL", "/NDL", "/NJH", "/NJS",
                ],
                capture_output=True,
            )
        time.sleep(0.3)
        subprocess.run(
            ["cmd", "/c", "rmdir", "/S", "/Q", str(path)],
            capture_output=True,
        )
        time.sleep(0.3)
        if path.exists():
            shutil.rmtree(path, ignore_errors=True)
    else:
        shutil.rmtree(path, ignore_errors=True)


# ── Pipeline steps ────────────────────────────────────────────────────────────

def validate_credentials() -> None:
    """Verify GCP service-account key is present and readable."""
    creds_path = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS", "")
    if not creds_path:
        raise EnvironmentError(
            "GOOGLE_APPLICATION_CREDENTIALS is not set.\n"
            "Add it to your .env file, e.g.:\n"
            "  GOOGLE_APPLICATION_CREDENTIALS=/path/to/credentials/service_account.json"
        )
    if not Path(creds_path).exists():
        raise FileNotFoundError(
            f"Service-account key not found at: {creds_path}\n"
            "Place your GCP JSON key at credentials/service_account.json "
            "and set GOOGLE_APPLICATION_CREDENTIALS in .env"
        )
    logger.info("✔ Credentials found at {}", creds_path)


def ingest_tfl(n_files: int | None = None) -> None:
    """Ingest TFL Santander journey + station data via dlt."""
    sys.path.insert(0, str(PROJECT_ROOT))
    if n_files is not None:
        os.environ["TFL_N_FILES"] = str(n_files)
    from ingestion.ingest_tfl_cycling import run as tfl_run  # noqa: PLC0415
    tfl_run()


def ingest_accidents(years: str | None = None) -> None:
    """Ingest UK STATS19 accident / casualty / vehicle data via dlt."""
    sys.path.insert(0, str(PROJECT_ROOT))
    if years is not None:
        os.environ["ACCIDENT_YEARS"] = years
    from ingestion.ingest_uk_accidents import run as acc_run  # noqa: PLC0415
    acc_run()


def spatial_transforms() -> None:
    """Run DuckDB spatial transforms (blackspot scoring, corridor geometry)."""
    sys.path.insert(0, str(PROJECT_ROOT))
    from transforms.spatial_transforms import run as spatial_run  # noqa: PLC0415
    spatial_run()


def dbt_pipeline(target: str = "dev") -> None:
    """Run dbt deps then dbt build (seeds → models → tests in DAG order)."""
    _force_remove_dir(PROJECT_ROOT / "dbt_packages")

    for cmd in [
        ["dbt", "deps", "--profiles-dir", ".", "--project-dir", "."],
        [
            "dbt", "build",
            "--profiles-dir", ".",
            "--project-dir", ".",
            "--target", target,
        ],
    ]:
        logger.info("Running: {}", " ".join(cmd))
        result = subprocess.run(cmd, cwd=PROJECT_ROOT, capture_output=False)
        if result.returncode != 0:
            raise RuntimeError(f"Command failed (exit {result.returncode}): {' '.join(cmd)}")


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="London Cycling Safety – Pipeline Orchestrator"
    )
    parser.add_argument(
        "--target",
        default="dev",
        choices=["dev", "prod"],
        help="dbt target: 'dev' uses DuckDB (default), 'prod' uses BigQuery",
    )
    parser.add_argument(
        "--skip-ingest",
        action="store_true",
        help="Skip dlt ingestion steps and run dbt build only",
    )
    parser.add_argument(
        "--tfl-n-files",
        type=int,
        default=None,
        metavar="N",
        help="Number of most-recent TFL weekly CSV files to ingest (overrides TFL_N_FILES env var)",
    )
    parser.add_argument(
        "--accident-years",
        type=str,
        default=None,
        metavar="YEARS",
        help="Comma-separated STATS19 years to load, e.g. 2022,2023,2024 (overrides ACCIDENT_YEARS env var)",
    )
    args = parser.parse_args()

    results: dict[str, bool] = {}

    # ── Credential check (BigQuery only) ──────────────────────────────────────
    if args.target == "prod":
        if not run_step("Validate GCP credentials", validate_credentials):
            logger.error("Aborting: credentials check failed.")
            sys.exit(1)

    # ── Set DESTINATION env var for ingestion scripts ─────────────────────────
    destination = "bigquery" if args.target == "prod" else "duckdb"
    os.environ.setdefault("DESTINATION", destination)
    logger.info("Destination: {}", destination.upper())

    # ── Ingestion ─────────────────────────────────────────────────────────────
    if not args.skip_ingest:
        results["Ingest TFL cycling"] = run_step(
            "Ingest TFL Cycling Data", ingest_tfl, args.tfl_n_files
        )
        results["Ingest UK accidents"] = run_step(
            "Ingest UK Accident Data", ingest_accidents, args.accident_years
        )

    # ── Spatial transforms (DuckDB / dev target only) ─────────────────────────
    if args.target == "dev" and not args.skip_ingest:
        results["Spatial transforms"] = run_step(
            "DuckDB Spatial Transforms", spatial_transforms
        )

    # ── dbt build ─────────────────────────────────────────────────────────────
    results["dbt build"] = run_step(
        f"dbt build (target={args.target})",
        dbt_pipeline,
        args.target,
    )

    # ── Summary ───────────────────────────────────────────────────────────────
    logger.info("")
    logger.info("=" * 60)
    logger.info("PIPELINE SUMMARY")
    logger.info("=" * 60)
    for step, ok in results.items():
        status = "✓ OK  " if ok else "✗ FAIL"
        logger.info("  {} {}", status, step)

    all_ok = all(results.values())
    if all_ok:
        logger.success("Pipeline completed successfully (target={})!", args.target)
    else:
        failed = [s for s, ok in results.items() if not ok]
        logger.warning("Pipeline finished with failures: {}", failed)
        sys.exit(1)


if __name__ == "__main__":
    main()
