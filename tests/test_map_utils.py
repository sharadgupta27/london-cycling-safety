"""
Tests for dashboard/utils/map_utils.py
=======================================
Folium-based mapping utilities: base_map, heatmap, station circles,
corridor lines, and legend injection.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pandas as pd
import pytest


# ─────────────────────────────────────────────────────────────────────────────
# Streamlit stub (map_utils may transitively import streamlit-adjacent libs)
# ─────────────────────────────────────────────────────────────────────────────
import sys
import types

st_stub = types.ModuleType("streamlit")
st_stub.cache_data = lambda *args, **kwargs: (lambda fn: fn)
sys.modules.setdefault("streamlit", st_stub)

from dashboard.utils.map_utils import (
    add_corridor_lines,
    add_heatmap_layer,
    add_legend,
    add_station_circles,
    base_map,
)

import folium


# ─────────────────────────────────────────────────────────────────────────────
# Sample DataFrames
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture()
def station_df():
    return pd.DataFrame({
        "station_id":    [1, 2, 3],
        "station_name":  ["King's Cross", "London Bridge", "Victoria"],
        "start_lat":     [51.530, 51.506, 51.495],
        "start_lon":     [-0.123, -0.086, -0.144],
        "weighted_risk_score": [15.2, 8.4, 4.1],
    })


@pytest.fixture()
def accident_df():
    return pd.DataFrame({
        "latitude":  [51.52, 51.50, 51.48],
        "longitude": [-0.10, -0.08, -0.12],
        "severity":  [1, 2, 3],
    })


@pytest.fixture()
def corridor_df():
    return pd.DataFrame({
        "corridor_label":         ["A–B", "C–D"],
        "lat_a":                  [51.53, 51.51],
        "lon_a":                  [-0.12, -0.10],
        "lat_b":                  [51.50, 51.49],
        "lon_b":                  [-0.09, -0.08],
        "mid_lat":                [51.515, 51.500],
        "mid_lon":                [-0.105, -0.090],
        "journey_count":          [5000, 2000],
        "corridor_accident_count":[8, 3],
        "risk_category":          ["HIGH", "MEDIUM"],
        "corridor_colour":        ["#d73027", "#fee08b"],
        "risk_per_km":            [0.8, 0.4],
        "length_m":               [1200, 900],
    })


# ─────────────────────────────────────────────────────────────────────────────
# base_map
# ─────────────────────────────────────────────────────────────────────────────

class TestBaseMap:
    def test_returns_folium_map(self):
        m = base_map()
        assert isinstance(m, folium.Map)

    def test_default_centre_is_london(self):
        m = base_map()
        lat, lon = m.location
        assert abs(lat - 51.505) < 0.1
        assert abs(lon - (-0.09)) < 0.2

    def test_custom_centre(self):
        m = base_map(lat=51.52, lon=-0.11)
        lat, lon = m.location
        assert abs(lat - 51.52) < 0.001
        assert abs(lon - (-0.11)) < 0.001

    def test_default_zoom_around_11(self):
        m = base_map()
        assert 9 <= m.options.get("zoom", m.options.get("zoom_start", 11)) <= 14

    def test_minimap_added(self):
        m = base_map()
        children_types = {type(c).__name__ for c in m._children.values()}
        assert "MiniMap" in children_types


# ─────────────────────────────────────────────────────────────────────────────
# add_heatmap_layer
# ─────────────────────────────────────────────────────────────────────────────

class TestAddHeatmapLayer:
    def test_returns_same_map(self, accident_df):
        m = base_map()
        result = add_heatmap_layer(m, accident_df)
        assert result is m

    def test_heatmap_child_added(self, accident_df):
        m = base_map()
        add_heatmap_layer(m, accident_df)
        children_types = {type(c).__name__ for c in m._children.values()}
        assert "HeatMap" in children_types

    def test_handles_empty_dataframe(self):
        m = base_map()
        empty = pd.DataFrame({"latitude": [], "longitude": []})
        # Should not raise
        result = add_heatmap_layer(m, empty)
        assert result is m

    def test_weight_col_used_when_present(self, accident_df):
        m = base_map()
        # Should not raise when a valid weight column is provided
        add_heatmap_layer(m, accident_df, weight_col="severity")

    def test_missing_weight_col_does_not_raise(self, accident_df):
        m = base_map()
        # non-existent column: should fall back gracefully
        add_heatmap_layer(m, accident_df, weight_col="nonexistent_col")


# ─────────────────────────────────────────────────────────────────────────────
# add_station_circles
# ─────────────────────────────────────────────────────────────────────────────

class TestAddStationCircles:
    def test_returns_same_map(self, station_df):
        m = base_map()
        result = add_station_circles(m, station_df, lat_col="start_lat", lon_col="start_lon")
        assert result is m

    def test_feature_group_added(self, station_df):
        m = base_map()
        add_station_circles(m, station_df, lat_col="start_lat", lon_col="start_lon")
        children_types = {type(c).__name__ for c in m._children.values()}
        assert "FeatureGroup" in children_types

    def test_handles_empty_dataframe(self):
        m = base_map()
        empty = pd.DataFrame({"start_lat": [], "start_lon": []})
        result = add_station_circles(m, empty)
        assert result is m

    def test_custom_lat_lon_cols(self, station_df):
        # If the function accepts lat_col / lon_col kwargs, it should use them
        m = base_map()
        result = add_station_circles(
            m, station_df,
            lat_col="start_lat", lon_col="start_lon",
        )
        assert isinstance(result, folium.Map)

    def test_popup_cols_do_not_raise(self, station_df):
        m = base_map()
        add_station_circles(
            m, station_df,
            lat_col="start_lat", lon_col="start_lon",
            popup_cols=["station_name", "weighted_risk_score"],
        )


# ─────────────────────────────────────────────────────────────────────────────
# add_corridor_lines
# ─────────────────────────────────────────────────────────────────────────────

class TestAddCorridorLines:
    def test_returns_same_map(self, corridor_df):
        m = base_map()
        result = add_corridor_lines(m, corridor_df)
        assert result is m

    def test_feature_group_added(self, corridor_df):
        m = base_map()
        add_corridor_lines(m, corridor_df)
        children_types = {type(c).__name__ for c in m._children.values()}
        assert "FeatureGroup" in children_types

    def test_handles_empty_dataframe(self):
        m = base_map()
        empty = pd.DataFrame({
            "lat_a": [], "lon_a": [], "lat_b": [], "lon_b": [],
            "mid_lat": [], "mid_lon": [],
        })
        result = add_corridor_lines(m, empty)
        assert result is m

    def test_corridor_colour_applied(self, corridor_df):
        """Each row's colour should appear in the rendered HTML."""
        m = base_map()
        add_corridor_lines(m, corridor_df)
        html = m._repr_html_()
        assert "#d73027" in html
        assert "#fee08b" in html


# ─────────────────────────────────────────────────────────────────────────────
# add_legend
# ─────────────────────────────────────────────────────────────────────────────

class TestAddLegend:
    def test_returns_same_map(self):
        m = base_map()
        result = add_legend(m, "Test", {"Low": "#00ff00", "High": "#ff0000"})
        assert result is m

    def test_legend_html_injected(self):
        m = base_map()
        add_legend(m, "Risk Legend", {"Low": "#00ff00", "High": "#ff0000"})
        html = m._repr_html_()
        assert "Risk Legend" in html
        assert "#00ff00" in html
        assert "#ff0000" in html

    def test_empty_colour_labels(self):
        m = base_map()
        # Should not raise with empty dict
        result = add_legend(m, "Empty", {})
        assert result is m
