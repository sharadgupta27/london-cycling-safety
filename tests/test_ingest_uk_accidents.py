"""
Tests for ingestion/ingest_uk_accidents.py
===========================================
All network calls are patched; no real HTTP requests are made.
"""

from __future__ import annotations

import io
import textwrap
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from ingestion.ingest_uk_accidents import (
    LAT_MAX,
    LAT_MIN,
    LON_MAX,
    LON_MIN,
    STATS19_URLS,
    _download_stats19,
    _filter_london_accidents,
    _filter_years,
    _parse_accident_dates,
)


# ─────────────────────────────────────────────────────────────────────────────
# _filter_london_accidents
# ─────────────────────────────────────────────────────────────────────────────

class TestFilterLondonAccidents:
    def test_removes_rows_outside_bounding_box(self, sample_accidents_df):
        result = _filter_london_accidents(sample_accidents_df.copy())
        # Row index 2 has lon=0.50 / lat=52.00 — outside London bbox
        assert len(result) == 2

    def test_keeps_rows_inside_bounding_box(self, sample_accidents_df):
        result = _filter_london_accidents(sample_accidents_df.copy())
        assert all(result["longitude"].between(LON_MIN, LON_MAX))
        assert all(result["latitude"].between(LAT_MIN, LAT_MAX))

    def test_no_crash_if_no_coords_columns(self):
        df = pd.DataFrame({"accident_index": ["A001", "A002"], "severity": [1, 2]})
        result = _filter_london_accidents(df)
        # No lon/lat columns → original df returned unmodified
        assert len(result) == 2

    def test_coerces_string_coords(self):
        df = pd.DataFrame({
            "longitude": ["-0.12", "0.50"],   # strings
            "latitude":  ["51.50", "52.00"],
        })
        result = _filter_london_accidents(df)
        assert len(result) == 1

    def test_empty_df_returns_empty(self):
        df = pd.DataFrame({"longitude": [], "latitude": []})
        result = _filter_london_accidents(df)
        assert len(result) == 0

    def test_returns_copy_not_view(self, sample_accidents_df):
        result = _filter_london_accidents(sample_accidents_df.copy())
        assert result is not sample_accidents_df


# ─────────────────────────────────────────────────────────────────────────────
# _parse_accident_dates
# ─────────────────────────────────────────────────────────────────────────────

class TestParseAccidentDates:
    def test_parses_uk_date_format(self):
        df = pd.DataFrame({"date": ["01/06/2022", "15/07/2023"]})
        result = _parse_accident_dates(df)
        assert pd.api.types.is_datetime64_any_dtype(result["date"])
        assert result["date"].iloc[0].month == 6

    def test_adds_year_column(self):
        df = pd.DataFrame({"date": ["01/06/2022", "15/07/2023"]})
        result = _parse_accident_dates(df)
        assert "year" in result.columns
        assert result["year"].iloc[0] == 2022
        assert result["year"].iloc[1] == 2023

    def test_does_not_overwrite_existing_year_column(self):
        df = pd.DataFrame({"date": ["01/06/2022"], "year": [2022]})
        result = _parse_accident_dates(df)
        assert result["year"].iloc[0] == 2022

    def test_invalid_dates_become_nat(self):
        df = pd.DataFrame({"date": ["99/99/9999", "01/01/2022"]})
        result = _parse_accident_dates(df)
        assert pd.isna(result["date"].iloc[0])

    def test_no_date_column_returns_unchanged(self, sample_accidents_df):
        df = sample_accidents_df.drop(columns=["date"])
        result = _parse_accident_dates(df)
        assert "date" not in result.columns


# ─────────────────────────────────────────────────────────────────────────────
# _filter_years
# ─────────────────────────────────────────────────────────────────────────────

class TestFilterYears:
    def test_keeps_matching_years(self, sample_accidents_df):
        df = _parse_accident_dates(sample_accidents_df.copy())
        result = _filter_years(df, ["2022"])
        assert all(result["year"] == 2022)

    def test_filters_out_non_matching_years(self, sample_accidents_df):
        df = _parse_accident_dates(sample_accidents_df.copy())
        result = _filter_years(df, ["2099"])
        assert len(result) == 0

    def test_empty_years_returns_all(self, sample_accidents_df):
        df = _parse_accident_dates(sample_accidents_df.copy())
        result = _filter_years(df, [])
        assert len(result) == len(df)

    def test_multiple_years(self, sample_accidents_df):
        df = _parse_accident_dates(sample_accidents_df.copy())
        result = _filter_years(df, ["2021", "2022"])
        assert set(result["year"]) <= {2021, 2022}

    def test_no_year_column_returns_all(self):
        df = pd.DataFrame({"accident_index": ["A", "B"], "severity": [1, 2]})
        result = _filter_years(df, ["2022"])
        assert len(result) == 2


# ─────────────────────────────────────────────────────────────────────────────
# _download_stats19  (network mocked)
# ─────────────────────────────────────────────────────────────────────────────

def _minimal_accidents_csv() -> bytes:
    csv_text = textwrap.dedent("""\
        accident_index,longitude,latitude,accident_severity,date,number_of_casualties
        2022A001,-0.12,51.50,1,01/06/2022,1
        2022A002,-0.09,51.51,3,15/07/2022,1
    """)
    return csv_text.encode()


class TestDownloadStats19:
    def test_returns_dataframe_on_success(self):
        mock_resp = MagicMock()
        mock_resp.raise_for_status.return_value = None
        mock_resp.status_code = 200
        mock_resp.headers = {"content-length": "200"}
        mock_resp.iter_content.return_value = [_minimal_accidents_csv()]
        with patch("ingestion.ingest_uk_accidents.requests.get", return_value=mock_resp):
            df = _download_stats19("https://fake.url/accidents.csv", "accidents")
        assert df is not None
        assert isinstance(df, pd.DataFrame)
        assert len(df) == 2

    def test_columns_lowercased(self):
        mock_resp = MagicMock()
        mock_resp.raise_for_status.return_value = None
        mock_resp.status_code = 200
        mock_resp.headers = {"content-length": "200"}
        mock_resp.iter_content.return_value = [_minimal_accidents_csv()]
        with patch("ingestion.ingest_uk_accidents.requests.get", return_value=mock_resp):
            df = _download_stats19("https://fake.url/accidents.csv", "accidents")
        assert all(c == c.lower() for c in df.columns)

    def test_accident_reference_renamed_to_accident_index(self):
        csv_text = textwrap.dedent("""\
            accident_reference,longitude,latitude,accident_severity
            2024C001,-0.12,51.50,1
        """).encode()
        mock_resp = MagicMock()
        mock_resp.raise_for_status.return_value = None
        mock_resp.status_code = 200
        mock_resp.headers = {"content-length": "100"}
        mock_resp.iter_content.return_value = [csv_text]
        with patch("ingestion.ingest_uk_accidents.requests.get", return_value=mock_resp):
            df = _download_stats19("https://fake.url/collision.csv", "accidents")
        assert "accident_index" in df.columns
        assert "accident_reference" not in df.columns

    def test_returns_none_on_http_error(self):
        import requests as req_mod
        mock_resp = MagicMock()
        mock_resp.raise_for_status.side_effect = req_mod.HTTPError("404")
        with patch("ingestion.ingest_uk_accidents.requests.get", return_value=mock_resp):
            result = _download_stats19("https://fake.url/gone.csv", "accidents")
        assert result is None

    def test_tries_fallback_url_on_failure(self):
        import requests as req_mod
        call_count = {"n": 0}

        def side_effect(url, **kwargs):
            call_count["n"] += 1
            if call_count["n"] == 1:
                r = MagicMock()
                r.raise_for_status.side_effect = req_mod.HTTPError("404")
                return r
            # Second URL succeeds
            r = MagicMock()
            r.raise_for_status.return_value = None
            r.status_code = 200
            r.headers = {"content-length": "200"}
            r.iter_content.return_value = [_minimal_accidents_csv()]
            return r

        with patch("ingestion.ingest_uk_accidents.requests.get", side_effect=side_effect):
            df = _download_stats19(
                ["https://fake.url/first.csv", "https://fake.url/second.csv"],
                "accidents",
            )
        assert df is not None
        assert call_count["n"] == 2

    def test_all_urls_fail_returns_none(self):
        import requests as req_mod
        mock_resp = MagicMock()
        mock_resp.raise_for_status.side_effect = req_mod.HTTPError("404")
        with patch("ingestion.ingest_uk_accidents.requests.get", return_value=mock_resp):
            result = _download_stats19(
                ["https://fake.url/a.csv", "https://fake.url/b.csv"],
                "accidents",
            )
        assert result is None


# ─────────────────────────────────────────────────────────────────────────────
# STATS19_URLS constants
# ─────────────────────────────────────────────────────────────────────────────

class TestStats19Urls:
    def test_accidents_has_collision_url_first(self):
        """collision URL should be tried before the legacy accident URL."""
        urls = STATS19_URLS["accidents"]
        assert isinstance(urls, list)
        assert len(urls) >= 2
        assert "collision" in urls[0]

    def test_casualties_and_vehicles_defined(self):
        assert "casualties" in STATS19_URLS
        assert "vehicles" in STATS19_URLS
        assert len(STATS19_URLS["casualties"]) >= 1
        assert len(STATS19_URLS["vehicles"]) >= 1

    def test_bounding_box_constants(self):
        # London bbox sanity check
        assert LON_MIN < LON_MAX
        assert LAT_MIN < LAT_MAX
        assert -1.0 < LON_MIN < 0.0   # west of Greenwich
        assert 0.0 < LON_MAX < 1.0    # east of Greenwich
        assert 51.0 < LAT_MIN < 52.0
        assert 51.0 < LAT_MAX < 52.0
