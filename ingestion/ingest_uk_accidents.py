"""
UK Road Safety / STATS19 – dlt ingestion pipeline
===================================================
Downloads DfT (Department for Transport) road accident, casualty, and vehicle
CSV files and loads them into DuckDB (raw schema).

Tables created:
  raw.uk_accidents   – accident records with lat/lon, severity, date/time
  raw.uk_casualties  – casualty records linked to accidents
  raw.uk_vehicles    – vehicle records linked to accidents

Data source:
  https://data.dft.gov.uk/road-accidents-safety-data/

Run:
    python ingestion/ingest_uk_accidents.py
"""

from __future__ import annotations

import io
import json
import os
import sys
from pathlib import Path
from typing import Iterator

import dlt
import pandas as pd
import requests
from dotenv import load_dotenv
from loguru import logger
from tqdm import tqdm

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
load_dotenv(PROJECT_ROOT / ".env")

DUCKDB_PATH = os.getenv("DUCKDB_PATH", "london_cycling.duckdb")
ACCIDENT_YEARS_RAW = os.getenv("ACCIDENT_YEARS", "2022,2023,2024")
ACCIDENT_YEARS = [y.strip() for y in ACCIDENT_YEARS_RAW.split(",")]

# DfT STATS19 file URLs (updated annually)
# "last-5-years" bundles are the most convenient.
# NOTE: DfT renamed "accident" → "collision" in 2024.
# We try the collision name first, fall back to the legacy accident name.
STATS19_URLS = {
    "accidents": [
        (
            "https://data.dft.gov.uk/road-accidents-safety-data/"
            "dft-road-casualty-statistics-collision-last-5-years.csv"
        ),
        (
            "https://data.dft.gov.uk/road-accidents-safety-data/"
            "dft-road-casualty-statistics-accident-last-5-years.csv"
        ),
    ],
    "casualties": [
        (
            "https://data.dft.gov.uk/road-accidents-safety-data/"
            "dft-road-casualty-statistics-casualty-last-5-years.csv"
        ),
    ],
    "vehicles": [
        (
            "https://data.dft.gov.uk/road-accidents-safety-data/"
            "dft-road-casualty-statistics-vehicle-last-5-years.csv"
        ),
    ],
}

# London bounding box (WGS84)
LON_MIN, LON_MAX = -0.55, 0.30
LAT_MIN, LAT_MAX = 51.28, 51.70


# ── helpers ─────────────────────────────────────────────────────────────────

def _download_stats19(url_or_urls: "str | list[str]", table: str) -> "pd.DataFrame | None":
    """Download a STATS19 CSV from DfT, filter to London, and clean up columns.

    ``url_or_urls`` can be a single URL string **or** a list of candidate URLs
    to try in order (useful when DfT renames files between years).
    """
    urls = [url_or_urls] if isinstance(url_or_urls, str) else url_or_urls
    for url in urls:
        logger.info("Downloading STATS19 {} from {}", table, url)
        try:
            resp = requests.get(url, timeout=300, stream=True)
            resp.raise_for_status()
        except Exception as exc:
            logger.error("Failed to download {}: {}", url, exc)
            continue  # try next candidate URL

        try:
            content = b""
            total = int(resp.headers.get("content-length", 0))
            with tqdm(total=total, unit="B", unit_scale=True, desc=f"  {table}") as bar:
                for chunk in resp.iter_content(chunk_size=65536):
                    content += chunk
                    bar.update(len(chunk))
            df = pd.read_csv(io.BytesIO(content), low_memory=False)
            df.columns = [c.strip().lower().replace(" ", "_") for c in df.columns]
            # DfT has renamed columns across years:
            #   accident_index → accident_reference (intermediate)
            #   accident_index → collision_index (2024 collision dataset)
            # We keep whichever name is present; stg_accidents.sql references collision_index.
            # For backwards compat, rename accident_reference → collision_index if needed.
            if "accident_reference" in df.columns and "collision_index" not in df.columns:
                df = df.rename(columns={"accident_reference": "collision_index"})
            if "accident_index" in df.columns and "collision_index" not in df.columns:
                df = df.rename(columns={"accident_index": "collision_index"})
            if "accident_severity" in df.columns and "collision_severity" not in df.columns:
                df = df.rename(columns={"accident_severity": "collision_severity"})
            if "accident_year" in df.columns and "collision_year" not in df.columns:
                df = df.rename(columns={"accident_year": "collision_year"})
            logger.info("  Raw rows: {:,}", len(df))
            return df
        except Exception as exc:
            logger.error("Failed to parse {}: {}", url, exc)
            continue

    logger.error("All candidate URLs failed for table: {}", table)
    return None


def _filter_london_accidents(df: pd.DataFrame) -> pd.DataFrame:
    """Keep only London accidents (bounding box + local_authority_district 0–9 prefix)."""
    if "longitude" in df.columns and "latitude" in df.columns:
        df["longitude"] = pd.to_numeric(df["longitude"], errors="coerce")
        df["latitude"] = pd.to_numeric(df["latitude"], errors="coerce")
        mask = (
            df["longitude"].between(LON_MIN, LON_MAX) &
            df["latitude"].between(LAT_MIN, LAT_MAX)
        )
        df = df[mask].copy()
    logger.info("  London rows: {:,}", len(df))
    return df


def _parse_accident_dates(df: pd.DataFrame) -> pd.DataFrame:
    if "date" in df.columns:
        df["date"] = pd.to_datetime(df["date"], format="mixed", dayfirst=True, errors="coerce")
    if "year" not in df.columns and "date" in df.columns:
        df["year"] = df["date"].dt.year
    return df


def _filter_years(df: pd.DataFrame, years: list[str]) -> pd.DataFrame:
    if not years:
        return df
    year_col = next(
        (c for c in ("year", "collision_year", "accident_year") if c in df.columns),
        None,
    )
    if year_col is None:
        logger.warning("No year column found in data; skipping year filter (all rows kept)")
        return df
    int_years = [int(y) for y in years if y.isdigit()]
    filtered = df[df[year_col].isin(int_years)].copy()
    logger.info("  Year filter (col={}, years={}): {:,} → {:,} rows", year_col, int_years, len(df), len(filtered))
    return filtered


# ── dlt sources ─────────────────────────────────────────────────────────────

@dlt.source(name="uk_road_safety")
def uk_road_safety_source(years_csv: str = None):
    """years_csv: comma-separated year string, e.g. '2022,2023,2024'.
    Uses ACCIDENT_YEARS env variable when not supplied.
    A str default is used instead of list to satisfy dlt/pydantic mutable-default rule.
    """
    _years = [y.strip() for y in (years_csv or ACCIDENT_YEARS_RAW).split(",")]
    yield uk_accidents_resource(_years)
    yield uk_casualties_resource(_years)
    yield uk_vehicles_resource(_years)


@dlt.resource(
    name="uk_accidents",
    write_disposition="replace",
    primary_key="collision_index",
)
def uk_accidents_resource(years: list[str]) -> Iterator[dict]:
    df = _download_stats19(STATS19_URLS["accidents"], "accidents")
    if df is None:
        return
    df = _parse_accident_dates(df)
    df = _filter_years(df, years)
    df = _filter_london_accidents(df)

    # Enrich: hour_of_day from time column
    if "time" in df.columns:
        df["hour_of_day"] = pd.to_datetime(df["time"], format="%H:%M", errors="coerce").dt.hour

    logger.info("Yielding {:,} London accident rows", len(df))
    for row in df.to_dict(orient="records"):
        yield row


@dlt.resource(
    name="uk_casualties",
    write_disposition="replace",
    primary_key=["collision_index", "vehicle_reference", "casualty_reference"],
)
def uk_casualties_resource(years: list[str]) -> Iterator[dict]:
    df = _download_stats19(STATS19_URLS["casualties"], "casualties")
    if df is None:
        return
    year_col = next((c for c in ("collision_year", "accident_year") if c in df.columns), None)
    if year_col:
        int_years = [int(y) for y in years if y.isdigit()]
        df = df[df[year_col].isin(int_years)].copy()
    # We can't filter casualty rows by lat/lon – we'll join to accidents later
    logger.info("Yielding {:,} casualty rows", len(df))
    for row in df.to_dict(orient="records"):
        yield row


@dlt.resource(
    name="uk_vehicles",
    write_disposition="replace",
    primary_key=["collision_index", "vehicle_reference"],
)
def uk_vehicles_resource(years: list[str]) -> Iterator[dict]:
    df = _download_stats19(STATS19_URLS["vehicles"], "vehicles")
    if df is None:
        return
    year_col = next((c for c in ("collision_year", "accident_year") if c in df.columns), None)
    if year_col:
        int_years = [int(y) for y in years if y.isdigit()]
        df = df[df[year_col].isin(int_years)].copy()
    logger.info("Yielding {:,} vehicle rows", len(df))
    for row in df.to_dict(orient="records"):
        yield row


# ── entrypoint ───────────────────────────────────────────────────────────────

def _purge_stale_schema(pipeline_name: str = "uk_road_safety") -> None:
    """Delete the local dlt schema file so it is regenerated from current data.

    All uk_road_safety resources use write_disposition='replace', so the schema
    is always reconstructed from scratch on each run.  Keeping an old schema
    causes UnboundColumnException when column names change (e.g. accident_index
    was renamed to collision_index across DfT STATS19 releases).
    """
    schema_file = (
        Path.home() / ".dlt" / "pipelines" / pipeline_name
        / "schemas" / f"{pipeline_name}.schema.json"
    )
    if schema_file.exists():
        # Only wipe if any table has a non-nullable column that looks stale
        # (i.e. not matching any current primary-key definition).
        try:
            schema = json.loads(schema_file.read_text())
            current_pks = {
                "uk_casualties": {"collision_index", "vehicle_reference", "casualty_reference"},
                "uk_vehicles": {"collision_index", "vehicle_reference"},
                "uk_accidents": {"collision_index"},
            }
            stale = False
            for tbl, pks in current_pks.items():
                cols = schema.get("tables", {}).get(tbl, {}).get("columns", {})
                for cname, cdef in cols.items():
                    if not cdef.get("nullable", True) and cname not in pks:
                        logger.warning(
                            "Stale non-nullable column '{}' in table '{}'; "
                            "resetting local schema.", cname, tbl
                        )
                        stale = True
                        break
                if stale:
                    break
            if stale:
                schema_file.unlink()
                logger.info("Local schema file removed – will regenerate on this run.")
        except Exception as exc:  # pragma: no cover
            logger.warning("Could not inspect local schema ({}); removing it.", exc)
            schema_file.unlink(missing_ok=True)


def run(years: list[str] = None, db_path: str = DUCKDB_PATH) -> None:
    _years = years or ACCIDENT_YEARS
    years_csv = ",".join(str(y) for y in _years)
    logger.info("=== UK Road Safety Ingestion ===")
    logger.info("Target: {}  |  Years: {}", os.getenv("DESTINATION", "duckdb"), _years)

    _purge_stale_schema()

    dest = os.getenv("DESTINATION", "duckdb").lower()
    if dest == "bigquery":
        logger.info("Destination: BigQuery (project={})",
                    os.getenv("DESTINATION__BIGQUERY__PROJECT_ID", "?"))
        destination = dlt.destinations.bigquery()
    else:
        logger.info("Destination: DuckDB ({})", db_path)
        destination = dlt.destinations.duckdb(db_path)

    pipeline = dlt.pipeline(
        pipeline_name="uk_road_safety",
        destination=destination,
        dataset_name="raw",
    )
    load_info = pipeline.run(uk_road_safety_source(years_csv=years_csv))
    logger.info("Load complete: {}", load_info)


if __name__ == "__main__":
    run()
