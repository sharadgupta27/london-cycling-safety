"""
🚴 London Cycling Safety – Home Page
=====================================
ArcGIS-style dark dashboard entry point.

How to run:
    cd london-cycling-safety
    streamlit run dashboard/app.py
"""

import sys
from pathlib import Path

import folium
import streamlit as st
from streamlit_folium import st_folium

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from dashboard.utils.data_loader import load_blackspot_stations, pipeline_summary
from dashboard.utils.map_utils import add_legend, add_station_circles, base_map
from dashboard.utils.theme import (
    inject_arcgis_theme,
    page_tab_nav,
    gauge_indicator,
    ACCENT, DANGER, WARNING, SAFE, BLUE,
)

# ── Page config ────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="London Cycling Safety",
    page_icon="🚴",
    layout="wide",
    initial_sidebar_state="expanded",
)
inject_arcgis_theme()
page_tab_nav("home")

# ── Sidebar ─────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("""
    <div style="text-align:center; padding:0.5rem 0 0.9rem 0;">
      <div style="font-size:2.2rem; line-height:1.1;">🚴</div>
      <div style="color:#FF9800; font-weight:700; font-size:0.88rem;
                  text-transform:uppercase; letter-spacing:0.09em; margin-top:0.25rem;">
        London Cycling Safety
      </div>
      <div style="color:#3A3A3A; font-size:0.68rem; margin-top:0.12rem;">
        TFL Santander Bikes · DfT STATS19
      </div>
    </div>
    <hr style="border-color:#222; margin:0 0 0.7rem 0;">
    """, unsafe_allow_html=True)

    st.markdown(
        '<p style="color:#FF9800; font-size:0.7rem; text-transform:uppercase; '
        'letter-spacing:0.09em; margin-bottom:0.35rem; font-weight:700;">DATA SOURCES</p>',
        unsafe_allow_html=True,
    )
    for icon, label in [
        ("📡", "TFL Open Data · cycling.data.tfl.gov.uk"),
        ("🚦", "DfT STATS19 · data.dft.gov.uk"),
        ("☁️", "BigQuery · kestra-dataengg"),
        ("🔧", "dbt-bigquery 1.11 · dbt-core 1.8"),
    ]:
        st.markdown(
            f'<div style="font-size:0.71rem; color:#505050; padding:0.12rem 0;">'
            f'{icon}&nbsp; {label}</div>',
            unsafe_allow_html=True,
        )

# ── Top bar ─────────────────────────────────────────────────────────────────
st.markdown("""
<div class="top-bar">
  <div>
    <span class="top-bar-title">🚴 London Cycling Safety — Corridor Analysis</span>
    <span class="top-bar-sub">&nbsp;|&nbsp; TFL Santander Bikes × UK STATS19 Accidents</span>
  </div>
  <div style="font-size:0.72rem; color:#555;">
    Data Engineering Zoomcamp &nbsp;·&nbsp; BigQuery + dbt
  </div>
</div>
""", unsafe_allow_html=True)

# ── Load data ─────────────────────────────────────────────────────────────
with st.spinner("Loading overview data …"):
    try:
        counts = pipeline_summary()
    except Exception:
        counts = {}
    try:
        stations_df = load_blackspot_stations()
    except Exception:
        stations_df = None

journeys   = counts.get("journeys",   0) or 0
stations   = counts.get("stations",   0) or 0
accidents  = counts.get("accidents",  0) or 0
casualties = counts.get("casualties", 0) or 0

# ── Gauge row ────────────────────────────────────────────────────────────────
st.markdown(
    '<p style="color:#555; font-size:0.72rem; text-transform:uppercase; '
    'letter-spacing:0.07em; margin:0.5rem 0 0.1rem 0;">PIPELINE OVERVIEW</p>',
    unsafe_allow_html=True,
)

g1, g2, g3, g4 = st.columns(4)
with g1:
    st.plotly_chart(
        gauge_indicator(journeys / 1_000_000, "Bike Journeys (M)", max_val=6,
                        fmt=".2f", suffix=" M", accent=BLUE),
        use_container_width=True, config={"displayModeBar": True, "displaylogo": False},
    )
with g2:
    st.plotly_chart(
        gauge_indicator(stations, "Docking Stations", max_val=900,
                        fmt=",.0f", accent=SAFE),
        use_container_width=True, config={"displayModeBar": True, "displaylogo": False},
    )
with g3:
    st.plotly_chart(
        gauge_indicator(accidents / 1_000, "Road Accidents (K)", max_val=250,
                        fmt=".1f", suffix=" K", accent=WARNING),
        use_container_width=True, config={"displayModeBar": True, "displaylogo": False},
    )
with g4:
    st.plotly_chart(
        gauge_indicator(casualties / 1_000, "Casualties (K)", max_val=300,
                        fmt=".1f", suffix=" K", accent=DANGER),
        use_container_width=True, config={"displayModeBar": True, "displaylogo": False},
    )

st.markdown(
    "<hr style='margin:0.2rem 0 0.4rem 0; border-color:#2A2A2A; border-width:1px'>",
    unsafe_allow_html=True,
)

# ── Overview map ────────────────────────────────────────────────────────────
st.markdown(
    '<p style="color:#555; font-size:0.72rem; text-transform:uppercase; '
    'letter-spacing:0.07em; margin:0 0 0.3rem 0;">LONDON OVERVIEW — STATION RISK MAP</p>',
    unsafe_allow_html=True,
)
m = base_map(zoom=11)
if stations_df is not None and len(stations_df) > 0:
    m = add_station_circles(m, stations_df, name="Stations (risk)")
    m = add_legend(m, "Station Risk Score", {
        "Extreme (≥9)": DANGER,
        "High (7–8)":   ACCENT,
        "Medium (4–6)": WARNING,
        "Low (<4)":     SAFE,
    })
    folium.LayerControl(position="topright", collapsed=True).add_to(m)
st_folium(m, width="100%", height=520, returned_objects=[])

# ── Pipeline & tech stack ────────────────────────────────────────────────────
st.markdown(
    "<hr style='margin:0.5rem 0; border-color:#2A2A2A; border-width:1px'>",
    unsafe_allow_html=True,
)
col_arch, col_stack = st.columns(2)

with col_arch:
    with st.expander("⚙️ Pipeline Architecture", expanded=False):
        st.markdown("""
        ```
        ╔══════════════════════════════════════════════════════════╗
        ║                    DATA SOURCES                          ║
        ║  TFL Cycling API          DfT STATS19 Road Accidents     ║
        ║  cycling.data.tfl.gov.uk  data.dft.gov.uk (CSV)         ║
        ╚══════════════╤═══════════════════╤══════════════════════╝
                       │                   │
                       ▼                   ▼
        ╔══════════════════════════════════════════════════════════╗
        ║          INGESTION  (Python · dlt / requests)            ║
        ║  Local dev  →  DuckDB          Prod  →  Google BigQuery  ║
        ║  ingestion/ingest_tfl_cycling.py                         ║
        ║  ingestion/ingest_uk_accidents.py                        ║
        ╚══════════════════════════════╤═══════════════════════════╝
                                       │
                                       ▼
        ╔══════════════════════════════════════════════════════════╗
        ║           ORCHESTRATION  (Apache Airflow · Docker)             ║
        ║  full_pipeline DAG  ·  backfill DAG                            ║
        ║  dbt_refresh DAG    ·  Scheduled + manual triggers             ║
        ╚══════════════════════════════╤═══════════════════════════╝
                                       │
                                       ▼
        ╔══════════════════════════════════════════════════════════╗
        ║              dbt TRANSFORMATIONS                         ║
        ║  Staging          Intermediate          Marts            ║
        ║  stg_accidents    int_corridor_risk      mart_blackspot   ║
        ║  stg_journeys     int_station_blackspot  mart_corridor    ║
        ║  stg_stations     int_temporal_hourly    mart_temporal    ║
        ║               BigQuery GIS  (ST_DWITHIN, ST_MAKELINE)    ║
        ╚════════════╤══════════════════════════════════╤══════════╝
                     │                                  │
                     ▼                                  ▼
              Folium Maps                         Plotly Charts
              (dark tiles · Leaflet)              (dark theme)
                     └──────────────┬─────────────────┘
                                    ▼
                           Streamlit Dashboard
                       (multi-page · Docker Compose)
        ```
        """)

with col_stack:
    with st.expander("🛠️ Technology Stack", expanded=False):
        stack_rows = [
            ("Language",       "Python 3.11+",          "Core runtime for ingestion, transforms & app"),
            ("Ingestion",      "dlt 0.4+",               "Data load tool · BigQuery & DuckDB adapters"),
            ("Warehouse",      "Google BigQuery",        "Production · raw.* + dbt_* datasets"),
            ("Local Dev",      "DuckDB",                 "In-process analytical DB · zero-config"),
            ("Transforms",     "dbt-bigquery 1.11",      "Staging → Intermediate → Marts"),
            ("Spatial",        "BigQuery GIS",           "ST_MAKELINE · ST_DWITHIN · ST_DISTANCE"),
            ("Orchestration",  "Apache Airflow 2.9",     "Self-hosted · Docker · 3 DAGs (scheduled + manual)"),
            ("Visualisation",  "Folium + Plotly",        "Dark Leaflet tiles + dark Plotly charts"),
            ("App",            "Streamlit 1.35+",        "Multi-page · wide layout · Docker Compose"),
            ("Testing",        "pytest + pytest-cov",    "Unit & integration tests · conftest fixtures"),
            ("Containerise",   "Docker Compose",         "dev / prod profiles · hot-reload dev mode"),
        ]
        for layer, tool, desc in stack_rows:
            st.markdown(
                f'<div style="display:flex;justify-content:space-between;padding:0.3rem 0;'
                f'border-bottom:1px solid #2A2A2A;font-size:0.8rem;">'
                f'<span style="color:#FF9800;font-weight:600;width:110px;">{layer}</span>'
                f'<span style="color:#D8D8D8;flex:1;">{tool}</span>'
                f'<span style="color:#606060;font-size:0.72rem;width:270px;text-align:right;">{desc}</span>'
                f'</div>',
                unsafe_allow_html=True,
            )

st.caption(
    "Data: TFL Open Data  ·  DfT STATS19 (Crown copyright)  ·  BigQuery: kestra-dataengg  "
    "·  Orchestration: Apache Airflow  ·  Local dev: DuckDB  ·  Containerised with Docker Compose"
)

