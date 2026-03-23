"""
Tests for transforms/spatial_transforms.py
===========================================
Uses an in-memory DuckDB connection with fake spatial extension simulation.
Heavy SQL queries are run against the in-memory duck_con_with_raw fixture.
"""

from __future__ import annotations

import re
from unittest.mock import MagicMock, patch

import duckdb
import pandas as pd
import pytest

from transforms.spatial_transforms import (
    ACCIDENTS_GEO_SQL,
    BLACKSPOT_RADIUS_M,
    CORRIDOR_JOURNEYS_SQL,
    STATION_PROXIMITY_SQL,
    STATIONS_GEO_SQL,
    TRANSFORMS,
    _check_required_tables,
    create_spatial_schema,
    get_connection,
    run,
)


# ─────────────────────────────────────────────────────────────────────────────
# get_connection
# ─────────────────────────────────────────────────────────────────────────────

class TestGetConnection:
    def test_returns_duckdb_connection(self, tmp_path):
        db = str(tmp_path / "test.duckdb")
        # Patch the spatial extension install so tests don't need the extension binary
        with patch("transforms.spatial_transforms.duckdb.connect") as mock_connect:
            mock_con = MagicMock(spec=duckdb.DuckDBPyConnection)
            mock_connect.return_value = mock_con
            con = get_connection(db)
            mock_connect.assert_called_once_with(db)
            mock_con.execute.assert_called_with("INSTALL spatial; LOAD spatial;")

    def test_calls_spatial_extension(self, tmp_path):
        db = str(tmp_path / "test.duckdb")
        with patch("transforms.spatial_transforms.duckdb.connect") as mock_connect:
            mock_con = MagicMock(spec=duckdb.DuckDBPyConnection)
            mock_connect.return_value = mock_con
            get_connection(db)
            calls = [str(c) for c in mock_con.execute.call_args_list]
            assert any("spatial" in c.lower() for c in calls)


# ─────────────────────────────────────────────────────────────────────────────
# create_spatial_schema
# ─────────────────────────────────────────────────────────────────────────────

class TestCreateSpatialSchema:
    def test_creates_schema(self, duck_con):
        create_spatial_schema(duck_con)
        schemas = duck_con.execute(
            "SELECT schema_name FROM information_schema.schemata"
        ).fetchall()
        schema_names = [s[0] for s in schemas]
        assert "spatial_layer" in schema_names

    def test_idempotent(self, duck_con):
        create_spatial_schema(duck_con)
        create_spatial_schema(duck_con)  # should not raise
        schemas = duck_con.execute(
            "SELECT schema_name FROM information_schema.schemata"
        ).fetchall()
        schema_names = [s[0] for s in schemas]
        assert schema_names.count("spatial_layer") == 1


# ─────────────────────────────────────────────────────────────────────────────
# _check_required_tables
# ─────────────────────────────────────────────────────────────────────────────

class TestCheckRequiredTables:
    def test_returns_empty_when_all_tables_exist(self, duck_con_with_raw):
        missing = _check_required_tables(duck_con_with_raw)
        assert missing == []

    def test_returns_missing_table_names(self, duck_con):
        duck_con.execute("CREATE SCHEMA IF NOT EXISTS raw;")
        missing = _check_required_tables(duck_con)
        assert "uk_accidents"  in missing
        assert "tfl_journeys"  in missing
        assert "tfl_stations"  in missing

    def test_returns_only_actually_missing(self, duck_con):
        duck_con.execute("CREATE SCHEMA IF NOT EXISTS raw;")
        duck_con.execute("CREATE TABLE raw.uk_accidents (id INTEGER);")
        missing = _check_required_tables(duck_con)
        assert "uk_accidents" not in missing
        assert "tfl_journeys"  in missing


# ─────────────────────────────────────────────────────────────────────────────
# CORRIDOR_JOURNEYS_SQL  (logic test against in-memory data)
# ─────────────────────────────────────────────────────────────────────────────

class TestCorridorJourneysSQL:
    def test_deduplicates_directions(self, duck_con_with_raw):
        """LEAST/GREATEST ensures A→B and B→A are counted together."""
        duck_con_with_raw.execute("CREATE SCHEMA IF NOT EXISTS spatial_layer;")
        duck_con_with_raw.execute(CORRIDOR_JOURNEYS_SQL)
        rows = duck_con_with_raw.execute(
            "SELECT * FROM spatial_layer.corridor_journeys"
        ).fetchall()
        # station_a_id should always be <= station_b_id
        for row in rows:
            assert row[0] <= row[1], "station_a_id should be the smaller of the two"

    def test_minimum_10_journeys_threshold(self, duck_con_with_raw):
        """Corridors with fewer than 10 journeys should be excluded by HAVING COUNT(*) >= 10."""
        duck_con_with_raw.execute("CREATE SCHEMA IF NOT EXISTS spatial_layer;")
        # duck_con_with_raw only has 5 total journeys between pair (1,2)
        duck_con_with_raw.execute(CORRIDOR_JOURNEYS_SQL)
        rows = duck_con_with_raw.execute(
            "SELECT station_a_id, station_b_id, journey_count "
            "FROM spatial_layer.corridor_journeys"
        ).fetchall()
        # With only 5 rows total in the fixture, this should be empty
        for row in rows:
            assert row[2] >= 10


# ─────────────────────────────────────────────────────────────────────────────
# SQL constant string sanity checks
# ─────────────────────────────────────────────────────────────────────────────

class TestSqlConstants:
    def test_accidents_geo_sql_references_raw_uk_accidents(self):
        assert "raw.uk_accidents" in ACCIDENTS_GEO_SQL

    def test_accidents_geo_sql_creates_table_in_spatial_layer(self):
        assert "spatial_layer.accidents_geo" in ACCIDENTS_GEO_SQL

    def test_stations_geo_sql_references_raw_tfl_stations(self):
        assert "raw.tfl_stations" in STATIONS_GEO_SQL

    def test_station_proximity_sql_uses_radius_value(self):
        assert str(int(BLACKSPOT_RADIUS_M)) in STATION_PROXIMITY_SQL

    def test_all_transforms_listed(self):
        expected_names = {
            "accidents_geo", "stations_geo", "station_blackspot_scores",
            "corridor_journeys", "corridor_risk",
            "monthly_accident_trend",
        }
        actual_names = {name for name, _ in TRANSFORMS}
        assert expected_names == actual_names

    def test_blackspot_radius_is_positive(self):
        assert BLACKSPOT_RADIUS_M > 0


# ─────────────────────────────────────────────────────────────────────────────
# run()  (mocked connection)
# ─────────────────────────────────────────────────────────────────────────────

class TestRunFunction:
    def test_raises_on_missing_raw_tables(self, tmp_path):
        """run() should raise RuntimeError when raw tables don't exist."""
        db = str(tmp_path / "empty.duckdb")
        # Patch get_connection to return an in-memory connection that has no raw tables
        with patch("transforms.spatial_transforms.get_connection") as mock_gc:
            con = duckdb.connect(":memory:")
            mock_gc.return_value = con
            with pytest.raises(RuntimeError, match="Required raw tables not found"):
                run(db)

    def test_calls_get_connection_with_db_path(self, tmp_path):
        db = str(tmp_path / "test.duckdb")
        mock_con = MagicMock()
        mock_con.execute.return_value = MagicMock(fetchone=lambda: (0,))

        # Make _check_required_tables think all tables exist
        with patch("transforms.spatial_transforms.get_connection", return_value=mock_con), \
             patch("transforms.spatial_transforms._check_required_tables", return_value=[]), \
             patch("transforms.spatial_transforms.create_spatial_schema"):
            run(db)

        from transforms.spatial_transforms import get_connection as gc_fn
