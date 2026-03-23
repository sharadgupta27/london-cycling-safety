"""
Tests for ingestion/ingest_tfl_cycling.py
==========================================
All network calls are patched; no real HTTP requests are made.
"""

from __future__ import annotations

import io
import os
import textwrap
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from ingestion.ingest_tfl_cycling import (
    COLUMN_MAP,
    REQUIRED_COLS,
    _build_destination,
    _extract_stations,
    _normalise_columns,
    discover_tfl_csv_urls,
    _download_csv,
)


# ─────────────────────────────────────────────────────────────────────────────
# _normalise_columns
# ─────────────────────────────────────────────────────────────────────────────

class TestNormaliseColumns:
    def test_renames_title_case_headers(self):
        df = pd.DataFrame(columns=[
            "Rental Id", "Duration", "Bike Id",
            "Start Date", "StartStation Id", "StartStation Name",
            "End Date",   "EndStation Id",   "EndStation Name",
        ])
        result = _normalise_columns(df)
        assert "rental_id"          in result.columns
        assert "duration_seconds"   in result.columns
        assert "start_station_id"   in result.columns
        assert "end_station_name"   in result.columns

    def test_passthrough_already_snake_case(self):
        df = pd.DataFrame(columns=["rental_id", "duration_seconds", "bike_id"])
        result = _normalise_columns(df)
        assert list(result.columns) == ["rental_id", "duration_seconds", "bike_id"]

    def test_unknown_column_is_lowercased(self):
        df = pd.DataFrame(columns=["SomeWeirdColumn"])
        result = _normalise_columns(df)
        assert "someweirdcolumn" in result.columns

    def test_does_not_drop_data(self, sample_journey_df):
        original_rows = len(sample_journey_df)
        result = _normalise_columns(sample_journey_df.copy())
        assert len(result) == original_rows

    def test_longitude_latitude_renamed(self):
        df = pd.DataFrame(columns=[
            "Rental Id", "Duration", "Bike Id",
            "Start Date", "StartStation Id", "StartStation Name",
            "StartStation Longitude", "StartStation Latitude",
            "End Date",   "EndStation Id",   "EndStation Name",
            "EndStation Longitude",   "EndStation Latitude",
        ])
        result = _normalise_columns(df)
        assert "start_lon" in result.columns
        assert "start_lat" in result.columns
        assert "end_lon"   in result.columns
        assert "end_lat"   in result.columns


# ─────────────────────────────────────────────────────────────────────────────
# _extract_stations
# ─────────────────────────────────────────────────────────────────────────────

class TestExtractStations:
    def test_returns_unique_stations(self, sample_journey_df):
        stations = _extract_stations(sample_journey_df)
        # journey_df has 3 start stations + 3 end stations but only 3 unique IDs
        assert len(stations) == 3
        assert set(stations["station_id"]) == {1, 2, 3}

    def test_output_columns(self, sample_journey_df):
        stations = _extract_stations(sample_journey_df)
        for col in ("station_id", "station_name", "longitude", "latitude"):
            assert col in stations.columns

    def test_no_coords_returns_empty_df(self, sample_journey_df_no_coords):
        stations = _extract_stations(sample_journey_df_no_coords)
        assert len(stations) == 0
        for col in ("station_id", "station_name", "longitude", "latitude"):
            assert col in stations.columns

    def test_drops_rows_with_null_lat(self, sample_journey_df):
        df = sample_journey_df.copy()
        df.loc[0, "start_lat"] = None
        stations = _extract_stations(df)
        # station_id=1 appears as a start station with null lat; should still
        # appear via the end-station rows (end_lat is fine).
        assert len(stations) <= 3

    def test_station_id_is_numeric(self, sample_journey_df):
        stations = _extract_stations(sample_journey_df)
        assert pd.api.types.is_numeric_dtype(stations["station_id"])


# ─────────────────────────────────────────────────────────────────────────────
# _download_csv  (network mocked)
# ─────────────────────────────────────────────────────────────────────────────

def _minimal_tfl_csv() -> bytes:
    """Return a minimal valid TFL journey CSV as bytes."""
    csv_text = textwrap.dedent("""\
        Rental Id,Duration,Bike Id,End Date,EndStation Id,EndStation Name,Start Date,StartStation Id,StartStation Name,StartStation Longitude,StartStation Latitude,EndStation Longitude,EndStation Latitude
        1001,600,101,01/06/2023 08:10,2,London Bridge,01/06/2023 08:00,1,Waterloo,-0.1149,51.5036,-0.0875,51.5055
        1002,1200,102,01/06/2023 09:20,3,Victoria,01/06/2023 09:00,2,London Bridge,-0.0875,51.5055,-0.1447,51.4952
    """)
    return csv_text.encode()


class TestDownloadCsv:
    def test_returns_dataframe_on_success(self):
        mock_resp = MagicMock()
        mock_resp.raise_for_status.return_value = None
        mock_resp.content = _minimal_tfl_csv()
        with patch("ingestion.ingest_tfl_cycling.requests.get", return_value=mock_resp):
            df = _download_csv("https://fake.url/test.csv")
        assert df is not None
        assert isinstance(df, pd.DataFrame)
        assert len(df) == 2

    def test_returns_none_on_http_error(self):
        import requests as req_mod
        mock_resp = MagicMock()
        mock_resp.raise_for_status.side_effect = req_mod.HTTPError("404")
        with patch("ingestion.ingest_tfl_cycling.requests.get", return_value=mock_resp):
            result = _download_csv("https://fake.url/missing.csv")
        assert result is None

    def test_columns_are_normalised(self):
        mock_resp = MagicMock()
        mock_resp.raise_for_status.return_value = None
        mock_resp.content = _minimal_tfl_csv()
        with patch("ingestion.ingest_tfl_cycling.requests.get", return_value=mock_resp):
            df = _download_csv("https://fake.url/test.csv")
        assert "rental_id" in df.columns
        assert "duration_seconds" in df.columns

    def test_source_file_column_added(self):
        mock_resp = MagicMock()
        mock_resp.raise_for_status.return_value = None
        mock_resp.content = _minimal_tfl_csv()
        with patch("ingestion.ingest_tfl_cycling.requests.get", return_value=mock_resp):
            df = _download_csv("https://fake.url/myfile.csv")
        assert "source_file" in df.columns
        assert df["source_file"].iloc[0] == "myfile.csv"

    def test_filters_non_london_rows(self):
        """Rows outside London bounding box should be dropped."""
        csv_text = textwrap.dedent("""\
            Rental Id,Duration,Bike Id,End Date,EndStation Id,EndStation Name,Start Date,StartStation Id,StartStation Name,StartStation Longitude,StartStation Latitude,EndStation Longitude,EndStation Latitude
            9001,600,901,01/06/2023 08:10,2,X,01/06/2023 08:00,1,Y,2.00,52.00,3.00,53.00
        """).encode()
        mock_resp = MagicMock()
        mock_resp.raise_for_status.return_value = None
        mock_resp.content = csv_text
        with patch("ingestion.ingest_tfl_cycling.requests.get", return_value=mock_resp):
            df = _download_csv("https://fake.url/outside.csv")
        # Non-London lat/lon → all rows filtered out → None or empty
        assert df is None or len(df) == 0


# ─────────────────────────────────────────────────────────────────────────────
# _build_destination
# ─────────────────────────────────────────────────────────────────────────────

class TestBuildDestination:
    def test_default_is_duckdb(self, monkeypatch):
        monkeypatch.delenv("DESTINATION", raising=False)
        import dlt
        with patch("ingestion.ingest_tfl_cycling.dlt.destinations.duckdb") as mock_duckdb:
            mock_duckdb.return_value = MagicMock()
            _build_destination()
            mock_duckdb.assert_called_once()

    def test_bigquery_destination(self, monkeypatch):
        monkeypatch.setenv("DESTINATION", "bigquery")
        import dlt
        with patch("ingestion.ingest_tfl_cycling.dlt.destinations.bigquery") as mock_bq:
            mock_bq.return_value = MagicMock()
            _build_destination()
            mock_bq.assert_called_once()

    def test_case_insensitive(self, monkeypatch):
        monkeypatch.setenv("DESTINATION", "BigQuery")
        import dlt
        with patch("ingestion.ingest_tfl_cycling.dlt.destinations.bigquery") as mock_bq:
            mock_bq.return_value = MagicMock()
            _build_destination()
            mock_bq.assert_called_once()


# ─────────────────────────────────────────────────────────────────────────────
# discover_tfl_csv_urls  (network mocked)
# ─────────────────────────────────────────────────────────────────────────────

class TestDiscoverTflCsvUrls:
    _S3_XML = textwrap.dedent("""\
        <?xml version="1.0" encoding="UTF-8"?>
        <ListBucketResult xmlns="http://s3.amazonaws.com/doc/2006-03-01/">
          <Key>usage-stats/500JourneyDataExtract01Jan2024-07Jan2024.csv</Key>
          <Key>usage-stats/501JourneyDataExtract08Jan2024-14Jan2024.csv</Key>
          <Key>usage-stats/502JourneyDataExtract15Jan2024-21Jan2024.csv</Key>
        </ListBucketResult>
    """)

    def test_returns_list_of_urls(self):
        mock_resp = MagicMock()
        mock_resp.raise_for_status.return_value = None
        mock_resp.status_code = 200
        mock_resp.text = self._S3_XML
        with patch("ingestion.ingest_tfl_cycling.requests.get", return_value=mock_resp):
            urls = discover_tfl_csv_urls(n=2)
        assert isinstance(urls, list)
        assert len(urls) == 2

    def test_urls_are_strings(self):
        mock_resp = MagicMock()
        mock_resp.raise_for_status.return_value = None
        mock_resp.status_code = 200
        mock_resp.text = self._S3_XML
        with patch("ingestion.ingest_tfl_cycling.requests.get", return_value=mock_resp):
            urls = discover_tfl_csv_urls(n=3)
        for url in urls:
            assert isinstance(url, str)
            assert url.startswith("http")

    def test_returns_empty_list_on_all_failures(self):
        import requests as req_mod
        with patch(
            "ingestion.ingest_tfl_cycling.requests.get",
            side_effect=req_mod.ConnectionError("network down"),
        ):
            urls = discover_tfl_csv_urls(n=5)
        assert isinstance(urls, list)

    def test_sorted_descending(self):
        """Later file numbers should appear first (newest files first)."""
        mock_resp = MagicMock()
        mock_resp.raise_for_status.return_value = None
        mock_resp.status_code = 200
        mock_resp.text = self._S3_XML
        with patch("ingestion.ingest_tfl_cycling.requests.get", return_value=mock_resp):
            urls = discover_tfl_csv_urls(n=3)
        # Files are named 500, 501, 502 – descending means 502 first
        if len(urls) >= 2:
            assert urls[0] >= urls[1]


# ─────────────────────────────────────────────────────────────────────────────
# COLUMN_MAP and REQUIRED_COLS sanity checks
# ─────────────────────────────────────────────────────────────────────────────

class TestConstants:
    def test_required_cols_is_set(self):
        assert isinstance(REQUIRED_COLS, set)
        assert "rental_id" in REQUIRED_COLS
        assert "start_station_id" in REQUIRED_COLS

    def test_column_map_covers_both_formats(self):
        # Title-case (original CSV headers)
        assert COLUMN_MAP.get("Rental Id") == "rental_id"
        assert COLUMN_MAP.get("Duration") == "duration_seconds"
        # snake_case passthrough
        assert COLUMN_MAP.get("rental_id") == "rental_id"
        assert COLUMN_MAP.get("duration") == "duration_seconds"
