"""
Tests for dashboard/utils/data_loader.py
=========================================
Streamlit cache functions and DuckDB query helpers.
All DuckDB connections are mocked to avoid needing a real database file.
"""

from __future__ import annotations

from unittest.mock import MagicMock, call, patch

import pandas as pd
import pytest


# Streamlit must be importable but we don't want it to start a server;
# patch st.cache_data before importing the module under test.
import sys
import types

# Stub out streamlit so the module can be imported without a Streamlit server
st_stub = types.ModuleType("streamlit")
st_stub.cache_data = lambda *args, **kwargs: (lambda fn: fn)
sys.modules.setdefault("streamlit", st_stub)

from dashboard.utils.data_loader import (
    _con,
    load_accidents_raw,
    load_blackspot_stations,
    load_corridor_risk,
    load_monthly_trend,
    load_temporal_hourly,
    load_temporal_period,
    pipeline_summary,
)


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _mock_con(df: pd.DataFrame | None = None):
    """Return a mock DuckDB connection whose .execute().df() returns df."""
    con = MagicMock()
    if df is not None:
        con.execute.return_value.df.return_value = df
    return con


# ─────────────────────────────────────────────────────────────────────────────
# _con helper
# ─────────────────────────────────────────────────────────────────────────────

class TestConHelper:
    def test_opens_read_only_connection(self):
        with patch("dashboard.utils.data_loader.duckdb.connect") as mock_connect:
            mock_con = MagicMock()
            mock_connect.return_value = mock_con
            _con()
            # Should be called with read_only=True
            _, kwargs = mock_connect.call_args
            assert kwargs.get("read_only") is True

    def test_loads_spatial_extension(self):
        with patch("dashboard.utils.data_loader.duckdb.connect") as mock_connect:
            mock_con = MagicMock()
            mock_connect.return_value = mock_con
            _con()
            calls = [str(c) for c in mock_con.execute.call_args_list]
            assert any("spatial" in c.lower() for c in calls)

    def test_silently_ignores_spatial_load_error(self):
        with patch("dashboard.utils.data_loader.duckdb.connect") as mock_connect:
            mock_con = MagicMock()
            mock_con.execute.side_effect = Exception("spatial not installed")
            mock_connect.return_value = mock_con
            # Should not raise
            con = _con()
            assert con is mock_con


# ─────────────────────────────────────────────────────────────────────────────
# load_blackspot_stations
# ─────────────────────────────────────────────────────────────────────────────

class TestLoadBlackspotStations:
    def test_returns_dataframe(self):
        expected = pd.DataFrame({
            "station_id": [1, 2],
            "weighted_risk_score": [15, 8],
        })
        with patch("dashboard.utils.data_loader._con", return_value=_mock_con(expected)):
            result = load_blackspot_stations()
        assert isinstance(result, pd.DataFrame)
        assert len(result) == 2

    def test_queries_mart_blackspot_analysis(self):
        expected = pd.DataFrame({"station_id": [1]})
        mock_con = _mock_con(expected)
        with patch("dashboard.utils.data_loader._con", return_value=mock_con):
            load_blackspot_stations()
        sql = mock_con.execute.call_args[0][0]
        assert "mart_blackspot_analysis" in sql

    def test_orders_by_risk_score_desc(self):
        expected = pd.DataFrame({"station_id": [1]})
        mock_con = _mock_con(expected)
        with patch("dashboard.utils.data_loader._con", return_value=mock_con):
            load_blackspot_stations()
        sql = mock_con.execute.call_args[0][0].upper()
        assert "ORDER BY" in sql
        assert "DESC" in sql

    def test_closes_connection(self):
        mock_con = _mock_con(pd.DataFrame())
        with patch("dashboard.utils.data_loader._con", return_value=mock_con):
            load_blackspot_stations()
        mock_con.close.assert_called_once()


# ─────────────────────────────────────────────────────────────────────────────
# load_corridor_risk
# ─────────────────────────────────────────────────────────────────────────────

class TestLoadCorridorRisk:
    def test_returns_dataframe(self):
        expected = pd.DataFrame({"risk_rank": [1, 2, 3]})
        with patch("dashboard.utils.data_loader._con", return_value=_mock_con(expected)):
            result = load_corridor_risk(top_n=3)
        assert isinstance(result, pd.DataFrame)

    def test_respects_top_n(self):
        expected = pd.DataFrame({"risk_rank": [1]})
        mock_con = _mock_con(expected)
        with patch("dashboard.utils.data_loader._con", return_value=mock_con):
            load_corridor_risk(top_n=42)
        sql = mock_con.execute.call_args[0][0]
        assert "42" in sql

    def test_queries_mart_corridor_risk_score(self):
        mock_con = _mock_con(pd.DataFrame())
        with patch("dashboard.utils.data_loader._con", return_value=mock_con):
            load_corridor_risk()
        sql = mock_con.execute.call_args[0][0]
        assert "mart_corridor_risk_score" in sql


# ─────────────────────────────────────────────────────────────────────────────
# load_accidents_raw
# ─────────────────────────────────────────────────────────────────────────────

class TestLoadAccidentsRaw:
    def test_returns_dataframe(self):
        expected = pd.DataFrame({
            "accident_index": ["A001"],
            "longitude": [-0.12],
            "latitude": [51.50],
        })
        with patch("dashboard.utils.data_loader._con", return_value=_mock_con(expected)):
            result = load_accidents_raw()
        assert isinstance(result, pd.DataFrame)

    def test_queries_stg_accidents(self):
        mock_con = _mock_con(pd.DataFrame())
        with patch("dashboard.utils.data_loader._con", return_value=mock_con):
            load_accidents_raw()
        sql = mock_con.execute.call_args[0][0]
        assert "stg_accidents" in sql

    def test_filters_null_coordinates(self):
        mock_con = _mock_con(pd.DataFrame())
        with patch("dashboard.utils.data_loader._con", return_value=mock_con):
            load_accidents_raw()
        sql = mock_con.execute.call_args[0][0]
        assert "IS NOT NULL" in sql


# ─────────────────────────────────────────────────────────────────────────────
# pipeline_summary
# ─────────────────────────────────────────────────────────────────────────────

class TestPipelineSummary:
    def test_returns_dict(self):
        mock_con = MagicMock()
        mock_con.execute.return_value.fetchone.return_value = (42,)
        with patch("dashboard.utils.data_loader._con", return_value=mock_con):
            result = pipeline_summary()
        assert isinstance(result, dict)

    def test_has_expected_keys(self):
        mock_con = MagicMock()
        mock_con.execute.return_value.fetchone.return_value = (100,)
        with patch("dashboard.utils.data_loader._con", return_value=mock_con):
            result = pipeline_summary()
        for key in ("journeys", "stations", "accidents", "casualties"):
            assert key in result

    def test_handles_missing_table_gracefully(self):
        mock_con = MagicMock()
        mock_con.execute.side_effect = Exception("Table not found")
        with patch("dashboard.utils.data_loader._con", return_value=mock_con):
            result = pipeline_summary()
        for key in ("journeys", "stations", "accidents", "casualties"):
            assert result[key] == "N/A"

    def test_returns_integer_counts(self):
        mock_con = MagicMock()
        mock_con.execute.return_value.fetchone.return_value = (9999,)
        with patch("dashboard.utils.data_loader._con", return_value=mock_con):
            result = pipeline_summary()
        for key, val in result.items():
            if val != "N/A":
                assert isinstance(val, int), f"{key} should be int, got {type(val)}"


# ─────────────────────────────────────────────────────────────────────────────
# load_temporal_* functions
# ─────────────────────────────────────────────────────────────────────────────

class TestLoadTemporalFunctions:
    @pytest.mark.parametrize("loader,grain", [
        (load_temporal_hourly, "hourly"),
        (load_temporal_period, "time_period"),
        (load_monthly_trend,   "monthly"),
    ])
    def test_queries_correct_grain(self, loader, grain):
        mock_con = _mock_con(pd.DataFrame())
        with patch("dashboard.utils.data_loader._con", return_value=mock_con):
            loader()
        sql = mock_con.execute.call_args[0][0]
        assert grain in sql

    @pytest.mark.parametrize("loader", [
        load_temporal_hourly,
        load_temporal_period,
        load_monthly_trend,
    ])
    def test_queries_mart_temporal_safety(self, loader):
        mock_con = _mock_con(pd.DataFrame())
        with patch("dashboard.utils.data_loader._con", return_value=mock_con):
            loader()
        sql = mock_con.execute.call_args[0][0]
        assert "mart_temporal_safety" in sql

    @pytest.mark.parametrize("loader", [
        load_temporal_hourly,
        load_temporal_period,
        load_monthly_trend,
    ])
    def test_closes_connection(self, loader):
        mock_con = _mock_con(pd.DataFrame())
        with patch("dashboard.utils.data_loader._con", return_value=mock_con):
            loader()
        mock_con.close.assert_called_once()
