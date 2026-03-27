# ==============================================================================
# DAG: london_cycling_dbt_refresh
#
# dbt-only refresh – runs dbt without re-ingesting raw data.
# Useful when:
#   • You changed a dbt model and want to test the rebuild without waiting for ingestion
#   • You want to refresh a subset of models (use the dbt_select param)
#   • You need an emergency redeploy of the dbt layer after a hotfix
#
# Steps
# ──────────────────────────────────────────────────────────────────────────────
#   Task 1  dbt_refresh – deps + build (with optional --full-refresh / --select)
#
# Schedule
# ──────────────────────────────────────────────────────────────────────────────
# No schedule by default (schedule=None).
# Uncomment the `schedule` line below to enable a daily 05:00 UTC run.
#
# Params (overridable via "Trigger DAG w/ config"):
#   dbt_full_refresh (bool) – pass --full-refresh to dbt build (default false)
#   dbt_select       (str)  – optional dbt selector (e.g. "staging" or "marts")
# ==============================================================================

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from airflow import DAG
from airflow.models import Variable
from airflow.models.param import Param
from airflow.operators.bash import BashOperator

# ---------------------------------------------------------------------------
# Default arguments
# ---------------------------------------------------------------------------
default_args = {
    "owner": "london-cycling",
    "depends_on_past": False,
    "retries": 1,
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
# DAG definition
# ---------------------------------------------------------------------------
with DAG(
    dag_id="london_cycling_dbt_refresh",
    description=(
        "Lightweight dbt-only refresh: run dbt deps + dbt build against "
        "existing BigQuery raw data without re-ingesting."
    ),
    default_args=default_args,
    schedule=None,             # manual trigger by default; set to "0 5 * * *" for daily 05:00 UTC
    start_date=datetime(2024, 1, 1, tzinfo=timezone.utc),
    catchup=False,
    max_active_runs=1,
    tags=["london-cycling", "dbt", "manual"],
    params={
        "dbt_full_refresh": Param(
            False,
            type="boolean",
            description=(
                "Pass --full-refresh to dbt build. Drops and fully rebuilds all "
                "incremental models. Use sparingly on large BigQuery datasets."
            ),
        ),
        "dbt_select": Param(
            "",
            type="string",
            description=(
                "Optional dbt node selector string (e.g. 'staging' or 'marts.cycling'). "
                "When non-empty, adds --select <value> to dbt build so only matching "
                "models are built. Leave blank to build everything."
            ),
        ),
    },
) as dag:

    # ── Task 1 – dbt refresh ──────────────────────────────────────────────────
    dbt_refresh = BashOperator(
        task_id="dbt_refresh",
        bash_command="""
set -e
cd {{ var.value.get('LONDON_PROJECT_PATH', '/app') }}

# Step 1: install / update dbt packages (dbt_utils etc.)
dbt deps --profiles-dir . --project-dir .

# Step 2: build with optional flags
dbt build \\
  --profiles-dir . --project-dir . --target prod \\
  {% if params.dbt_full_refresh %}--full-refresh {% endif %}\\
  {% if params.dbt_select %}--select {{ params.dbt_select }}{% endif %}
""",
        env=_shared_env,
        append_env=True,
        doc_md=(
            "Run dbt deps + dbt build against BigQuery. "
            "Supports optional --full-refresh and --select flags via DAG params."
        ),
    )
