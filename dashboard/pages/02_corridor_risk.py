"""
Page 2 – Corridor Risk
=======================
Interactive Folium map of station-to-station corridors,
colour-coded by composite risk category, with a ranked table
and a bar chart of top corridors.
"""

import sys
from pathlib import Path

import plotly.express as px
import streamlit as st
from streamlit_folium import st_folium

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from dashboard.utils.data_loader import load_corridor_risk, load_accidents_raw
from dashboard.utils.map_utils import add_corridor_lines, add_heatmap_layer, base_map
from dashboard.utils.theme import (
    inject_arcgis_theme,
    page_tab_nav,
    dark_layout,
    RISK_COLOURS, ACCENT, DANGER, WARNING, SAFE, BLUE,
    PANEL, TEXT, TEXT_DIM, BORDER,
)
import folium

# ── Page config ──────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Corridor Risk | London Cycling Safety",
    page_icon="🟠",
    layout="wide",
    initial_sidebar_state="expanded",
)
inject_arcgis_theme()
page_tab_nav("corridor")

# ── Top bar ──────────────────────────────────────────────────────────────────
st.markdown("""
<div class="top-bar">
  <div>
    <span class="top-bar-title" style="color:#FF9800;">● CYCLING CORRIDOR RISK SCORES</span>
    <span class="top-bar-sub">&nbsp;|&nbsp; composite score = accident weight × ln(journeys)</span>
  </div>
</div>
""", unsafe_allow_html=True)

# ── Sidebar ──────────────────────────────────────────────────────────────────
st.sidebar.markdown("""
<div style="padding:0.3rem 0 0.7rem 0; border-bottom:1px solid #222; margin-bottom:0.7rem;">
  <div style="font-size:1.2rem; text-align:center;">🟠</div>
  <div style="color:#FF9800; font-weight:700; font-size:0.78rem; text-align:center;
              text-transform:uppercase; letter-spacing:0.08em; margin-top:0.2rem;">
    Corridor Risk
  </div>
  <div style="color:#333; font-size:0.66rem; text-align:center;">Composite risk · journey volume</div>
</div>
""", unsafe_allow_html=True)
st.sidebar.markdown(
    '<p style="text-transform:uppercase;letter-spacing:0.07em;font-size:0.72rem;'
    'color:#FF9800;font-weight:700;margin-bottom:0.4rem;">FILTERS</p>',
    unsafe_allow_html=True,
)
top_n          = st.sidebar.slider("Show top N corridors", 10, 100, 50, step=5)
risk_cats      = st.sidebar.multiselect(
    "Risk Category",
    ["Very High", "High", "Medium", "Low"],
    default=["Very High", "High", "Medium", "Low"],
)
min_journeys   = st.sidebar.number_input("Min journey count", min_value=10, value=50, step=10)
show_midpoints = st.sidebar.toggle("Show corridor midpoint markers", value=True)

# ── Load & filter ────────────────────────────────────────────────────────────
with st.spinner(""):
    df           = load_corridor_risk(top_n=top_n)
    accidents_df = load_accidents_raw()

if risk_cats:
    df = df[df["risk_category"].isin(risk_cats)]
df = df[df["journey_count"] >= min_journeys]

# ── KPI strip ────────────────────────────────────────────────────────────────
k1, k2, k3, k4 = st.columns(4)
k1.metric("Corridors Shown",        f"{len(df):,}")
k2.metric("Very High Risk",         f"{df[df['risk_category']=='Very High'].shape[0]:,}")
k3.metric("Total Journeys",         f"{int(df['journey_count'].sum()):,}")
k4.metric("Avg Accidents/Corridor",
          f"{df['corridor_accident_count'].mean():.1f}" if len(df) else "–")

# ── 
# Risk distribution note: top-N corridors by composite score are nearly all
# 'Very High' risk.  Deselect 'Very High' in Risk Category (sidebar) to see
# other categories, or lower the 'Show top N' slider.
if len(df) > 0:
    _dist = df["risk_category"].value_counts()
    if _dist.get("High", 0) + _dist.get("Medium", 0) + _dist.get("Low", 0) == 0:
        st.info(
            "All displayed corridors are Very High risk -- this is expected: "
            "the top corridors by composite score all fall in the worst category. "
            "Deselect **Very High** in the Risk Category filter (left sidebar) "
            "to explore High / Medium / Low corridors.",
        )



# -- Two-column layout -------------------------------------------------------
map_col, side_col = st.columns([3, 2], gap="small")

with map_col:
    m = base_map(zoom=11, tiles="CartoDB positron")
    if len(accidents_df) > 0:
        severe_acc = accidents_df[
            accidents_df["severity_label"].isin(["Fatal", "Serious"])
        ]
        if len(severe_acc) > 0:
            m = add_heatmap_layer(
                m, severe_acc, name="Fatal & Serious Accidents",
                radius=14, min_opacity=0.4,
            )
    with st.spinner(f"Routing {len(df)} corridors along road network …"):
        m = add_corridor_lines(m, df, name="Corridors", show_midpoints=show_midpoints,
                               use_road_routing=True)
    folium.LayerControl(position="topright", collapsed=False).add_to(m)
    st_folium(m, width="100%", height=520, returned_objects=[])
    st.markdown(
        '<div style="color:#888;font-size:0.71rem;margin-top:0.15rem;line-height:1.5;">'
        '&nbsp;▪ Corridors follow the real cycling road network (via OSRM). '
        'Line <b>thickness</b> = risk category (Very High → Low); '
        '<b>colour</b> = risk band (red→orange→yellow→green). '
        'Heatmap shows fatal &amp; serious accident clusters on actual roads.</div>',
        unsafe_allow_html=True,
    )

with side_col:
    # Risk category badge row
    cat_counts = df["risk_category"].value_counts().to_dict() if len(df) else {}
    badge_html = "".join(
        f'<span style="background:{c}22;border:1px solid {c};color:{c};'
        f'font-size:0.7rem;font-weight:700;border-radius:3px;'
        f'padding:2px 8px;margin-right:4px;white-space:nowrap;">'
        f'{cat}&nbsp;({cat_counts.get(cat, 0)})</span>'
        for cat, c in RISK_COLOURS.items()
    )
    st.markdown(
        '<div style="color:#666;font-size:0.72rem;text-transform:uppercase;'
        'letter-spacing:0.06em;border-bottom:1px solid #2A2A2A;padding-bottom:0.3rem;'
        'margin-bottom:0.5rem;">TOP CORRIDORS BY RISK</div>'
        f'<div style="margin-bottom:0.6rem;line-height:2.1;">{badge_html}</div>',
        unsafe_allow_html=True,
    )
    if len(df) > 0:
        top_show = df.nlargest(35, "composite_risk_score").reset_index(drop=True)
        items_html = ""
        for _, row in top_show.iterrows():
            cat      = row.get("risk_category", "Low")
            clr      = RISK_COLOURS.get(cat, "#888")
            label    = str(row.get("corridor_label", ""))[:40]
            journeys = int(row.get("journey_count", 0))
            accidents = int(row.get("corridor_accident_count", 0))
            score    = row.get("composite_risk_score", 0)
            items_html += (
                f'<div class="incident-item">'
                f'<div class="incident-dot" style="background:{clr};"></div>'
                f'<div>'
                f'<div class="incident-title">{label}</div>'
                f'<div class="incident-detail">'
                f'{cat} &nbsp;·&nbsp; Score {score:.1f} &nbsp;·&nbsp; '
                f'{journeys:,} journeys &nbsp;·&nbsp; {accidents} accidents'
                f'</div></div></div>'
            )
        st.markdown(
            f'<div style="max-height:462px;overflow-y:auto;">'
            f'<div class="incident-list">{items_html}</div></div>',
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            '<div style="color:#555;font-size:0.82rem;padding:1rem 0;">'
            'No corridors match current filters.</div>',
            unsafe_allow_html=True,
        )

# ── Scatter + table ──────────────────────────────────────────────────────────
st.markdown("<hr style='margin:0.3rem 0; border-color:#2A2A2A'>", unsafe_allow_html=True)
sc_col, tbl_col = st.columns([2, 3], gap="small")

with sc_col:
    st.markdown(
        '<div style="color:#666;font-size:0.72rem;text-transform:uppercase;'
        'letter-spacing:0.06em;margin-bottom:0.3rem;">JOURNEY VOLUME vs RISK DENSITY</div>',
        unsafe_allow_html=True,
    )
    if len(df) == 0:
        st.info("No corridor data matches current filters.")
    else:
        _size_col = "corridor_accident_count"
        _use_size = df[_size_col].notna().any() and df[_size_col].max() > 0
        fig_scat = px.scatter(
            df, x="journey_count", y="risk_per_km",
            color="risk_category",
            size=_size_col if _use_size else None,
            hover_name="corridor_label",
            hover_data={"length_m": ":.0f", "composite_risk_score": ":.1f"},
            labels={"journey_count": "Journeys", "risk_per_km": "Risk/km",
                    "risk_category": "Risk"},
            color_discrete_map=RISK_COLOURS,
            size_max=20,
        )
        fig_scat.update_layout(
            **dark_layout(
                height=340,
                margin=dict(l=8, r=8, t=10, b=30),
                legend=dict(
                    orientation="h", yanchor="bottom", y=1.01,
                    xanchor="right", x=1,
                    bgcolor="#1B1B1B", bordercolor=BORDER, borderwidth=1,
                ),
            )
        )
        st.plotly_chart(fig_scat, use_container_width=True, config={"displayModeBar": True, "displaylogo": False})

with tbl_col:
    st.markdown(
        '<div style="color:#666;font-size:0.72rem;text-transform:uppercase;'
        'letter-spacing:0.06em;margin-bottom:0.3rem;">CORRIDOR DATA TABLE</div>',
        unsafe_allow_html=True,
    )
    show_cols = [
        "risk_rank", "corridor_label", "risk_category",
        "journey_count", "corridor_accident_count",
        "length_m", "risk_per_km", "composite_risk_score",
    ]
    st.dataframe(
        df[show_cols].rename(columns={
            "risk_rank":               "Rank",
            "corridor_label":          "Corridor",
            "risk_category":           "Risk",
            "journey_count":           "Journeys",
            "corridor_accident_count": "Accidents",
            "length_m":                "Length (m)",
            "risk_per_km":             "Risk/km",
            "composite_risk_score":    "Score",
        }),
        use_container_width=True,
        height=340,
    )

st.caption("Score = risk_weight × ln(journeys+1). Risk/km normalises by corridor length.")
