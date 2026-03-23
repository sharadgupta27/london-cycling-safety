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
        'letter-spacing:0.09em; margin-bottom:0.45rem; font-weight:700;">HOW TO USE</p>',
        unsafe_allow_html=True,
    )
    st.markdown("""
    <div style="font-size:0.74rem; color:#666; line-height:1.85;">
      <span style="color:#bbb;">1.</span>&nbsp; Click the page links above to navigate<br>
      <span style="color:#bbb;">2.</span>&nbsp; Each page has <strong style="color:#aaa">sidebar filters</strong><br>
      <span style="color:#bbb;">3.</span>&nbsp; Maps are <strong style="color:#aaa">interactive</strong> – zoom &amp; click<br>
      <span style="color:#bbb;">4.</span>&nbsp; Charts show <strong style="color:#aaa">tooltips</strong> on hover<br>
      <span style="color:#bbb;">5.</span>&nbsp; Use "Open →" buttons below to jump to pages
    </div>
    """, unsafe_allow_html=True)

    st.markdown('<hr style="border-color:#222; margin:0.75rem 0;">', unsafe_allow_html=True)
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

# ── Overview map  +  navigation panels ──────────────────────────────────────
map_col, nav_col = st.columns([3, 2], gap="medium")

with map_col:
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
    st_folium(m, width="100%", height=420, returned_objects=[])

with nav_col:
    st.markdown(
        '<p style="color:#555; font-size:0.72rem; text-transform:uppercase; '
        'letter-spacing:0.07em; margin:0 0 0.4rem 0;">DASHBOARD VIEWS</p>',
        unsafe_allow_html=True,
    )
    pages_info = [
        (
            "#F44336", "🔴 ACCIDENT BLACKSPOT MAP",
            "Interactive heatmap overlaying accident density on 800+ TFL Santander docking "
            "stations. Each station is colour-coded by weighted risk score (10×fatal + 3×serious + 1×slight).",
            "pages/01_blackspot_map.py",
        ),
        (
            "#FF9800", "🟠 CORRIDOR RISK SCORES",
            "90K+ station-to-station corridors ranked by composite risk = accident weight × ln(journeys). "
            "Dark map, filterable by risk category and journey volume.",
            "pages/02_corridor_risk.py",
        ),
        (
            "#2196F3", "🔵 TEMPORAL PATTERNS",
            "Rush-hour vs weekend distribution, hour-of-day heatmap by weekday, monthly "
            "seasonality and year-over-year accident trends.",
            "pages/03_temporal_patterns.py",
        ),
    ]
    for colour, title, desc, page_path in pages_info:
        st.markdown(f"""
        <div class="arcgis-panel" style="border-left-color:{colour}; margin-bottom:0.35rem;">
          <div style="color:{colour}; font-size:0.78rem; font-weight:700;
                      text-transform:uppercase; letter-spacing:0.05em; margin-bottom:0.28rem;">
            {title}
          </div>
          <div style="color:#909090; font-size:0.74rem; line-height:1.5;">
            {desc}
          </div>
        </div>
        """, unsafe_allow_html=True)
        st.page_link(page_path, label=f"Open → {title.split(' ', 1)[1].title()}", use_container_width=True)

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
        TFL Cycling Data  ──────────────────────────────────────┐
        (cycling.data.tfl.gov.uk)                               │
                                                                ▼
        UK STATS19 Road Accidents  ──────→  [dlt → BigQuery raw.*]
        (data.dft.gov.uk)                                       │
                                                                ▼
                                              [dbt-bigquery models]
                                           staging → intermediate → marts
                                           int_corridor_risk (BQ GIS)
                                           mart_corridor_risk_score
                                           mart_blackspot_stations
                                                                │
                                     ┌──────────────────────────┤
                                     ▼                          ▼
                              Folium Maps                 Plotly Charts
                              (dark tiles)                (dark theme)
                                     └──────────────────────────┘
                                                                │
                                                       Streamlit App
        ```
        """)

with col_stack:
    with st.expander("🛠️ Technology Stack", expanded=False):
        stack_rows = [
            ("Ingestion",     "dlt",                "BigQuery write_disposition=replace"),
            ("Warehouse",     "Google BigQuery",    "raw + dbt_ datasets"),
            ("Transforms",    "dbt-bigquery 1.11",  "Staging → Intermediate → Marts"),
            ("Spatial",       "BigQuery GIS",       "ST_MAKELINE, ST_DWITHIN, ST_DISTANCE"),
            ("Visualisation", "Folium + Plotly",    "Dark map tiles + dark Plotly charts"),
            ("App",           "Streamlit 1.35+",    "Multi-page, wide layout"),
        ]
        for layer, tool, desc in stack_rows:
            st.markdown(
                f'<div style="display:flex;justify-content:space-between;padding:0.3rem 0;'
                f'border-bottom:1px solid #2A2A2A;font-size:0.8rem;">'
                f'<span style="color:#FF9800;font-weight:600;width:110px;">{layer}</span>'
                f'<span style="color:#D8D8D8;flex:1;">{tool}</span>'
                f'<span style="color:#606060;font-size:0.72rem;width:250px;text-align:right;">{desc}</span>'
                f'</div>',
                unsafe_allow_html=True,
            )

st.caption(
    "Data: TFL Open Data  ·  DfT STATS19 (Crown copyright)  ·  BigQuery: kestra-dataengg"
)

