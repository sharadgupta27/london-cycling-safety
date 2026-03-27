# ==============================================================================
# DAG: london_cycling_backfill
#
# Backfill / historical reload DAG – manual trigger only (no schedule).
# Use this DAG to:
#   • Load multiple years of historical STATS19 accident data for the first time
#   • Re-ingest a large batch of TFL journey files (e.g. 52 files ≈ 1 year)
#   • Rebuild all dbt incremental models from scratch (--full-refresh)
#
# The `skip_tfl` and `skip_accidents` boolean params let you re-run only the
# ingestion source that actually needs backfilling.
#
# Params (all overridable via "Trigger DAG w/ config"):
#   tfl_n_files      (int)  – number of TFL weekly CSV files to download (default 52)
#   accident_years   (str)  – comma-separated STATS19 years (default "2019,…,2024")
#   skip_tfl         (bool) – skip TFL ingestion (default false)
#   skip_accidents   (bool) – skip STATS19 ingestion (default false)
#   dbt_full_refresh (bool) – pass --full-refresh to dbt build (default true)
#
# Recommended first-run sequence
# ──────────────────────────────────────────────────────────────────────────────
#   1. In the Airflow UI click "Trigger DAG w/ config".
#   2. Set accident_years = "2019,2020,2021,2022,2023,2024"
#   3. Set tfl_n_files = 52  (≈ 1 year of weekly files)
#   4. Leave dbt_full_refresh = true (default).
#   5. Trigger.
# ==============================================================================

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from airflow import DAG
from airflow.models import Variable
from airflow.models.param import Param
from airflow.operators.bash import BashOperator
from airflow.operators.python import BranchPythonOperator
from airflow.operators.empty import EmptyOperator

# ---------------------------------------------------------------------------
# Default arguments applied to every task
# ---------------------------------------------------------------------------
default_args = {
    "owner": "london-cycling",
    "depends_on_past": False,
    "retries": 2,
    "retry_delay": timedelta(minutes=2),
}

# ---------------------------------------------------------------------------
# Airflow Variables
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

_shared_env = {
    "DESTINATION":                          "bigquery",
    "GOOGLE_APPLICATION_CREDENTIALS":       f"{CREDS_CONTAINER}/{CREDENTIALS_FILE}",
    "DESTINATION__BIGQUERY__PROJECT_ID":    GCP_PROJECT_ID,
    "DESTINATION__BIGQUERY__LOCATION":      GCP_BQ_LOCATION,
    "PYTHONPATH":                           APP_CONTAINER,
}


# ---------------------------------------------------------------------------
# Branch helpers
# ---------------------------------------------------------------------------
def _branch_tfl(**context) -> str:
    """Return the next task id depending on skip_tfl param."""
    skip = context["params"].get("skip_tfl", False)
    return "skip_tfl_log" if skip else "ingest_tfl_backfill"


def _branch_accidents(**context) -> str:
    """Return the next task id depending on skip_accidents param."""
    skip = context["params"].get("skip_accidents", False)
    return "skip_accidents_log" if skip else "ingest_accidents_backfill"


# ---------------------------------------------------------------------------
# DAG definition
# ---------------------------------------------------------------------------
with DAG(
    dag_id="london_cycling_backfill",
    description=(
        "Manual backfill / historical reload: ingest multiple years of STATS19 "
        "and/or a large batch of TFL files, then fully rebuild dbt models."
    ),
    default_args=default_args,
    schedule=None,                    # manual trigger only
    start_date=datetime(2024, 1, 1, tzinfo=timezone.utc),
    catchup=False,
    max_active_runs=1,
    tags=["london-cycling", "backfill", "manual"],
    params={
        "tfl_n_files": Param(
            52,
            type="integer",
            minimum=1,
            description=(
                "Number of TFL weekly CSV files to download for the backfill. "
                "52 ≈ one full year. Increase for longer historical periods."
            ),
        ),
        "accident_years": Param(
            "2019,2020,2021,2022,2023,2024",
            type="string",
            description=(
                "Comma-separated list of STATS19 years to backfill. "
                "All years listed are (re-)loaded; dlt handles deduplication internally."
            ),
        ),
        "skip_tfl": Param(
            False,
            type="boolean",
            description=(
                "Set to true to skip TFL ingestion and run only STATS19 + dbt. "
                "Useful when only the accident data needs to be reloaded."
            ),
        ),
        "skip_accidents": Param(
            False,
            type="boolean",
            description=(
                "Set to true to skip STATS19 ingestion and run only TFL + dbt. "
                "Useful when only the TFL data needs to be reloaded."
            ),
        ),
        "dbt_full_refresh": Param(
            True,
            type="boolean",
            description=(
                "Pass --full-refresh to dbt build so all incremental models are "
                "dropped and fully rebuilt. Defaults to TRUE for backfill runs."
            ),
        ),
    },
) as dag:

    # ── Branch: TFL ──────────────────────────────────────────────────────────
    branch_tfl = BranchPythonOperator(
        task_id="branch_tfl",
        python_callable=_branch_tfl,
    )

    ingest_tfl_backfill = BashOperator(
        task_id="ingest_tfl_backfill",
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
        doc_md="Backfill TFL Santander cycle-hire data into BigQuery.",
    )

    skip_tfl_log = EmptyOperator(
        task_id="skip_tfl_log",
        doc_md="TFL ingestion skipped (skip_tfl=true).",
    )

    # ── Branch: Accidents ────────────────────────────────────────────────────
    branch_accidents = BranchPythonOperator(
        task_id="branch_accidents",
        python_callable=_branch_accidents,
        trigger_rule="none_failed_min_one_success",
    )

    ingest_accidents_backfill = BashOperator(
        task_id="ingest_accidents_backfill",
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
        doc_md="Backfill UK STATS19 road accident data into BigQuery.",
    )

    skip_accidents_log = EmptyOperator(
        task_id="skip_accidents_log",
        doc_md="STATS19 accident ingestion skipped (skip_accidents=true).",
    )

    # ── Join before dbt ──────────────────────────────────────────────────────
    join_before_dbt = EmptyOperator(
        task_id="join_before_dbt",
        trigger_rule="none_failed_min_one_success",
    )

    # ── Task: dbt full rebuild ───────────────────────────────────────────────
    dbt_rebuild = BashOperator(
        task_id="dbt_rebuild",
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
        trigger_rule="none_failed_min_one_success",
        doc_md=(
            "Full dbt rebuild (deps + build) in BigQuery. "
            "Defaults to --full-refresh for backfill runs."
        ),
    )

    # ── Task dependencies ────────────────────────────────────────────────────
    branch_tfl >> [ingest_tfl_backfill, skip_tfl_log] >> branch_accidents
    branch_accidents >> [ingest_accidents_backfill, skip_accidents_log] >> join_before_dbt
    join_before_dbt >> dbt_rebuild
