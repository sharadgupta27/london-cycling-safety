"""
conftest.py – shared pytest fixtures for the London Cycling Safety test suite.
"""

from __future__ import annotations

import io
import os
import textwrap
from pathlib import Path
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

# ── Make the project root importable without installing the package ──────────
PROJECT_ROOT = Path(__file__).resolve().parent.parent
import sys
sys.path.insert(0, str(PROJECT_ROOT))


# ─────────────────────────────────────────────────────────────────────────────
# Minimal sample data fixtures
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture()
def sample_journey_df() -> pd.DataFrame:
    """A minimal DataFrame that resembles a TFL journey CSV after column rename."""
    return pd.DataFrame({
        "rental_id":          [1001, 1002, 1003],
        "duration_seconds":   [600,  1200, 300],
        "bike_id":            [101,  102,  103],
        "start_date":         pd.to_datetime(["2023-06-01 08:00", "2023-06-01 09:00", "2023-06-01 10:00"]),
        "start_station_id":   [1, 2, 3],
        "start_station_name": ["Waterloo", "London Bridge", "Victoria"],
        "start_lon":          [-0.1149, -0.0875, -0.1447],
        "start_lat":          [51.5036, 51.5055, 51.4952],
        "end_date":           pd.to_datetime(["2023-06-01 08:10", "2023-06-01 09:20", "2023-06-01 10:05"]),
        "end_station_id":     [2, 3, 1],
        "end_station_name":   ["London Bridge", "Victoria", "Waterloo"],
        "end_lon":            [-0.0875, -0.1447, -0.1149],
        "end_lat":            [51.5055, 51.4952, 51.5036],
        "source_file":        ["testfile.csv", "testfile.csv", "testfile.csv"],
    })


@pytest.fixture()
def sample_journey_df_no_coords() -> pd.DataFrame:
    """Journey DataFrame that lacks longitude/latitude (pre-2022 TFL format)."""
    return pd.DataFrame({
        "rental_id":          [2001, 2002],
        "duration_seconds":   [400,  800],
        "bike_id":            [201,  202],
        "start_date":         pd.to_datetime(["2017-12-01 08:00", "2017-12-01 09:00"]),
        "start_station_id":   [10, 20],
        "start_station_name": ["Alpha", "Beta"],
        "end_date":           pd.to_datetime(["2017-12-01 08:07", "2017-12-01 09:15"]),
        "end_station_id":     [20, 10],
        "end_station_name":   ["Beta", "Alpha"],
        "source_file":        ["old.csv", "old.csv"],
    })


@pytest.fixture()
def sample_accidents_df() -> pd.DataFrame:
    """Minimal accident DataFrame resembling cleaned STATS19."""
    return pd.DataFrame({
        "accident_index":     ["2022ABC001", "2022ABC002", "2021XYZ003"],
        "longitude":          [-0.12, -0.09, 0.50],    # third row outside London
        "latitude":           [51.50, 51.51, 52.00],
        "accident_severity":  [1, 3, 2],
        "date":               ["01/06/2022", "15/07/2022", "20/08/2021"],
        "time":               ["08:30", "17:45", "12:00"],
        "number_of_casualties": [1, 1, 2],
        "year":               [2022, 2022, 2021],
    })


@pytest.fixture()
def sample_accidents_df_renamed() -> pd.DataFrame:
    """Accident DataFrame with the 2024 DfT column rename (accident_reference)."""
    return pd.DataFrame({
        "accident_reference": ["2024COL001", "2024COL002"],
        "longitude":          [-0.12, -0.09],
        "latitude":           [51.50, 51.51],
        "accident_severity":  [2, 3],
        "date":               ["01/01/2024", "15/02/2024"],
        "number_of_casualties": [1, 1],
    })


# ─────────────────────────────────────────────────────────────────────────────
# DuckDB in-memory connection fixture
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture()
def duck_con():
    """In-memory DuckDB connection; torn down after each test."""
    import duckdb
    con = duckdb.connect(":memory:")
    yield con
    con.close()


@pytest.fixture()
def duck_con_with_raw(duck_con):
    """In-memory DuckDB with a minimal raw schema matching expected tables."""
    duck_con.execute("CREATE SCHEMA IF NOT EXISTS raw;")
    duck_con.execute("""
        CREATE TABLE raw.tfl_stations (
            station_id   INTEGER,
            station_name VARCHAR,
            longitude    DOUBLE,
            latitude     DOUBLE
        );
    """)
    duck_con.execute("""
        INSERT INTO raw.tfl_stations VALUES
            (1, 'Waterloo',      -0.1149, 51.5036),
            (2, 'London Bridge', -0.0875, 51.5055),
            (3, 'Victoria',      -0.1447, 51.4952);
    """)
    duck_con.execute("""
        CREATE TABLE raw.tfl_journeys (
            rental_id         INTEGER,
            start_station_id  INTEGER,
            end_station_id    INTEGER,
            duration_seconds  INTEGER,
            start_date        TIMESTAMP,
            end_date          TIMESTAMP
        );
    """)
    duck_con.execute("""
        INSERT INTO raw.tfl_journeys VALUES
            (1, 1, 2, 600,  '2023-06-01 08:00', '2023-06-01 08:10'),
            (2, 2, 3, 1200, '2023-06-01 09:00', '2023-06-01 09:20'),
            (3, 1, 2, 300,  '2023-06-01 10:00', '2023-06-01 10:05'),
            (4, 1, 2, 450,  '2023-06-01 11:00', '2023-06-01 11:08'),
            (5, 2, 3, 700,  '2023-06-01 12:00', '2023-06-01 12:12');
    """)
    duck_con.execute("""
        CREATE TABLE raw.uk_accidents (
            accident_index          VARCHAR,
            longitude               DOUBLE,
            latitude                DOUBLE,
            accident_severity       INTEGER,
            date                    DATE,
            number_of_casualties    INTEGER,
            number_of_vehicles      INTEGER,
            collision_year          INTEGER,
            year                    INTEGER,
            hour_of_day             INTEGER,
            day_of_week             INTEGER,
            road_type               VARCHAR,
            speed_limit             INTEGER,
            light_conditions        INTEGER,
            weather_conditions      INTEGER,
            collision_index         VARCHAR,
            collision_severity      INTEGER
        );
    """)
    duck_con.execute("""
        INSERT INTO raw.uk_accidents VALUES
            ('2022A001', -0.12, 51.50, 1, '2022-06-01', 1, 1, 2022, 2022, 8,  2, 'Single', 30, 1, 1, '2022A001', 1),
            ('2022A002', -0.09, 51.51, 3, '2022-07-15', 1, 1, 2022, 2022, 17, 4, 'Single', 20, 4, 2, '2022A002', 3);
    """)
    return duck_con


# ─────────────────────────────────────────────────────────────────────────────
# Environment variable helpers
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    """Ensure tests don't accidentally read user's .env values."""
    monkeypatch.delenv("DESTINATION", raising=False)
    monkeypatch.delenv("GOOGLE_APPLICATION_CREDENTIALS", raising=False)
