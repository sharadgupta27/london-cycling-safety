# ==============================================================================
# DAG: london_cycling_full_pipeline
#
# Full production pipeline – runs on a weekly schedule (Mon 03:00 UTC) and
# can also be triggered manually via the Airflow UI.
#
# Steps
# ──────────────────────────────────────────────────────────────────────────────
#   Task 1  ingest_tfl       – dlt ingests TFL Santander cycling data → BigQuery
#   Task 2  ingest_accidents – dlt ingests UK STATS19 accident data  → BigQuery
#   Task 3  dbt_build        – dbt deps + dbt build (staging → intermediate → marts)
#
# Configuration
# ──────────────────────────────────────────────────────────────────────────────
# All tasks run as DockerOperator tasks using the project image.
# Sensitive values (GCP project, dataset, credential path, etc.) are read
# from Airflow Variables / environment – nothing is hardcoded in this file.
#
# Airflow Variables used (set via UI → Admin → Variables, or env AIRFLOW_VAR_*):
#   LONDON_PROJECT_PATH   – absolute host path to the project root
#   CREDENTIALS_PATH      – absolute host path to the credentials/ directory
#   GCP_PROJECT_ID        – Google Cloud project ID
#   GCP_BQ_LOCATION       – BigQuery location (e.g. "EU")
#   CREDENTIALS_FILENAME  – service-account JSON filename inside credentials/
#
# DAG-level params (overridable at trigger time via "Trigger w/ config"):
#   tfl_n_files      (int)  – number of TFL weekly CSV files to ingest (default 12)
#   accident_years   (str)  – comma-separated STATS19 years (default "2023,2024")
#   dbt_full_refresh (bool) – pass --full-refresh to dbt build (default false)
# ==============================================================================

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

from airflow import DAG
from airflow.models.param import Param
from airflow.operators.bash import BashOperator
from airflow.models import Variable

# ---------------------------------------------------------------------------
# Default arguments applied to every task
# ---------------------------------------------------------------------------
default_args = {
    "owner": "london-cycling",
    "depends_on_past": False,
    "retries": 2,
    "retry_delay": timedelta(minutes=2),
    "retry_exponential_backoff": False,
}

# ---------------------------------------------------------------------------
# Airflow Variables (with sensible fallbacks for local dev)
# ---------------------------------------------------------------------------
LONDON_PROJECT_PATH = Variable.get("LONDON_PROJECT_PATH", default_var="/app")
CREDENTIALS_PATH    = Variable.get("CREDENTIALS_PATH",    default_var="/credentials")
GCP_PROJECT_ID      = Variable.get("GCP_PROJECT_ID",      default_var="")
GCP_BQ_LOCATION     = Variable.get("GCP_BQ_LOCATION",     default_var="EU")
CREDENTIALS_FILE    = Variable.get(
    "CREDENTIALS_FILENAME",
    default_var="kestra-dataengg-d4b5461e94b4.json",
)

CREDS_CONTAINER = "/credentials"
APP_CONTAINER   = "/app"

# ---------------------------------------------------------------------------
# Shared environment exported to every BashOperator task
# ---------------------------------------------------------------------------
_shared_env = {
    "DESTINATION":                          "bigquery",
    "GOOGLE_APPLICATION_CREDENTIALS":       f"{CREDS_CONTAINER}/{CREDENTIALS_FILE}",
    "DESTINATION__BIGQUERY__PROJECT_ID":    GCP_PROJECT_ID,
    "DESTINATION__BIGQUERY__LOCATION":      GCP_BQ_LOCATION,
    # Make project root importable inside each task
    "PYTHONPATH":                           APP_CONTAINER,
}


# ---------------------------------------------------------------------------
# DAG definition
# ---------------------------------------------------------------------------
with DAG(
    dag_id="london_cycling_full_pipeline",
    description=(
        "Weekly production pipeline: ingest TFL + STATS19 via dlt, "
        "then run dbt staging → intermediate → marts."
    ),
    default_args=default_args,
    schedule="0 3 * * 1",          # every Monday at 03:00 UTC
    start_date=datetime(2024, 1, 1, tzinfo=timezone.utc),
    catchup=False,
    max_active_runs=1,
    tags=["london-cycling", "production", "weekly"],
    params={
        "tfl_n_files": Param(
            12,
            type="integer",
            minimum=1,
            description=(
                "Number of most-recent TFL weekly CSV files to download and ingest. "
                "Each file covers roughly one week of Santander cycle hire journeys. "
                "Default 12 ≈ 3 months."
            ),
        ),
        "accident_years": Param(
            "2023,2024",
            type="string",
            description=(
                "Comma-separated list of STATS19 years to load (e.g. '2023,2024'). "
                "dlt loads incrementally, so years already ingested are skipped unless "
                "the underlying data changes."
            ),
        ),
        "dbt_full_refresh": Param(
            False,
            type="boolean",
            description=(
                "When true, passes --full-refresh to dbt build so all incremental "
                "models are dropped and fully rebuilt. Use sparingly."
            ),
        ),
    },
) as dag:

    # ── Task 1 – Ingest TFL Santander cycling data ───────────────────────────
    ingest_tfl = BashOperator(
        task_id="ingest_tfl",
        bash_command=(
            "cd {{ var.value.get('LONDON_PROJECT_PATH', '/app') }} && "
            "TFL_N_FILES={{ params.tfl_n_files }} "
            "python ingestion/ingest_tfl_cycling.py"
        ),
        env={
            **_shared_env,
            "TFL_N_FILES": "{{ params.tfl_n_files }}",
        },
        append_env=True,
        doc_md="Ingest TFL Santander cycle-hire data into BigQuery via dlt.",
    )

    # ── Task 2 – Ingest UK STATS19 accident data ─────────────────────────────
    ingest_accidents = BashOperator(
        task_id="ingest_accidents",
        bash_command=(
            "cd {{ var.value.get('LONDON_PROJECT_PATH', '/app') }} && "
            "ACCIDENT_YEARS={{ params.accident_years }} "
            "python ingestion/ingest_uk_accidents.py"
        ),
        env={
            **_shared_env,
            "ACCIDENT_YEARS": "{{ params.accident_years }}",
        },
        append_env=True,
        doc_md="Ingest UK STATS19 road accident/casualty data into BigQuery via dlt.",
    )

    # ── Task 3 – dbt build ───────────────────────────────────────────────────
    dbt_build = BashOperator(
        task_id="dbt_build",
        bash_command="""
set -e
cd {{ var.value.get('LONDON_PROJECT_PATH', '/app') }}
dbt deps --profiles-dir . --project-dir .
dbt build \\
  --profiles-dir . --project-dir . --target prod \\
  {% if params.dbt_full_refresh %}--full-refresh{% endif %}
""",
        env=_shared_env,
        append_env=True,
        doc_md=(
            "Run dbt deps + dbt build (staging → intermediate → marts). "
            "Passes --full-refresh when the DAG param is set."
        ),
    )

    # ── Task dependencies ────────────────────────────────────────────────────
    # ingest_tfl and ingest_accidents run in parallel, then dbt_build follows.
    [ingest_tfl, ingest_accidents] >> dbt_build
