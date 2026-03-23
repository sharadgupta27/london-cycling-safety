"""
DuckDB Spatial Transforms
==========================
Uses DuckDB's native `spatial` extension to:
  1. Install & load the spatial extension
  2. Build a geo-enriched accidents table with GEOMETRY points
  3. Build a geo-enriched stations table with GEOMETRY points
  4. Compute the accident density (# accidents within radius) for every station
  5. Build corridor segments between common start→end station pairs
  6. Score corridors by accident count along their bounding box

All results are written into the `spatial` schema in DuckDB.

Run:
    python transforms/spatial_transforms.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import duckdb
from dotenv import load_dotenv
from loguru import logger

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
load_dotenv(PROJECT_ROOT / ".env")

DUCKDB_PATH = os.getenv("DUCKDB_PATH", "london_cycling.duckdb")
BLACKSPOT_RADIUS_M = float(os.getenv("BLACKSPOT_RADIUS_M", "500"))


def get_connection(db_path: str = DUCKDB_PATH) -> duckdb.DuckDBPyConnection:
    con = duckdb.connect(db_path)
    con.execute("INSTALL spatial; LOAD spatial;")
    logger.info("DuckDB spatial extension loaded")
    return con


def create_spatial_schema(con: duckdb.DuckDBPyConnection) -> None:
    con.execute("CREATE SCHEMA IF NOT EXISTS spatial_layer;")
    logger.info("Schema spatial_layer created")


# ── 1. Spatialise accidents ─────────────────────────────────────────────────

ACCIDENTS_GEO_SQL = """
CREATE OR REPLACE TABLE spatial_layer.accidents_geo AS
SELECT
    -- DfT renamed accident_index -> collision_index in 2024 collision dataset;
    -- alias back to the old name so all downstream SQL is unchanged.
    a.collision_index                                   AS accident_index,
    a.date,
    COALESCE(CAST(a.collision_year AS INTEGER), a.year) AS year,
    a.hour_of_day,
    a.day_of_week,
    CAST(a.collision_severity AS INTEGER)               AS accident_severity,
    CASE CAST(a.collision_severity AS INTEGER)
        WHEN 1 THEN 'Fatal'
        WHEN 2 THEN 'Serious'
        ELSE 'Slight'
    END                                                 AS severity_label,
    a.number_of_casualties,
    a.number_of_vehicles,
    a.road_type,
    a.speed_limit,
    a.light_conditions,
    a.weather_conditions,
    TRY_CAST(a.longitude AS DOUBLE)                     AS longitude,
    TRY_CAST(a.latitude  AS DOUBLE)                     AS latitude,
    ST_Point(
        TRY_CAST(a.longitude AS DOUBLE),
        TRY_CAST(a.latitude  AS DOUBLE)
    )::GEOMETRY                                         AS geom
FROM raw.uk_accidents AS a
WHERE a.longitude IS NOT NULL
  AND a.latitude  IS NOT NULL
  AND TRY_CAST(a.longitude AS DOUBLE) BETWEEN -0.55 AND 0.30
  AND TRY_CAST(a.latitude  AS DOUBLE) BETWEEN 51.28 AND 51.70;
"""

# ── 2. Spatialise stations ─────────────────────────────────────────────────

STATIONS_GEO_SQL = """
CREATE OR REPLACE TABLE spatial_layer.stations_geo AS
SELECT
    station_id,
    station_name,
    longitude,
    latitude,
    ST_Point(longitude, latitude)::GEOMETRY AS geom
FROM raw.tfl_stations
WHERE longitude IS NOT NULL
  AND latitude  IS NOT NULL;
"""

# ── 3. Station accident proximity ──────────────────────────────────────────
# Count accidents within BLACKSPOT_RADIUS_M of each station.
# ST_Distance on WGS84 GEOMETRY returns degrees; we convert to metres using
# the approximation 1° ≈ 111_320 m at London's latitude.

STATION_PROXIMITY_SQL = """
CREATE OR REPLACE TABLE spatial_layer.station_blackspot_scores AS
SELECT
    s.station_id,
    s.station_name,
    s.longitude,
    s.latitude,
    COUNT(a.accident_index)                                 AS accident_count,
    SUM(a.number_of_casualties)                             AS total_casualties,
    SUM(CASE WHEN a.accident_severity = 1 THEN 1 ELSE 0 END) AS fatal_count,
    SUM(CASE WHEN a.accident_severity = 2 THEN 1 ELSE 0 END) AS serious_count,
    SUM(CASE WHEN a.accident_severity = 3 THEN 1 ELSE 0 END) AS slight_count,
    -- weighted risk score: fatal=10, serious=3, slight=1
    SUM(
        CASE a.accident_severity
            WHEN 1 THEN 10
            WHEN 2 THEN 3
            ELSE 1
        END
    )                                                       AS weighted_risk_score,
    {radius_m}                                              AS search_radius_m
FROM spatial_layer.stations_geo  AS s
LEFT JOIN spatial_layer.accidents_geo AS a
    ON ST_Distance(s.geom, a.geom) * 111320 <= {radius_m}
GROUP BY s.station_id, s.station_name, s.longitude, s.latitude;
""".format(radius_m=BLACKSPOT_RADIUS_M)

# ── 4. Corridor risk ───────────────────────────────────────────────────────
# Identify the top-N most-travelled corridors from journey data,
# then score them by accidents inside the corridor's bounding box.

CORRIDOR_JOURNEYS_SQL = """
CREATE OR REPLACE TABLE spatial_layer.corridor_journeys AS
SELECT
    LEAST(start_station_id, end_station_id)   AS station_a_id,
    GREATEST(start_station_id, end_station_id) AS station_b_id,
    COUNT(*)                                   AS journey_count
FROM raw.tfl_journeys
WHERE start_station_id IS NOT NULL
  AND end_station_id   IS NOT NULL
  AND start_station_id <> end_station_id
GROUP BY 1, 2
HAVING COUNT(*) >= 10
ORDER BY journey_count DESC;
"""

CORRIDOR_RISK_SQL = """
CREATE OR REPLACE TABLE spatial_layer.corridor_risk AS
WITH corridor_coords AS (
    SELECT
        cj.station_a_id,
        cj.station_b_id,
        cj.journey_count,
        sa.station_name  AS station_a_name,
        sb.station_name  AS station_b_name,
        sa.longitude     AS lon_a,
        sa.latitude      AS lat_a,
        sb.longitude     AS lon_b,
        sb.latitude      AS lat_b,
        -- corridor midpoint
        (sa.longitude + sb.longitude) / 2.0 AS mid_lon,
        (sa.latitude  + sb.latitude)  / 2.0 AS mid_lat,
        -- corridor length in metres (haversine approximated)
        SQRT(
          POWER((sb.longitude - sa.longitude) * 111320 * COS(RADIANS(sa.latitude)), 2) +
          POWER((sb.latitude  - sa.latitude)  * 111320, 2)
        )                                    AS length_m
    FROM spatial_layer.corridor_journeys cj
    JOIN spatial_layer.stations_geo sa ON sa.station_id = cj.station_a_id
    JOIN spatial_layer.stations_geo sb ON sb.station_id = cj.station_b_id
),
corridor_accidents AS (
    SELECT
        cc.station_a_id,
        cc.station_b_id,
        COUNT(a.accident_index)  AS corridor_accident_count,
        SUM(
            CASE a.accident_severity
                WHEN 1 THEN 10
                WHEN 2 THEN 3
                ELSE 1
            END
        )                        AS corridor_risk_raw
    FROM corridor_coords cc
    JOIN spatial_layer.accidents_geo a
        ON  a.longitude BETWEEN LEAST(cc.lon_a, cc.lon_b) - 0.002
                            AND GREATEST(cc.lon_a, cc.lon_b) + 0.002
        AND a.latitude  BETWEEN LEAST(cc.lat_a, cc.lat_b) - 0.002
                            AND GREATEST(cc.lat_a, cc.lat_b) + 0.002
    GROUP BY cc.station_a_id, cc.station_b_id
)
SELECT
    cc.*,
    COALESCE(ca.corridor_accident_count, 0) AS corridor_accident_count,
    COALESCE(ca.corridor_risk_raw, 0)       AS corridor_risk_raw,
    -- normalise: accidents per km of corridor
    CASE WHEN cc.length_m > 0
         THEN COALESCE(ca.corridor_risk_raw, 0) / (cc.length_m / 1000.0)
         ELSE 0
    END                                     AS risk_per_km,
    -- composite score weighting risk and journey volume
    (COALESCE(ca.corridor_risk_raw, 0) * LOG(cc.journey_count + 1))
                                            AS composite_risk_score
FROM corridor_coords cc
LEFT JOIN corridor_accidents ca
       ON ca.station_a_id = cc.station_a_id
      AND ca.station_b_id = cc.station_b_id
ORDER BY composite_risk_score DESC;
"""

# ── 5. Monthly trend ─────────────────────────────────────────────────────

MONTHLY_TREND_SQL = """
CREATE OR REPLACE TABLE spatial_layer.monthly_accident_trend AS
SELECT
    year,
    EXTRACT(MONTH FROM date)::INT AS month,
    STRFTIME(date, '%Y-%m')       AS year_month,
    COUNT(*)                      AS accident_count,
    SUM(number_of_casualties)     AS casualty_count,
    AVG(number_of_casualties)     AS avg_casualties_per_accident
FROM spatial_layer.accidents_geo
WHERE date IS NOT NULL
GROUP BY year, month, year_month
ORDER BY year, month;
"""


# ── orchestrate all transforms ────────────────────────────────────────────

TRANSFORMS: list[tuple[str, str]] = [
    ("accidents_geo", ACCIDENTS_GEO_SQL),
    ("stations_geo", STATIONS_GEO_SQL),
    ("station_blackspot_scores", STATION_PROXIMITY_SQL),
    ("corridor_journeys", CORRIDOR_JOURNEYS_SQL),
    ("corridor_risk", CORRIDOR_RISK_SQL),
    ("monthly_accident_trend", MONTHLY_TREND_SQL),
]


# Tables that MUST exist in raw.* before we can proceed
_REQUIRED_RAW_TABLES = ["uk_accidents", "tfl_journeys", "tfl_stations"]


def _check_required_tables(con: duckdb.DuckDBPyConnection) -> list[str]:
    """Return a list of missing required raw tables."""
    missing = []
    for tbl in _REQUIRED_RAW_TABLES:
        try:
            con.execute(f"SELECT 1 FROM raw.{tbl} LIMIT 1")
        except Exception:
            missing.append(tbl)
    return missing


def run(db_path: str = DUCKDB_PATH) -> None:
    logger.info("=== DuckDB Spatial Transforms ===")
    con = get_connection(db_path)
    create_spatial_schema(con)

    # Pre-flight: fail fast if upstream ingestion tables don't exist
    missing = _check_required_tables(con)
    if missing:
        con.close()
        raise RuntimeError(
            f"Required raw tables not found: {missing}. "
            "Run the ingestion steps first (ingest_tfl_cycling.py, ingest_uk_accidents.py)."
        )

    failed: list[str] = []
    for name, sql in TRANSFORMS:
        logger.info("Running transform: {}", name)
        try:
            con.execute(sql)
            count = con.execute(f"SELECT COUNT(*) FROM spatial_layer.{name}").fetchone()[0]
            logger.info("  ✓ spatial_layer.{} – {:,} rows", name, count)
        except Exception as exc:
            logger.error("  ✗ {} failed: {}", name, exc)
            failed.append(name)

    con.close()
    if failed:
        raise RuntimeError(f"Spatial transforms failed for: {failed}")
    logger.info("All spatial transforms complete.")


if __name__ == "__main__":
    run()
