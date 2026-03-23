"""theme.py — ArcGIS-Style Dark Dashboard Theme
==============================================
Call inject_arcgis_theme() once per page, right after st.set_page_config().

Usage:
    from dashboard.utils.theme import inject_arcgis_theme, dark_layout, gauge_indicator
    inject_arcgis_theme()
"""

from __future__ import annotations

import plotly.graph_objects as go
import streamlit as st

# ── Colour palette ────────────────────────────────────────────────────────────
BG       = "#1B1B1B"   # app / main background
PANEL    = "#242424"   # widget / card background
PANEL2   = "#2D2D2D"   # slightly lighter panel
BORDER   = "#3A3A3A"   # panel borders / grid lines
TEXT     = "#E8E8E8"   # primary text
TEXT_DIM = "#A0A0A0"   # secondary / label text
ACCENT   = "#FF9800"   # orange  – highlighted / selected
DANGER   = "#F44336"   # red     – high risk / fatal
WARNING  = "#FFC107"   # amber   – medium risk
SAFE     = "#4CAF50"   # green   – low risk
BLUE     = "#2196F3"   # blue    – info / journeys

# Risk category colours (matches ArcGIS indicator palette)
RISK_COLOURS: dict[str, str] = {
    "Very High": DANGER,
    "High":      ACCENT,
    "Medium":    WARNING,
    "Low":       SAFE,
}


# ── Plotly dark layout helper ─────────────────────────────────────────────────
def dark_layout(**overrides) -> dict:
    """Return a dark Plotly layout dict ready for fig.update_layout(**dark_layout(...))."""
    base: dict = dict(
        paper_bgcolor=PANEL,
        plot_bgcolor=BG,
        font=dict(color=TEXT, family="Arial"),
        xaxis=dict(
            gridcolor=BORDER,
            gridwidth=0.5,
            zerolinecolor=BORDER,
            tickfont=dict(color=TEXT_DIM),
        ),
        yaxis=dict(
            gridcolor=BORDER,
            gridwidth=0.5,
            zerolinecolor=BORDER,
            tickfont=dict(color=TEXT_DIM),
        ),
        legend=dict(
            bgcolor=PANEL2,
            bordercolor=BORDER,
            borderwidth=1,
            font=dict(color=TEXT),
        ),
        margin=dict(l=8, r=8, t=32, b=8),
        hoverlabel=dict(bgcolor=PANEL2, bordercolor=BORDER, font=dict(color=TEXT)),
        title_font=dict(color=TEXT),
    )
    # Deep-merge overrides so nested dicts (xaxis, yaxis …) blend properly
    for key, val in overrides.items():
        if isinstance(val, dict) and isinstance(base.get(key), dict):
            base[key] = {**base[key], **val}
        else:
            base[key] = val
    return base


# ── Gauge / indicator widget ──────────────────────────────────────────────────
def gauge_indicator(
    value: float | int | str,
    title: str,
    max_val: float = 100,
    fmt: str = ",.0f",
    accent: str = ACCENT,
    suffix: str = "",
) -> go.Figure:
    """Return a Plotly gauge+number figure styled to match ArcGIS dark gauges."""
    num_val = float(value) if isinstance(value, (int, float)) else 0
    fig = go.Figure(go.Indicator(
        mode="gauge+number",
        value=num_val,
        title={"text": title, "font": {"color": TEXT_DIM, "size": 12}},
        number={
            "font": {"color": accent, "size": 26, "family": "Arial"},
            "valueformat": fmt,
            "suffix": suffix,
        },
        gauge={
            "axis": {
                "range": [0, max_val],
                "tickcolor": TEXT_DIM,
                "tickfont": {"color": TEXT_DIM, "size": 8},
                "nticks": 5,
            },
            "bar": {"color": accent, "thickness": 0.28},
            "bgcolor": "#111111",
            "bordercolor": BORDER,
            "borderwidth": 1,
            "steps": [
                {"range": [0,             max_val * 0.4], "color": "#1E2A1E"},
                {"range": [max_val * 0.4, max_val * 0.7], "color": "#2A2A1A"},
                {"range": [max_val * 0.7, max_val],       "color": "#2A1A1A"},
            ],
            "threshold": {
                "line": {"color": DANGER, "width": 2},
                "thickness": 0.75,
                "value": max_val * 0.9,
            },
        },
    ))
    fig.update_layout(
        paper_bgcolor=PANEL,
        font=dict(color=TEXT),
        height=175,
        margin=dict(l=10, r=10, t=40, b=5),
    )
    return fig


# ── Global CSS ────────────────────────────────────────────────────────────────
_CSS = """
<style>
/* ═══════════════════════════════════════════════════════════════
   ArcGIS-Style Dark Dashboard  –  london-cycling-safety
   ═══════════════════════════════════════════════════════════════ */

/* ── App shell ─────────────────────────────────────────────── */
.stApp,
[data-testid="stApp"] {
    background-color: #1B1B1B !important;
}
[data-testid="stMain"] {
    background-color: #1B1B1B !important;
}
.block-container,
[data-testid="block-container"] {
    padding-top:    0.35rem !important;
    padding-bottom: 0.5rem  !important;
    max-width:      100%    !important;
}

/* ── Sidebar ────────────────────────────────────────────────── */
section[data-testid="stSidebar"],
section[data-testid="stSidebar"] > div {
    background-color: #111111 !important;
    border-right: 1px solid #2A2A2A;
}
section[data-testid="stSidebar"] label,
section[data-testid="stSidebar"] p,
section[data-testid="stSidebar"] span {
    color: #B8B8B8 !important;
}
section[data-testid="stSidebar"] h1,
section[data-testid="stSidebar"] h2,
section[data-testid="stSidebar"] h3 {
    color: #E0E0E0 !important;
}
section[data-testid="stSidebar"] hr {
    border-color: #2A2A2A !important;
}

/* ── General text ───────────────────────────────────────────── */
h1, h2, h3, h4, h5, h6 { color: #FFFFFF !important; }
p, li, .stMarkdown       { color: #D0D0D0; }
hr                        { border-color: #2A2A2A !important; }

/* ── Metric cards ───────────────────────────────────────────── */
[data-testid="stMetric"] {
    background-color: #242424 !important;
    border-left: 3px solid #FF9800 !important;
    border-radius: 3px !important;
    padding: 0.55rem 0.85rem !important;
}
[data-testid="stMetricValue"] {
    color: #FF9800 !important;
    font-size: 1.35rem !important;
    font-weight: 700 !important;
}
[data-testid="stMetricLabel"] {
    color: #808080 !important;
    font-size: 0.75rem !important;
    text-transform: uppercase;
    letter-spacing: 0.05em;
}
[data-testid="stMetricDelta"] { color: #4CAF50 !important; }

/* ── Expander ───────────────────────────────────────────────── */
[data-testid="stExpander"] {
    background-color: #242424 !important;
    border: 1px solid #333 !important;
}
[data-testid="stExpander"] summary {
    color: #C0C0C0 !important;
}

/* ── Widget labels ──────────────────────────────────────────── */
[data-testid="stWidgetLabel"] { color: #909090 !important; }

/* ── Number input ───────────────────────────────────────────── */
[data-testid="stNumberInput"] input {
    background-color: #1B1B1B !important;
    color: #E0E0E0 !important;
    border-color: #3A3A3A !important;
}

/* ── Spinner ────────────────────────────────────────────────── */
[data-testid="stSpinner"] { color: #FF9800 !important; }

/* ── Caption / footer ───────────────────────────────────────── */
[data-testid="stCaptionContainer"] {
    color: #555 !important;
    font-size: 0.72rem;
}

/* ── Top navigation header bar ──────────────────────────────── */
.top-bar {
    background: #111111;
    border-bottom: 2px solid #FF9800;
    padding: 0.35rem 0.5rem 0.35rem 0.5rem;
    margin: -0.35rem -1rem 0.55rem -1rem;
    display: flex;
    align-items: center;
    justify-content: space-between;
}
.top-bar-title {
    font-size: 0.95rem;
    font-weight: 700;
    color: #FFFFFF;
    letter-spacing: 0.06em;
    text-transform: uppercase;
}
.top-bar-sub {
    font-size: 0.72rem;
    color: #FF9800;
}

/* ── Panel utility ──────────────────────────────────────────── */
.arcgis-panel {
    background-color: #242424;
    border: 1px solid #333;
    border-left: 3px solid #FF9800;
    border-radius: 2px;
    padding: 0.7rem 0.9rem;
    margin-bottom: 0.4rem;
}

/* ── Incident / violation list (left-panel ArcGIS style) ────── */
.incident-list { list-style: none; padding: 0; margin: 0; }
.incident-item {
    display: flex;
    align-items: flex-start;
    padding: 0.45rem 0.5rem;
    border-bottom: 1px solid #242424;
    font-size: 0.82rem;
    background: #1E1E1E;
}
.incident-item:nth-child(odd)  { background: #1E1E1E; }
.incident-item:nth-child(even) { background: #222222; }
.incident-dot {
    width: 9px; height: 9px;
    border-radius: 50%;
    margin-top: 4px;
    margin-right: 8px;
    flex-shrink: 0;
}
.incident-title  { color: #FF9800; font-weight: 600; font-size: 0.82rem; }
.incident-detail { color: #787878; font-size: 0.75rem; margin-top: 1px; }

/* ── Hide Streamlit chrome ──────────────────────────────────── */
[data-testid="stToolbar"], footer { display: none !important; }

/* ── Dataframe dark tint ────────────────────────────────────── */
[data-testid="stDataFrame"] thead tr th {
    background-color: #242424 !important;
    color: #A0A0A0 !important;
}

/* ── Tab nav bar ─────────────────────────────────────────────── */
.tab-nav {
    display: flex;
    gap: 0;
    border-bottom: 2px solid #2A2A2A;
    margin: 0.1rem 0 0.55rem 0;
    padding: 0;
}
.tab-nav a, .tab-nav a:visited {
    color: #606060;
    text-decoration: none;
    font-size: 0.78rem;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.06em;
    padding: 0.45rem 1.1rem;
    border-bottom: 2px solid transparent;
    margin-bottom: -2px;
    transition: color 0.15s, border-color 0.15s;
}
.tab-nav a:hover { color: #D0D0D0; border-bottom-color: #555; }
.tab-nav a.active-tab { color: #FF9800 !important; border-bottom-color: #FF9800 !important; }
.tab-nav a.home-tab { color: #3A3A3A; font-size: 1rem; padding: 0.35rem 0.75rem; }
.tab-nav a.home-tab:hover { color: #C0C0C0; }

/* ── Sidebar widget accent overrides (multiselect tags, slider, toggle) ─── */
/* Multiselect selected-item tags */
[data-baseweb="tag"] {
    background-color: #1A3A5C !important;
    border: 1px solid #2E6DA4 !important;
    border-radius: 3px !important;
}
[data-baseweb="tag"] span {
    color: #90CAF9 !important;
}
/* Tag close button */
[data-baseweb="tag"] [role="button"] {
    color: #64B5F6 !important;
}
/* Slider pill/track active fill - uses primaryColor so this is a safety pin */
section[data-testid="stSidebar"] [data-testid="stSlider"] input[type="range"]::-webkit-slider-thumb {
    background: #42A5F5 !important;
}
/* Ensure slider value label is visible */
section[data-testid="stSidebar"] [data-testid="stSlider"] [data-testid="stTickBarMin"],
section[data-testid="stSidebar"] [data-testid="stSlider"] [data-testid="stTickBarMax"] {
    color: #7B9BB8 !important;
}
</style>
"""


def inject_arcgis_theme() -> None:
    """Inject the ArcGIS dark CSS into the current Streamlit page."""
    st.markdown(_CSS, unsafe_allow_html=True)


def page_tab_nav(active: str) -> None:
    """Render a tab bar with Home + 3 page links.

    active: one of "home", "blackspot", "corridor", "temporal"
    """
    tabs = [
        ("home",      "🏠",                 "app",                    "Home"),
        ("blackspot", "🔴 Blackspot Map",    "01_blackspot_map",       "01_blackspot_map"),
        ("corridor",  "🟠 Corridor Risk",    "02_corridor_risk",       "02_corridor_risk"),
        ("temporal",  "🔵 Temporal Patterns","03_temporal_patterns",   "03_temporal_patterns"),
    ]
    parts = []
    for key, label, page_file, _ in tabs:
        css_cls = "home-tab" if key == "home" else ""
        if key == active:
            css_cls += " active-tab"
        css_cls = css_cls.strip()
        href = f"/{page_file}" if key != "home" else "/"
        parts.append(
            f'<a class="{css_cls}" href="{href}" target="_self">{label}</a>'
        )
    st.markdown(
        f'<nav class="tab-nav">{"".join(parts)}</nav>',
        unsafe_allow_html=True,
    )
