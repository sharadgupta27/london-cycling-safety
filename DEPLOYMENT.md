# London Cycling Safety — Deployment Guide

Step-by-step instructions for anyone to run this project locally or deploy it in production.

---

## Table of Contents

1. [Project Overview](#1-project-overview)
2. [Prerequisites](#2-prerequisites)
3. [Get the Code](#3-get-the-code)
4. [Local Development (DuckDB)](#4-local-development-duckdb)
   - 4.1 Create Python environment
   - 4.2 Configure `.env`
   - 4.3 Run the full pipeline
   - 4.4 Run individual stages
   - 4.5 Launch the dashboard
5. [Windows Batch File Workflow](#5-windows-batch-file-workflow)
   - 5.1 Step 1 — Environment setup (`Step1_setup.bat`)
   - 5.2 Step 2A — Development pipeline (`Step2_run_dev.bat`)
   - 5.3 Step 2B — Production pipeline (`Step2_run_prod.bat`)
6. [Production — BigQuery](#6-production--bigquery)
   - 6.1 GCP prerequisites
   - 6.2 Configure `.env` and credentials
   - 6.3 Run the production pipeline
   - 6.4 Scheduled runs
7. [Apache Airflow Orchestration (Recommended)](#7-apache-airflow-orchestration-recommended)
   - 7.1 Start Airflow
   - 7.2 Configure the environment file
   - 7.3 Available DAGs
   - 7.4 Trigger a manual run
   - 7.5 Run the backfill (historical load)
   - 7.6 How tasks execute
8. [Project Structure](#8-project-structure)
9. [Troubleshooting](#9-troubleshooting)

---

## 1. Project Overview

End-to-end data pipeline that analyses the safety of London's Santander cycle hire network.

```
TFL Cycling Data            UK Road Safety Data (DfT STATS19)
        │                               │
        └──────────────┬────────────────┘
                       ▼
              [dlt] – incremental ingestion
                       │
                       ▼
              DuckDB (raw schema)   ←── local dev
             /  BigQuery (raw dataset) ←── production
                       │
                       ▼
     DuckDB: spatial_transforms.py (ST_Distance, ST_Buffer)
     BigQuery: BigQuery GIS inside dbt models
                       │
                       ▼
              [dbt] staging → intermediate → marts
                       │
                       ▼
         Streamlit + Folium + Plotly dashboard
         [schedule_pipeline.py] – optional weekly schedule (Mon 03:00)
         [Apache Airflow] – recommended scheduler (Docker, web UI, retries, history) → see §7
```

**What it produces:**
- Bike station blackspot risk scores (accidents within 500 m)
- Route corridor risk ranking (accidents along frequent journeys)
- Temporal safety patterns (rush hour, weekday vs weekend, seasonal)

---

## 2. Prerequisites

Install the following **before** proceeding.

| Tool | Version | Download |
|---|---|---|
| Python | ≥ 3.11 | https://python.org |
| uv | any | https://docs.astral.sh/uv/ |
| Git | any | https://git-scm.com |
| Google Cloud account | — | **only** for production / BigQuery option |
| Docker Desktop | any | https://docs.docker.com/desktop/ — **only** for Airflow orchestration option |

Verify Python is installed:

```bash
python --version    # Python 3.11.x or higher
git --version
```

---

## 3. Get the Code

```bash
git clone https://github.com/sharadgupta27/london-cycling-safety.git
cd london-cycling-safety
```

> Replace `<your-username>` with the actual GitHub username once pushed.

---

## 4. Local Development (DuckDB)

Everything here runs **entirely on your laptop** — no cloud account needed.

### 4.1 Create Python environment

**macOS / Linux:**
```bash
uv venv
source .venv/bin/activate
uv pip install -r requirements.txt
```

**Windows (PowerShell):**
```powershell
uv venv
.\.venv\Scripts\Activate.ps1
uv pip install -r requirements.txt
```

> If PowerShell blocks the activation script, run once:
> ```powershell
> Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
> ```

---

### 4.2 Configure `.env`

Copy the example file and edit it:

```bash
cp .env.example .env
```

Open `.env` in any editor — the defaults work as-is, but you can customise:

```dotenv
DUCKDB_PATH=london_cycling.duckdb   # where the local database lives
TFL_N_FILES=12                       # number of weekly TFL files to download
ACCIDENT_YEARS=2022,2023,2024        # which years of STATS19 accidents to load
BLACKSPOT_RADIUS_M=500               # accident search radius around each station
STREAMLIT_PORT=8501                  # dashboard port
```

---

### 4.3 Run the full pipeline

This single command runs all stages end-to-end:

```bash
python run_pipeline.py
```

Expected output (takes 5–15 min depending on internet speed):

```
[INFO] Stage 1/4 – TFL ingestion ...
  ✓ tfl_journeys: 1,400,000 rows loaded
  ✓ tfl_stations: 0 rows  (see Troubleshooting §8)

[INFO] Stage 2/4 – UK accidents ingestion ...
  ✓ accidents:  75,000 rows loaded
  ✓ casualties: 90,000 rows loaded
  ✓ vehicles:   120,000 rows loaded

[INFO] Stage 3/4 – Spatial transforms ...
  ✓ spatial_layer.station_blackspot_scores created
  ✓ spatial_layer.corridor_risk created

[INFO] Stage 4/4 – dbt run ...
  ✓ 9 models passed, 0 errors
```

---

### 4.4 Run individual stages

```bash
# Ingestion only
python ingestion/ingest_tfl_cycling.py
python ingestion/ingest_uk_accidents.py

# Spatial transforms only (DuckDB spatial extension)
python transforms/spatial_transforms.py

# dbt only (seeds + models + tests in DAG order)
dbt deps  --profiles-dir . --project-dir .
dbt build --profiles-dir . --project-dir .

# Skip ingestion, re-run transforms + dbt
python run_pipeline.py --skip-ingest
```

---

### 4.5 Launch the dashboard

```bash
python run_pipeline.py --dashboard
```

Or start the dashboard independently:

**macOS / Linux:**
```bash
streamlit run dashboard/app.py --server.port 8501
```

**Windows (PowerShell):**
```powershell
streamlit run dashboard\app.py --server.port 8501
```

Open **http://localhost:8501** in your browser.

---

## 5. Windows Batch File Workflow

Three batch files in the project root provide a clear, step-by-step workflow for Windows users.
Run them **in order**: setup first, then whichever pipeline you need.

```
Step1_setup.bat        ← run once (or after a clean clone)
    │
    ├─▶  Step2_run_dev.bat   ← local pipeline (DuckDB, no cloud account needed)
    └─▶  Step2_run_prod.bat  ← production pipeline (Google BigQuery)
```

---

### 5.1 Step 1 — Environment setup (`Step1_setup.bat`)

**Double-click** `Step1_setup.bat`, or from a terminal:

```bat
Step1_setup.bat
```

What it does:

| Step | Action |
|---|---|
| 1 | Checks Python 3.11+ is on PATH |
| 2 | Locates an existing `.venv` one level up; creates a project-local `.venv` if none is found |
| 3 | Installs all Python dependencies from `requirements.txt` using `uv` |
| 4 | Copies `.env.example` → `.env` if no `.env` exists yet |

Run this **once after cloning**, or again whenever `requirements.txt` changes.

---

### 5.2 Step 2A — Development pipeline (`Step2_run_dev.bat`)

Runs the full local (DuckDB) pipeline and launches the Streamlit dashboard.  
**No cloud account required.**

```bat
Step2_run_dev.bat
```

What it does:

| Step | Action |
|---|---|
| 1 | Ingests TFL + STATS19 data via dlt → local DuckDB |
| 2 | Runs DuckDB spatial transforms (blackspot scores, corridor geometry) |
| 3 | Runs `dbt build` — seeds → staging → intermediate → marts + tests |
| 4 | Launches Streamlit dashboard at **http://localhost:8501** |

> Press **Ctrl+C** in the terminal window to stop the dashboard when done.

---

### 5.3 Step 2B — Production pipeline (`Step2_run_prod.bat`)

Runs the full production pipeline writing to Google BigQuery.  
**Requires GCP credentials** — see §6 for setup.

```bat
Step2_run_prod.bat
```

Optional flag to skip ingestion and re-run only dbt:

```bat
Step2_run_prod.bat --skip-ingest
```

What it does:

| Step | Action |
|---|---|
| 1 | Installs BigQuery extras (`dlt[bigquery]`, `dbt-bigquery`) into the venv |
| 2 | Validates `.env` exists and warns if `credentials\service_account.json` is missing |
| 3 | Runs `orchestration/pipeline.py --target prod` (ingest → BigQuery + dbt build) |

---

## 6. Production — BigQuery

This section runs the production pipeline writing to Google BigQuery.  
No Docker needed — `orchestration/pipeline.py` handles everything.

### 6.1 GCP prerequisites

You need a Google Cloud project with billing enabled.

**Step 1 — Enable APIs (run once):**
```bash
gcloud services enable bigquery.googleapis.com bigquerystorage.googleapis.com
```

**Step 2 — Create a service account:**
```bash
gcloud iam service-accounts create london-cycling-pipeline \
  --display-name "London Cycling Pipeline"
```

**Step 3 — Grant required roles:**
```bash
export PROJECT_ID=$(gcloud config get-value project)

gcloud projects add-iam-policy-binding $PROJECT_ID \
  --member="serviceAccount:london-cycling-pipeline@${PROJECT_ID}.iam.gserviceaccount.com" \
  --role="roles/bigquery.dataEditor"

gcloud projects add-iam-policy-binding $PROJECT_ID \
  --member="serviceAccount:london-cycling-pipeline@${PROJECT_ID}.iam.gserviceaccount.com" \
  --role="roles/bigquery.jobUser"
```

**Step 4 — Download the key file:**
```bash
gcloud iam service-accounts keys create credentials/service_account.json \
  --iam-account="london-cycling-pipeline@${PROJECT_ID}.iam.gserviceaccount.com"
```

> `credentials/` is in `.gitignore` — the key will not be committed.

---

### 6.2 Configure `.env` and credentials

Edit `.env` (copy from `.env.example` if you haven't already):

```dotenv
GOOGLE_APPLICATION_CREDENTIALS=C:/path/to/london-cycling-safety/credentials/service_account.json
GCP_PROJECT_ID=your-gcp-project-id
GCP_BQ_DATASET=dbt_london_cycling
GCP_BQ_LOCATION=EU
```

> **Windows**: use forward slashes or double back-slashes in the path.

---

### 6.3 Run the production pipeline

**Windows — double-click** `Step2_run_prod.bat` (after running `Step1_setup.bat` once), or from a terminal:

```bat
Step2_run_prod.bat
```

Or use Python directly / Makefile:

```bash
python orchestration/pipeline.py --target prod

# or
make pipeline-prod
```

Expected behaviour:

| Step | What happens |
|---|---|
| Credential check | Verifies `GOOGLE_APPLICATION_CREDENTIALS` file exists |
| Ingest TFL | dlt downloads TFL CSVs → BigQuery `raw` dataset |
| Ingest accidents | dlt downloads STATS19 → BigQuery `raw` dataset |
| dbt build | `dbt deps` + `dbt build --target prod` (seeds → staging → marts + tests) |

On success, [BigQuery console](https://console.cloud.google.com/bigquery) shows:
- Dataset `raw` — `tfl_journeys`, `tfl_stations`, `uk_accidents`, `uk_casualties`, `uk_vehicles`
- Dataset `dbt_london_cycling` — `mart_blackspot_analysis`, `mart_corridor_risk`, `mart_temporal_safety`

---

### 6.4 Scheduled runs

**Option A — Python scheduler (blocks terminal):**
```bash
python orchestration/schedule_pipeline.py --target prod
# or
make schedule
```

**Option B — Windows Task Scheduler:**
1. Create a trigger: weekly, Monday, 03:00
2. Action: Start a program → `run_prod.bat`

**Option C — Linux / macOS cron:**
```bash
0 3 * * 1  /path/to/.venv/bin/python /path/to/orchestration/pipeline.py --target prod >> pipeline.log 2>&1
```

**Option D — Apache Airflow (Recommended — web UI, retries, history):**

Airflow is the preferred approach for any environment with Docker. It provides a web UI,
run history, automatic retries, and dedicated DAGs for full pipeline, backfill, and dbt refresh.

See **§7 Apache Airflow Orchestration** below for full setup instructions.

---

## 7. Apache Airflow Orchestration (Recommended)

[Apache Airflow](https://airflow.apache.org) is the recommended way to run and schedule the
production pipeline. It provides a web UI, run history, retries, and parameterised DAGs for
every workflow — replacing the fragile `schedule_pipeline.py / cron` approach.

### Prerequisites

- [Docker Desktop](https://docs.docker.com/desktop/install/windows-install/) running
- Root `.env` filled in (see §6.2)

### 7.1 Start Airflow

```bat
cd london-cycling-safety\airflow
docker compose up -d
```

First boot builds the custom Airflow image (≈ 2–3 min) and initialises the metadata DB.
Subsequent starts are instant.

```
# Or use the Makefile shortcut from the project root:
make airflow-up
```

| Endpoint | URL | Credentials |
|---|---|---|
| Airflow UI | http://localhost:8080 | admin / admin |

To stop:
```bat
docker compose down
# or
make airflow-down
```

### 7.2 Configure the environment file

All configuration is read from the single root `.env` file. Key variables used by Airflow:

| Variable | Example value | Purpose |
|---|---|---|
| `LONDON_PROJECT_PATH` | `C:/Users/gupta/Desktop/…/london-cycling-safety` | Mounted as `/app` inside task containers |
| `CREDENTIALS_PATH` | `…/london-cycling-safety/credentials` | Mounted as `/credentials` (read-only) |
| `CREDENTIALS_FILENAME` | `kestra-dataengg-d4b5461e94b4.json` | GCP service-account JSON filename |
| `GCP_PROJECT_ID` | `kestra-dataengg` | BigQuery project |
| `GCP_BQ_DATASET` | `dbt_london_cycling` | dbt target dataset prefix |
| `GCP_BQ_LOCATION` | `EU` | BigQuery dataset location |

These are automatically surfaced as Airflow Variables (`AIRFLOW_VAR_*`) so DAGs can read them
with `Variable.get(...)` without any manual UI configuration.

### 7.3 Available DAGs

| DAG | ID | Schedule | Purpose |
|---|---|---|---|
| Full pipeline | `london_cycling_full_pipeline` | Mon 03:00 UTC | Weekly production run – ingest TFL + STATS19 → dbt build |
| Backfill | `london_cycling_backfill` | Manual only | Load multiple years of historical data + full dbt rebuild |
| dbt refresh | `london_cycling_dbt_refresh` | Manual (optional daily) | Re-run dbt without re-ingesting |

DAG files live in `airflow/dags/`:

```
airflow/
├── docker-compose.yml         ← Airflow stack (webserver + scheduler + postgres)
└── dags/
    ├── full_pipeline.py       ← london_cycling_full_pipeline (weekly, Mon 03:00 UTC)
    ├── backfill.py            ← london_cycling_backfill (manual)
    └── dbt_refresh.py         ← london_cycling_dbt_refresh (manual)
```

### 7.4 Trigger a manual run

1. Open http://localhost:8080 and log in (admin / admin).
2. Click **DAGs** → select a DAG (e.g. `london_cycling_backfill`).
3. Click the **▶ Trigger DAG** button (top-right) → **Trigger DAG w/ config**.
4. Adjust JSON params as needed (e.g. `{"accident_years": "2019,2020,2021,2022,2023,2024"}`).
5. Click **Trigger**.

You can watch task logs in real-time by clicking on a task instance in the Grid or Graph view.

### 7.5 Run the backfill (first-time historical load)

Use DAG `london_cycling_backfill` with this config:

```json
{
    "accident_years":   "2019,2020,2021,2022,2023,2024",
    "tfl_n_files":      52,
    "dbt_full_refresh": true,
    "skip_tfl":         false,
    "skip_accidents":   false
}
```

| Param | Recommended value | Notes |
|---|---|---|
| `accident_years` | `"2019,2020,2021,2022,2023,2024"` | All available STATS19 years |
| `tfl_n_files` | `52` | ≈ 1 full year of weekly TFL files |
| `dbt_full_refresh` | `true` (default) | Rebuilds all incremental models from scratch |
| `skip_tfl` | `false` (default) | Set `true` to skip TFL and only reload accidents |
| `skip_accidents` | `false` (default) | Set `true` to skip STATS19 and only reload TFL |

### 7.6 How tasks execute

BashOperator tasks run directly inside the Airflow scheduler container.
The project root and credentials are bind-mounted so scripts run unmodified:

```
HOST                                      Container (Airflow scheduler)
──────────────────────────────────────── ───────────────────────
$LONDON_PROJECT_PATH               →     /app          (read-write)
$CREDENTIALS_PATH                  →     /credentials  (read-only)
```

All project Python dependencies (`dlt`, `dbt-bigquery`, etc.) are pre-installed in
the Airflow image via `Dockerfile.airflow`.

---

## 8. Project Structure

```
london-cycling-safety/
│
├── ingestion/
│   ├── ingest_tfl_cycling.py       # dlt pipeline: TFL Santander journey data
│   └── ingest_uk_accidents.py      # dlt pipeline: DfT STATS19 accident data
│
├── transforms/
│   └── spatial_transforms.py       # DuckDB spatial layer (local dev only)
│
├── models/                         # dbt models
│   ├── staging/                    # raw → clean column names + types
│   ├── intermediate/               # spatial joins, corridor risk, blackspot scores
│   │                               # (BigQuery GIS branches for production)
│   └── marts/                      # final analysis tables
│
├── dashboard/
│   ├── app.py                      # Streamlit entry point
│   ├── pages/                      # multi-page dashboard pages
│   └── utils/data_loader.py        # DuckDB query helpers
│
├── orchestration/
│   ├── pipeline.py              # production orchestrator (BigQuery target)
│   └── schedule_pipeline.py    # optional weekly scheduler
│
├── airflow/                        # Apache Airflow orchestration (recommended)
│   ├── docker-compose.yml          # Airflow webserver + scheduler + postgres
│   └── dags/
│       ├── full_pipeline.py        # weekly production run (Mon 03:00 UTC)
│       ├── backfill.py             # manual historical load
│       └── dbt_refresh.py          # dbt-only refresh
│
├── Dockerfile.airflow              # custom Airflow image with project deps
│
├── profiles.yml                    # dbt profiles (dev=DuckDB, prod=BigQuery)
├── dbt_project.yml                 # dbt project config
├── packages.yml                    # dbt packages (empty — no external deps)
├── run_pipeline.py                 # single entry point for all stages
├── requirements.txt                # Python dependencies (local dev)
├── .env.example                    # environment variable template
├── Step1_setup.bat                 # Windows: set up venv + install deps
├── Step2_run_dev.bat               # Windows: run local DuckDB pipeline + dashboard
├── Step2_run_prod.bat              # Windows: run production BigQuery pipeline
└── DEPLOYMENT.md                   # ← you are here
```

---

## 9. Troubleshooting

### `tfl_stations: 0 rows`

The oldest TFL CSV files (pre-2019) do not include latitude/longitude columns.  
The pipeline handles this gracefully — journeys still load correctly.  
Station data is derived from newer files; if 0 rows appear, increase `TFL_N_FILES` in `.env`:
```dotenv
TFL_N_FILES=50
```

---

### `ModuleNotFoundError` on `duckdb` or `dbt`

Your virtual environment may not be activated:
```bash
# macOS / Linux
source .venv/bin/activate

# Windows PowerShell
.\.venv\Scripts\Activate.ps1
```

---

### dbt error: `packages-install-path` locked on Windows

VS Code may hold a file lock on the dbt packages directory.  
The project uses `C:/Temp/dbt_packages_london_cycling` (outside the workspace) to avoid this.  
If you still hit the error, close VS Code and re-run, or set a custom path in `.env`:
```dotenv
DBT_PACKAGES_PATH=C:/Temp/dbt_packages_london_cycling
```

---

### `StreamlitAPIException` or dashboard blank

The DuckDB file may not have been built yet. Run the pipeline first:
```bash
python run_pipeline.py
# Windows: Step1_setup.bat, then Step2_run_dev.bat
```
Then start the dashboard separately:
```bash
streamlit run dashboard/app.py
```

---

### BigQuery `403 Access Denied`

The service account is missing a required role.  
Run the `gcloud projects add-iam-policy-binding` commands in §6.1 again and re-execute the pipeline.

---

### Airflow port 8080 already in use

Change the host port in `airflow/docker-compose.yml`:
```yaml
ports:
  - "8081:8080"   # change 8081 to any free port
```
Then open http://localhost:8081 instead of http://localhost:8080.

---

### DAG does not appear in the Airflow UI

Airflow scans `airflow/dags/` every 30 seconds. If a new DAG is missing after a minute:
1. Check for import errors: **Admin → DAG Import Errors** in the Airflow UI.
2. In terminal: `docker compose -f airflow/docker-compose.yml logs airflow-scheduler | tail -50`
3. Verify the DAG file is saved in `airflow/dags/` (bind-mounted as `/opt/airflow/dags`).

---

### `airflow-init` exits without creating admin user

```bash
docker compose -f airflow/docker-compose.yml logs airflow-init
```
Common causes: metadata DB connection issue (wait a few seconds and re-run `make airflow-up`),
or a leftover volume from a previous install. To reset completely:
```bash
docker compose -f airflow/docker-compose.yml down -v
make airflow-up
```

---

### GCP credentials not found inside Airflow tasks

Ensure `CREDENTIALS_PATH` in `.env` points to the directory containing the service-account JSON
(not to the JSON file itself). The directory is mounted read-only as `/credentials` inside the
Airflow scheduler container. Then verify `CREDENTIALS_FILENAME` matches the actual filename.
