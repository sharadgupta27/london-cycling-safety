"""
TFL Santander Cycle Hire – dlt ingestion pipeline
==================================================
Discovers the latest weekly journey CSV files from cycling.data.tfl.gov.uk,
extracts station metadata (name, lon, lat) embedded in the journey rows, and
loads both tables incrementally into DuckDB.

Tables created:
  raw.tfl_journeys   – every journey record
  raw.tfl_stations   – unique docking stations with coordinates

Run:
    python ingestion/ingest_tfl_cycling.py
"""

from __future__ import annotations

import io
import os
import re
import sys
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path
from typing import Iterator

import dlt
import pandas as pd
import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from loguru import logger
from tqdm import tqdm

# ── project root so we can import from sibling modules ─────────────────────
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
load_dotenv(PROJECT_ROOT / ".env")

DUCKDB_PATH = os.getenv("DUCKDB_PATH", "london_cycling.duckdb")
TFL_N_FILES = int(os.getenv("TFL_N_FILES", "12"))

TFL_BASE_URL = "https://cycling.data.tfl.gov.uk/usage-stats/"
FALLBACK_STATION_URL = (
    "https://api.tfl.gov.uk/BikePoint"
)

# ── column renames: TFL CSV headers vary slightly across years ──────────────
COLUMN_MAP = {
    # ── legacy format (pre-2025) ─────────────────────────────────────────────
    "Rental Id": "rental_id",
    "rental_id": "rental_id",
    "Duration": "duration_seconds",
    "duration": "duration_seconds",
    "Bike Id": "bike_id",
    "bike_id": "bike_id",
    "End Date": "end_date",
    "end_date": "end_date",
    "EndStation Id": "end_station_id",
    "end_station_id": "end_station_id",
    "EndStation Name": "end_station_name",
    "end_station_name": "end_station_name",
    "EndStation Longitude": "end_lon",
    "end_station_longitude": "end_lon",
    "EndStation Latitude": "end_lat",
    "end_station_latitude": "end_lat",
    "Start Date": "start_date",
    "start_date": "start_date",
    "StartStation Id": "start_station_id",
    "start_station_id": "start_station_id",
    "StartStation Name": "start_station_name",
    "start_station_name": "start_station_name",
    "StartStation Longitude": "start_lon",
    "start_station_longitude": "start_lon",
    "StartStation Latitude": "start_lat",
    "start_station_latitude": "start_lat",
    "Bike model": "bike_model",
    "bike_model": "bike_model",
    # ── new format (July 2025+) ───────────────────────────────────────────────
    "Number": "rental_id",
    "Start date": "start_date",
    "Start station": "start_station_name",
    "Start station number": "start_station_id",
    "End date": "end_date",
    "End station": "end_station_name",
    "End station number": "end_station_id",
    "Bike number": "bike_id",
    "Total duration": "duration_text",        # human-readable, e.g. "17m 1s" – not used
    "Total duration (ms)": "duration_ms",     # convert to duration_seconds below
}

REQUIRED_COLS = {
    "rental_id", "duration_seconds", "bike_id",
    "start_date", "start_station_id", "start_station_name",
    "end_date", "end_station_id", "end_station_name",
}


# ── helpers ─────────────────────────────────────────────────────────────────

# S3 bucket that backs the TFL cycling data portal
_TFL_S3_URL = "https://s3-eu-west-1.amazonaws.com/cycling.data.tfl.gov.uk/"


def _s3_listing(n: int) -> list[str]:
    """Parse the S3 bucket XML listing to find the most recent N journey CSV URLs."""
    ns = "{http://s3.amazonaws.com/doc/2006-03-01/}"
    params = "?prefix=usage-stats/&max-keys=2000"
    resp = requests.get(_TFL_S3_URL + params, timeout=30)
    resp.raise_for_status()
    root = ET.fromstring(resp.text)
    keys = [el.text for el in root.iter(f"{ns}Key")
            if el.text and re.search(r"JourneyDataExtract.*\.csv$", el.text, re.IGNORECASE)]
    # Sort by the leading numeric file number (not alphabetically, which would
    # put e.g. '99JourneyData' before '451JourneyData')
    def _file_num(key: str) -> int:
        m = re.search(r"/(\d+)JourneyDataExtract", key)
        return int(m.group(1)) if m else 0
    keys_sorted = sorted(keys, key=_file_num, reverse=True)[:n]
    urls = [_TFL_S3_URL + k for k in keys_sorted]
    logger.info("S3 listing: found {} journey files, using latest {}", len(keys), len(urls))
    return urls


def _probe_recent_urls(n: int) -> list[str]:
    """Estimate current TFL file numbers by date arithmetic and verify with HEAD requests.

    TFL releases ~52 files/year starting from file ~1 in mid-2015.
    By March 2026 (~10.7 years × 52 = ~556 files) so we probe 600 → 400.
    """
    # Estimate: 1 file ≈ week 1 of Jul 2015 → file N = (today - ref) / 7
    ref_date = datetime(2015, 7, 6)          # approximate first file date
    weeks_since = (datetime.now() - ref_date).days // 7
    high_guess = weeks_since + 10            # add buffer
    low_guess  = max(high_guess - 160, 1)    # look back ~3 years

    found: list[str] = []
    logger.info("Probing TFL file numbers {} → {} (HEAD requests)", high_guess, low_guess)
    for num in range(high_guess, low_guess, -1):
        if len(found) >= n:
            break
        # Try the S3 prefix listing for this specific number
        prefix_url = (
            f"{_TFL_S3_URL}?prefix=usage-stats/{num}JourneyDataExtract&max-keys=5"
        )
        try:
            ns = "{http://s3.amazonaws.com/doc/2006-03-01/}"
            r = requests.get(prefix_url, timeout=8)
            if r.status_code == 200:
                root = ET.fromstring(r.text)
                keys = [el.text for el in root.iter(f"{ns}Key")
                        if el.text and el.text.endswith(".csv")]
                if keys:
                    found.append(_TFL_S3_URL + keys[0])
                    logger.debug("  Found #{}: {}", num, keys[0])
        except Exception:
            continue
    return found


def discover_tfl_csv_urls(n: int = TFL_N_FILES) -> list[str]:
    """Discover the N most-recent TFL journey CSV URLs.

    Strategy (tried in order):
      1. S3 bucket XML listing  – fastest, most reliable
      2. S3 per-number probing  – slower but works if listing is paginated oddly
      3. HTML scrape of TFL base URL
    """
    logger.info("Discovering TFL journey CSV URLs (want {})", n)

    # 1. S3 full listing
    try:
        urls = _s3_listing(n)
        if urls:
            return urls
    except Exception as exc:
        logger.warning("S3 listing failed: {}", exc)

    # 2. Per-number probing via S3 prefix
    try:
        urls = _probe_recent_urls(n)
        if urls:
            logger.info("Probing found {} URLs", len(urls))
            return urls
    except Exception as exc:
        logger.warning("S3 probing failed: {}", exc)

    # 3. TFL HTML scrape (original approach)
    try:
        resp = requests.get(TFL_BASE_URL, timeout=30)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        links = [
            a["href"] for a in soup.find_all("a", href=True)
            if re.search(r"JourneyDataExtract.*\.csv$", a["href"], re.IGNORECASE)
        ]
        urls = [
            u if u.startswith("http") else TFL_BASE_URL + u.lstrip("/")
            for u in links
        ]
        urls = sorted(urls, reverse=True)[:n]
        if urls:
            logger.info("TFL HTML scrape found {} files", len(urls))
            return urls
    except Exception as exc:
        logger.warning("TFL HTML scrape failed: {}", exc)

    logger.error(
        "All TFL URL discovery methods failed. "
        "Check https://cycling.data.tfl.gov.uk/ manually and update FALLBACK_URLS."
    )
    return []


def _normalise_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Rename columns to snake_case standard names."""
    df = df.rename(columns={c: COLUMN_MAP.get(c, c.lower().replace(" ", "_")) for c in df.columns})
    return df


def _download_csv(url: str) -> pd.DataFrame | None:
    """Download a TFL journey CSV and return as a DataFrame."""
    try:
        resp = requests.get(url, timeout=120)
        resp.raise_for_status()
        df = pd.read_csv(io.BytesIO(resp.content), encoding="utf-8", low_memory=False)
        df = _normalise_columns(df)
        # ── new format convenience: derive duration_seconds from duration_ms ──
        if "duration_ms" in df.columns and "duration_seconds" not in df.columns:
            df["duration_seconds"] = pd.to_numeric(df["duration_ms"], errors="coerce") / 1000
        missing = REQUIRED_COLS - set(df.columns)
        if missing:
            logger.warning("Skipping {} – missing columns: {}", url.split("/")[-1], missing)
            return None
        # Parse datetimes
        for col in ("start_date", "end_date"):
            if col in df.columns:
                df[col] = pd.to_datetime(df[col], format="%Y-%m-%d %H:%M", errors="coerce")
        # Coerce numeric columns
        for col in ("start_lon", "start_lat", "end_lon", "end_lat", "duration_seconds"):
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce")
        # Filter to London bounding box (roughly) – only when coordinates are present
        if "start_lat" in df.columns and "start_lon" in df.columns:
            df = df[
                df["start_lat"].between(51.28, 51.70) &
                df["start_lon"].between(-0.55, 0.30)
            ]
        df["source_file"] = url.split("/")[-1]
        return df
    except Exception as exc:
        logger.error("Failed to download {}: {}", url, exc)
        return None


def _fetch_stations_from_bikepoint() -> pd.DataFrame:
    """Fetch all TFL Santander docking stations from the TFL BikePoint API.

    Falls back to an empty DataFrame if the API is unavailable.
    The API returns a JSON array; each element has:
      id       – e.g. "BikePoints_1"
      commonName – full station name
      lat / lon  – coordinates
    """
    logger.info("Fetching station list from TFL BikePoint API: {}", FALLBACK_STATION_URL)
    try:
        resp = requests.get(FALLBACK_STATION_URL, timeout=60)
        resp.raise_for_status()
        data = resp.json()
        records = []
        for item in data:
            raw_id = item.get("id", "")          # "BikePoints_1"
            num_match = re.search(r"(\d+)$", raw_id)
            if not num_match:
                continue
            records.append({
                "station_id": int(num_match.group(1)),
                "station_name": item.get("commonName", "").strip(),
                "longitude": float(item.get("lon", 0)),
                "latitude": float(item.get("lat", 0)),
            })
        df = pd.DataFrame(records)
        logger.info("BikePoint API returned {} stations", len(df))
        return df
    except Exception as exc:
        logger.warning("BikePoint API unavailable ({}); stations table will be empty", exc)
        return pd.DataFrame(columns=["station_id", "station_name", "longitude", "latitude"])


def _extract_stations(df: pd.DataFrame) -> pd.DataFrame:
    """Derive unique station records from the journey rows.

    Older TFL files (pre-2022) don't include longitude/latitude columns.
    Those files are skipped; we still get coordinates from any newer files.
    """
    has_coords = all(
        c in df.columns
        for c in ("start_lon", "start_lat", "end_lon", "end_lat")
    )
    if not has_coords:
        return pd.DataFrame(columns=["station_id", "station_name", "longitude", "latitude"])

    starts = df[["start_station_id", "start_station_name", "start_lon", "start_lat"]].rename(
        columns={"start_station_id": "station_id", "start_station_name": "station_name",
                 "start_lon": "longitude", "start_lat": "latitude"}
    )
    ends = df[["end_station_id", "end_station_name", "end_lon", "end_lat"]].rename(
        columns={"end_station_id": "station_id", "end_station_name": "station_name",
                 "end_lon": "longitude", "end_lat": "latitude"}
    )
    stations = (
        pd.concat([starts, ends])
        .dropna(subset=["station_id", "longitude", "latitude"])
        .drop_duplicates("station_id")
        .reset_index(drop=True)
    )
    stations["station_id"] = pd.to_numeric(stations["station_id"], errors="coerce")
    return stations


# ── dlt sources ─────────────────────────────────────────────────────────────

@dlt.source(name="tfl_cycling")
def tfl_cycling_source(n_files: int = TFL_N_FILES):
    urls = discover_tfl_csv_urls(n_files)
    yield tfl_journeys_resource(urls)
    yield tfl_stations_resource(urls)


@dlt.resource(name="tfl_journeys", write_disposition="replace", primary_key="rental_id")
def tfl_journeys_resource(urls: list[str]) -> Iterator[dict]:
    for url in tqdm(urls, desc="Ingesting TFL journey files"):
        df = _download_csv(url)
        if df is None:
            continue
        logger.info("  → {} rows from {}", len(df), url.split("/")[-1])
        for row in df.to_dict(orient="records"):
            yield row


@dlt.resource(name="tfl_stations", write_disposition="replace")
def tfl_stations_resource(urls: list[str]) -> Iterator[dict]:
    all_stations: list[pd.DataFrame] = []
    for url in tqdm(urls, desc="Extracting station coordinates"):
        df = _download_csv(url)
        if df is None:
            continue
        all_stations.append(_extract_stations(df))
    if all_stations:
        combined = (
            pd.concat(all_stations)
            .dropna(subset=["station_id", "longitude", "latitude"])
            .drop_duplicates("station_id")
            .reset_index(drop=True)
        )
        combined = combined[
            combined["longitude"].between(-0.55, 0.30) &
            combined["latitude"].between(51.28, 51.70)
        ]
        logger.info("Extracted {} unique bike stations from journey files", len(combined))
    else:
        combined = pd.DataFrame()

    # New TFL format (2025+) no longer embeds coordinates in journey CSVs.
    # Fall back to the TFL BikePoint REST API for station locations.
    if combined.empty:
        logger.info("No coordinates in journey files – falling back to TFL BikePoint API")
        combined = _fetch_stations_from_bikepoint()

    for row in combined.to_dict(orient="records"):
        yield row


# ── entrypoint ───────────────────────────────────────────────────────────────

def _build_destination():
    """Return the appropriate dlt destination based on the DESTINATION env var.

    - ``DESTINATION=bigquery``  → Google BigQuery.
      Reads DESTINATION__BIGQUERY__PROJECT_ID, DESTINATION__BIGQUERY__DATASET_NAME,
      DESTINATION__BIGQUERY__LOCATION and GOOGLE_APPLICATION_CREDENTIALS from env.
    - (default)                → local DuckDB.
    """
    dest = os.getenv("DESTINATION", "duckdb").lower()
    if dest == "bigquery":
        logger.info("Destination: BigQuery (project={})",
                    os.getenv("DESTINATION__BIGQUERY__PROJECT_ID", "?"))
        return dlt.destinations.bigquery()
    logger.info("Destination: DuckDB ({})", DUCKDB_PATH)
    return dlt.destinations.duckdb(DUCKDB_PATH)


def run(n_files: int = TFL_N_FILES, db_path: str = DUCKDB_PATH) -> None:
    logger.info("=== TFL Santander Cycling Ingestion ===")
    logger.info("Target DuckDB: {}  |  Files to ingest: {}", db_path, n_files)

    pipeline = dlt.pipeline(
        pipeline_name="tfl_cycling",
        destination=_build_destination(),
        dataset_name="raw",
    )
    load_info = pipeline.run(tfl_cycling_source(n_files=n_files))
    logger.info("Load complete: {}", load_info)


if __name__ == "__main__":
    run()
