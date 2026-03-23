"""
data_loader.py
==============
Backend-aware query helpers for the Streamlit dashboard.

Set DASHBOARD_TARGET=prod in .env to query BigQuery (production).
Default (DASHBOARD_TARGET=dev) queries the local DuckDB file.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import TYPE_CHECKING

import duckdb
import pandas as pd
import requests
import streamlit as st
from dotenv import load_dotenv

if TYPE_CHECKING:
    from google.cloud import bigquery as _bq_type

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
load_dotenv(PROJECT_ROOT / ".env")

DUCKDB_PATH = os.getenv("DUCKDB_PATH", "london_cycling.duckdb")
DB_FILE = PROJECT_ROOT / DUCKDB_PATH


# ── Backend detection ────────────────────────────────────────────────────────

def _use_bigquery() -> bool:
    """Return True when DASHBOARD_TARGET=prod (or DESTINATION=bigquery)."""
    val = os.getenv("DASHBOARD_TARGET", os.getenv("DESTINATION", "dev")).lower()
    return val in ("prod", "bigquery")


# ── DuckDB backend ───────────────────────────────────────────────────────────

def _con() -> duckdb.DuckDBPyConnection:
    """Open a read-only DuckDB connection."""
    con = duckdb.connect(str(DB_FILE), read_only=True)
    try:
        con.execute("LOAD spatial;")
    except Exception:
        pass
    return con


def _duckdb_query(sql: str) -> pd.DataFrame:
    con = _con()
    df = con.execute(sql).df()
    con.close()
    return df


# ── BigQuery backend ─────────────────────────────────────────────────────────

_bq_client_instance = None


def _bq_client() -> "_bq_type.Client":
    """Return a cached BigQuery client authenticated via the service-account key."""
    global _bq_client_instance
    if _bq_client_instance is None:
        from google.cloud import bigquery
        from google.oauth2 import service_account

        project = os.getenv("GCP_PROJECT_ID")
        creds_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
        if creds_path and Path(creds_path).exists():
            creds = service_account.Credentials.from_service_account_file(
                creds_path,
                scopes=["https://www.googleapis.com/auth/bigquery"],
            )
            _bq_client_instance = bigquery.Client(project=project, credentials=creds)
        else:
            # Fall back to Application Default Credentials
            _bq_client_instance = bigquery.Client(project=project)
    return _bq_client_instance


def _bq_table(schema_suffix: str, table: str) -> str:
    """Return a fully-qualified BigQuery table reference.

    schema_suffix examples: 'marts', 'staging', 'intermediate', 'raw', ''
    dbt naming: {GCP_BQ_DATASET}_{schema_suffix}  (e.g. dbt_london_cycling_marts)
    """
    project = os.getenv("GCP_PROJECT_ID", "kestra-dataengg")
    base = os.getenv("GCP_BQ_DATASET", "dbt_london_cycling")
    if schema_suffix == "raw":
        dataset = "raw"
    elif schema_suffix == "":
        dataset = base
    else:
        dataset = f"{base}_{schema_suffix}"
    return f"`{project}`.`{dataset}`.`{table}`"


def _bq_query(sql: str) -> pd.DataFrame:
    """Run a BigQuery SQL string and return a pandas DataFrame."""
    client = _bq_client()
    return client.query(sql).to_dataframe()


@st.cache_data(ttl=600, show_spinner=False)
def load_blackspot_stations() -> pd.DataFrame:
    """All bike stations with risk scores and colours."""
    if _use_bigquery():
        tbl = _bq_table("marts", "mart_blackspot_analysis")
        return _bq_query(f"SELECT * FROM {tbl} ORDER BY weighted_risk_score DESC")
    return _duckdb_query("""
        SELECT * FROM main_marts.mart_blackspot_analysis
        ORDER BY weighted_risk_score DESC
    """)


@st.cache_data(ttl=600, show_spinner=False)
def load_corridor_risk(top_n: int = 50) -> pd.DataFrame:
    """Top corridors by composite risk score."""
    top_n = max(1, int(top_n))
    if _use_bigquery():
        tbl = _bq_table("marts", "mart_corridor_risk_score")
        return _bq_query(f"SELECT * FROM {tbl} ORDER BY risk_rank LIMIT {top_n}")
    return _duckdb_query(f"""
        SELECT * FROM main_marts.mart_corridor_risk_score
        ORDER BY risk_rank LIMIT {top_n}
    """)


@st.cache_data(ttl=600, show_spinner=False)
def load_accidents_raw() -> pd.DataFrame:
    """Raw accident points for the heatmap layer."""
    cols = """
        accident_index, longitude, latitude,
        accident_severity, severity_label,
        number_of_casualties, hour_of_day, day_of_week, day_type, year
    """
    where = "longitude IS NOT NULL AND latitude IS NOT NULL"
    if _use_bigquery():
        tbl = _bq_table("staging", "stg_accidents")
        return _bq_query(f"SELECT {cols} FROM {tbl} WHERE {where} LIMIT 100000")
    return _duckdb_query(f"""
        SELECT {cols} FROM main_staging.stg_accidents
        WHERE {where} LIMIT 100000
    """)


@st.cache_data(ttl=600, show_spinner=False)
def load_temporal_hourly() -> pd.DataFrame:
    """Hourly temporal patterns."""
    if _use_bigquery():
        tbl = _bq_table("marts", "mart_temporal_safety")
        return _bq_query(f"""
            SELECT * FROM {tbl}
            WHERE grain = 'hourly'
            ORDER BY year, CAST(dimension AS INT64)
        """)
    return _duckdb_query("""
        SELECT * FROM main_marts.mart_temporal_safety
        WHERE grain = 'hourly'
        ORDER BY year, CAST(dimension AS INTEGER)
    """)


@st.cache_data(ttl=600, show_spinner=False)
def load_temporal_period() -> pd.DataFrame:
    """Time-period (rush hour etc.) breakdown."""
    if _use_bigquery():
        tbl = _bq_table("marts", "mart_temporal_safety")
        return _bq_query(f"""
            SELECT * FROM {tbl}
            WHERE grain = 'time_period'
            ORDER BY year, dimension
        """)
    return _duckdb_query("""
        SELECT * FROM main_marts.mart_temporal_safety
        WHERE grain = 'time_period'
        ORDER BY year, dimension
    """)


@st.cache_data(ttl=600, show_spinner=False)
def load_monthly_trend() -> pd.DataFrame:
    """Monthly accident trend."""
    if _use_bigquery():
        tbl = _bq_table("marts", "mart_temporal_safety")
        return _bq_query(f"""
            SELECT * FROM {tbl}
            WHERE grain = 'monthly'
            ORDER BY year, dimension
        """)
    return _duckdb_query("""
        SELECT * FROM main_marts.mart_temporal_safety
        WHERE grain = 'monthly'
        ORDER BY year, dimension
    """)


@st.cache_data(ttl=600, show_spinner=False)
def pipeline_summary() -> dict:
    """Record counts for the home page status panel."""
    raw_tables = {
        "journeys":   "tfl_journeys",
        "stations":   "tfl_stations",
        "accidents":  "uk_accidents",
        "casualties": "uk_casualties",
    }
    counts = {}
    if _use_bigquery():
        for key, table in raw_tables.items():
            tbl = _bq_table("raw", table)
            try:
                counts[key] = int(_bq_query(f"SELECT COUNT(*) AS n FROM {tbl}")["n"].iloc[0])
            except Exception:
                counts[key] = 0
    else:
        con = _con()
        for key, table in raw_tables.items():
            try:
                counts[key] = int(con.execute(f"SELECT COUNT(*) FROM raw.{table}").fetchone()[0])
            except Exception:
                counts[key] = 0
        con.close()
    return counts


@st.cache_data(ttl=10800, show_spinner=False)
def fetch_osrm_route(
    lon_a: float, lat_a: float,
    lon_b: float, lat_b: float,
) -> list[list[float]] | None:
    """Return road-following [lat, lon] pairs from the OSRM public cycling API.

    Results are cached for 24 h so repeated page renders don't re-fetch.
    Returns None on error (caller should fall back to straight arc).
    """
    url = (
        f"http://router.project-osrm.org/route/v1/cycling/"
        f"{lon_a},{lat_a};{lon_b},{lat_b}"
        f"?overview=full&geometries=geojson"
    )
    try:
        resp = requests.get(url, timeout=8)
        data = resp.json()
        if data.get("code") == "Ok" and data.get("routes"):
            # OSRM returns [lon, lat]; Folium needs [lat, lon]
            return [[c[1], c[0]] for c in data["routes"][0]["geometry"]["coordinates"]]
    except Exception:
        pass
    return None
