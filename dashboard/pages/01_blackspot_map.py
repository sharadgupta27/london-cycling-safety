"""
Page 1 – Blackspot Map
=======================
Interactive Folium map showing:
  • Accident heatmap layer
  • Bike station circles coloured by risk score
  • Filter controls in sidebar
"""

import sys
from pathlib import Path

import folium
import pandas as pd
import plotly.express as px
import streamlit as st
from streamlit_folium import st_folium

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from dashboard.utils.data_loader import load_accidents_raw, load_blackspot_stations
from dashboard.utils.map_utils import (
    add_heatmap_layer,
    add_legend,
    add_station_circles,
    base_map,
)
from dashboard.utils.theme import (
    inject_arcgis_theme,
    page_tab_nav,
    dark_layout,
    ACCENT, DANGER, WARNING, SAFE, PANEL, TEXT, TEXT_DIM, BORDER,
)

# ── Page config ──────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Blackspot Map | London Cycling Safety",
    page_icon="🔴",
    layout="wide",
    initial_sidebar_state="expanded",
)
inject_arcgis_theme()
page_tab_nav("blackspot")

# ── Top bar ──────────────────────────────────────────────────────────────────
st.markdown("""
<div class="top-bar">
  <div>
    <span class="top-bar-title" style="color:#F44336;">● ACCIDENT BLACKSPOT MAP</span>
    <span class="top-bar-sub">&nbsp;|&nbsp; TFL stations scored by accident density</span>
  </div>
</div>
""", unsafe_allow_html=True)

# ── Sidebar ──────────────────────────────────────────────────────────────────
st.sidebar.markdown("""
<div style="padding:0.3rem 0 0.7rem 0; border-bottom:1px solid #222; margin-bottom:0.7rem;">
  <div style="font-size:1.2rem; text-align:center;">🔴</div>
  <div style="color:#F44336; font-weight:700; font-size:0.78rem; text-align:center;
              text-transform:uppercase; letter-spacing:0.08em; margin-top:0.2rem;">
    Blackspot Map
  </div>
  <div style="color:#333; font-size:0.66rem; text-align:center;">Station risk scores · heatmap</div>
</div>
""", unsafe_allow_html=True)
st.sidebar.page_link("app.py", label="🏠 Home", use_container_width=True)
st.sidebar.markdown("<hr style='border-color:#222; margin:0.4rem 0;'>", unsafe_allow_html=True)
st.sidebar.markdown(
    '<p style="text-transform:uppercase;letter-spacing:0.07em;font-size:0.72rem;'
    'color:#FF9800;font-weight:700;margin-bottom:0.4rem;">FILTERS</p>',
    unsafe_allow_html=True,
)

severity_filter = st.sidebar.multiselect(
    "Accident Severity",
    options=["Fatal", "Serious", "Slight"],
    default=["Fatal", "Serious", "Slight"],
)
show_heatmap    = st.sidebar.toggle("Show Accident Heatmap",             value=True)
show_stations   = st.sidebar.toggle("Show Bike Station Markers",         value=True)
blackspots_only = st.sidebar.toggle("High-Risk Stations Only (top 10%)", value=False)
risk_threshold  = st.sidebar.slider("Min Weighted Risk Score", 0, 500, 0, step=10)

# ── Load & filter ────────────────────────────────────────────────────────────
with st.spinner(""):
    stations_df  = load_blackspot_stations()
    accidents_df = load_accidents_raw()

if severity_filter:
    accidents_df = accidents_df[accidents_df["severity_label"].isin(severity_filter)]
if blackspots_only:
    stations_df = stations_df[stations_df["is_blackspot"] == True]
stations_df = stations_df[stations_df["weighted_risk_score"] >= risk_threshold]

# ── KPI strip ────────────────────────────────────────────────────────────────
k1, k2, k3, k4 = st.columns(4)
k1.metric("Docking Stations",   f"{len(stations_df):,}")
k2.metric("Accidents in View",  f"{len(accidents_df):,}")
k3.metric("Blackspot Stations", f"{stations_df[stations_df['is_blackspot']==True].shape[0]:,}")
k4.metric("Max Risk Score",
          f"{int(stations_df['weighted_risk_score'].max()):,}" if len(stations_df) else "–")

# ── Two-column layout ────────────────────────────────────────────────────────
map_col, side_col = st.columns([3, 2], gap="small")

with map_col:
    m = base_map()
    if show_heatmap and len(accidents_df) > 0:
        sw = {"Fatal": 10, "Serious": 3, "Slight": 1}
        accidents_df["heat_weight"] = accidents_df["severity_label"].map(sw).fillna(1)
        m = add_heatmap_layer(
            m, accidents_df,
            lat_col="latitude", lon_col="longitude",
            weight_col="heat_weight", name="Accident Heatmap", radius=14,
        )
    if show_stations and len(stations_df) > 0:
        m = add_station_circles(
            m, stations_df, colour_col="risk_colour",
            popup_cols=[
                "station_name", "weighted_risk_score", "nearby_accident_count",
                "nearby_fatal_count", "nearby_serious_count", "total_trips",
                "risk_per_1000_trips", "risk_decile",
            ],
            radius=7, name="Bike Stations",
        )
    m = add_legend(m, "Risk Decile (stations)", {
        "Decile 10 – Highest": "#d73027",
        "Decile 7–9":          "#fdae61",
        "Decile 4–6":          "#ffffbf",
        "Decile 1–3 – Lowest": "#006837",
    })
    folium.LayerControl(position="topright", collapsed=False).add_to(m)
    st_folium(m, width="100%", height=520, returned_objects=[])

with side_col:
    st.markdown(
        '<div style="color:#666;font-size:0.72rem;text-transform:uppercase;'
        'letter-spacing:0.06em;border-bottom:1px solid #2A2A2A;padding-bottom:0.3rem;'
        'margin-bottom:0.3rem;">TOP RISK STATIONS</div>',
        unsafe_allow_html=True,
    )
    top10 = stations_df.nlargest(10, "weighted_risk_score").reset_index(drop=True)
    if len(top10):
        items_html = ""
        for _, row in top10.iterrows():
            decile = int(row.get("risk_decile", 5))
            clr = "#F44336" if decile >= 9 else ("#FF9800" if decile >= 7 else "#FFC107")
            items_html += (
                f'<div class="incident-item">'
                f'<div class="incident-dot" style="background:{clr};"></div>'
                f'<div><div class="incident-title">{str(row["station_name"])[:38]}</div>'
                f'<div class="incident-detail">'
                f'Score: {int(row["weighted_risk_score"]):,} &nbsp;·&nbsp; '
                f'Accidents: {int(row.get("nearby_accident_count", 0))} &nbsp;·&nbsp; '
                f'Decile {decile}</div></div></div>'
            )
        st.markdown(f'<div class="incident-list">{items_html}</div>', unsafe_allow_html=True)
    else:
        st.markdown(
            '<div style="color:#555;font-size:0.82rem;padding:0.8rem 0;">'
            'No stations match current filters.</div>',
            unsafe_allow_html=True,
        )

    # ── Risk score histogram ──────────────────────────────────────────────
    if len(stations_df) > 0:
        fig_hist = px.histogram(
            stations_df, x="weighted_risk_score", color="risk_decile",
            nbins=40,
            labels={"weighted_risk_score": "Risk Score", "risk_decile": "Decile"},
            color_discrete_sequence=px.colors.diverging.RdYlGn_r,
        )
        fig_hist.update_layout(
            **dark_layout(
                showlegend=False,
                title_text="Risk Score Distribution",
                title_font_size=11,
                height=230,
                margin=dict(l=4, r=4, t=28, b=28),
            )
        )
        st.plotly_chart(fig_hist, use_container_width=True, config={"displayModeBar": True, "displaylogo": False})

st.caption("Risk = 10×fatal + 3×serious + 1×slight accidents within search radius")
