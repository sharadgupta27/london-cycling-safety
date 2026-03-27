"""
Page 3 – Temporal Patterns
============================
Plotly-based charts exploring:
  • Hour-of-day accident distribution (weekday vs weekend)
  • Rush-hour vs other time periods
  • Monthly seasonality trend
  • Year-over-year comparison
"""

import sys
from pathlib import Path

import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import pandas as pd
import streamlit as st

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from dashboard.utils.data_loader import (
    load_temporal_hourly,
    load_temporal_period,
    load_monthly_trend,
)
from dashboard.utils.theme import (
    inject_arcgis_theme,
    page_tab_nav,
    dark_layout,
    ACCENT, DANGER, WARNING, SAFE, BLUE,
    PANEL, TEXT, TEXT_DIM, BORDER,
)

# ── Page config ──────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Temporal Patterns | London Cycling Safety",
    page_icon="🕐",
    layout="wide",
    initial_sidebar_state="expanded",
)
inject_arcgis_theme()
page_tab_nav("temporal")

# ── Top bar ──────────────────────────────────────────────────────────────────
st.markdown("""
<div class="top-bar">
  <div>
    <span class="top-bar-title" style="color:#2196F3;">● TEMPORAL SAFETY PATTERNS</span>
    <span class="top-bar-sub">&nbsp;|&nbsp; Rush hours · Weekends · Seasonality</span>
  </div>
</div>
""", unsafe_allow_html=True)

# ── Sidebar ──────────────────────────────────────────────────────────────────
st.sidebar.markdown("""
<div style="padding:0.3rem 0 0.7rem 0; border-bottom:1px solid #222; margin-bottom:0.7rem;">
  <div style="font-size:1.2rem; text-align:center;">🔵</div>
  <div style="color:#2196F3; font-weight:700; font-size:0.78rem; text-align:center;
              text-transform:uppercase; letter-spacing:0.08em; margin-top:0.2rem;">
    Temporal Patterns
  </div>
  <div style="color:#333; font-size:0.66rem; text-align:center;">Rush hours · seasonality · trends</div>
</div>
""", unsafe_allow_html=True)
st.sidebar.markdown(
    '<p style="text-transform:uppercase;letter-spacing:0.07em;font-size:0.72rem;'
    'color:#FF9800;font-weight:700;margin-bottom:0.4rem;">FILTERS</p>',
    unsafe_allow_html=True,
)

with st.spinner(""):
    hourly_df  = load_temporal_hourly()
    period_df  = load_temporal_period()
    monthly_df = load_monthly_trend()

available_years = sorted(
    hourly_df["year"].dropna().unique().astype(int).tolist()
) if len(hourly_df) else []
selected_years = st.sidebar.multiselect("Years", available_years, default=available_years)

if selected_years:
    hourly_df  = hourly_df[hourly_df["year"].isin(selected_years)]
    period_df  = period_df[period_df["year"].isin(selected_years)]
    monthly_df = monthly_df[monthly_df["year"].isin(selected_years)]

# ── KPI strip ────────────────────────────────────────────────────────────────
total_accidents   = hourly_df["accident_count"].sum()
rush_accidents    = hourly_df[
    hourly_df["time_of_day_period"].isin(["AM Rush (07-09)", "PM Rush (17-19)"])
]["accident_count"].sum()
night_accidents   = hourly_df[
    hourly_df["time_of_day_period"] == "Night (00-06)"
]["accident_count"].sum()
weekend_accidents = hourly_df[hourly_df["day_type"] == "Weekend"]["accident_count"].sum()
weekday_accidents = hourly_df[hourly_df["day_type"] == "Weekday"]["accident_count"].sum()

k1, k2, k3, k4 = st.columns(4)
k1.metric("Rush Hour Accidents",
          f"{int(rush_accidents):,}",
          f"{rush_accidents/total_accidents*100:.1f}% of total" if total_accidents else "")
k2.metric("Weekend Accidents",
          f"{int(weekend_accidents):,}",
          f"{weekend_accidents/total_accidents*100:.1f}% of total" if total_accidents else "")
k3.metric("Weekday Accidents",
          f"{int(weekday_accidents):,}",
          f"{weekday_accidents/total_accidents*100:.1f}% of total" if total_accidents else "")
k4.metric("Night (00–06) Accidents",
          f"{int(night_accidents):,}",
          f"{night_accidents/total_accidents*100:.1f}% of total" if total_accidents else "")

st.markdown("<hr style='margin:0.3rem 0; border-color:#2A2A2A'>", unsafe_allow_html=True)

# ── 2×2 chart grid ───────────────────────────────────────────────────────────
row1_left, row1_right = st.columns(2, gap="small")

# ── Chart 1: Hour-of-day line ─────────────────────────────────────────────────
with row1_left:
    st.markdown(
        '<div style="color:#666;font-size:0.72rem;text-transform:uppercase;'
        'letter-spacing:0.06em;margin-bottom:0.25rem;">ACCIDENTS BY HOUR — WEEKDAY vs WEEKEND</div>',
        unsafe_allow_html=True,
    )
    if len(hourly_df) > 0:
        hp = (
            hourly_df.groupby(["dimension", "day_type"])["accident_count"]
            .sum().reset_index()
        )
        hp["hour"] = pd.to_numeric(hp["dimension"], errors="coerce")
        hp = hp.dropna(subset=["hour"]).sort_values("hour")
        fig_h = px.line(
            hp, x="hour", y="accident_count", color="day_type", markers=True,
            color_discrete_map={"Weekday": BLUE, "Weekend": DANGER},
            labels={"hour": "Hour", "accident_count": "Accidents", "day_type": ""},
        )
        for s, e in [(7, 9), (17, 19)]:
            fig_h.add_vrect(x0=s, x1=e + 1, fillcolor=ACCENT, opacity=0.1, line_width=0)
        fig_h.update_layout(
            **dark_layout(
                height=330,
                xaxis=dict(tickmode="linear", tick0=0, dtick=2,
                           gridcolor=BORDER, tickfont=dict(color=TEXT_DIM)),
                legend=dict(orientation="h", yanchor="bottom", y=1.01,
                            xanchor="right", x=1,
                            bgcolor="#1B1B1B", bordercolor=BORDER, borderwidth=1),
                margin=dict(l=8, r=8, t=10, b=30),
            )
        )
        st.plotly_chart(fig_h, use_container_width=True, config={"displayModeBar": True, "displaylogo": False})
    else:
        st.info("No hourly data available.")

# ── Chart 2: Time period comparison ──────────────────────────────────────────
with row1_right:
    st.markdown(
        '<div style="color:#666;font-size:0.72rem;text-transform:uppercase;'
        'letter-spacing:0.06em;margin-bottom:0.25rem;">ACCIDENTS BY TIME PERIOD</div>',
        unsafe_allow_html=True,
    )
    period_agg = None
    if len(period_df) > 0:
        period_agg = (
            period_df.groupby(["dimension", "day_type"])
            [["accident_count", "fatal_count", "serious_count"]]
            .sum().reset_index().rename(columns={"dimension": "time_period"})
        )
        period_order = [
            "AM Rush (07-09)", "Midday (10-16)", "PM Rush (17-19)",
            "Evening (20-23)", "Night (00-06)",
        ]
        period_agg["time_period"] = pd.Categorical(
            period_agg["time_period"], categories=period_order, ordered=True
        )
        period_agg = period_agg.sort_values("time_period")
        fig_p = px.bar(
            period_agg, x="time_period", y="accident_count", color="day_type",
            barmode="group",
            color_discrete_map={"Weekday": BLUE, "Weekend": DANGER},
            labels={"time_period": "", "accident_count": "Accidents", "day_type": ""},
        )
        fig_p.update_layout(
            **dark_layout(
                height=330,
                xaxis=dict(tickfont=dict(color=TEXT_DIM, size=9)),
                legend=dict(orientation="h", yanchor="bottom", y=1.01,
                            xanchor="right", x=1,
                            bgcolor="#1B1B1B", bordercolor=BORDER, borderwidth=1),
                margin=dict(l=8, r=8, t=10, b=30),
            )
        )
        st.plotly_chart(fig_p, use_container_width=True, config={"displayModeBar": True, "displaylogo": False})
    else:
        st.info("No period data available.")

row2_left, row2_right = st.columns(2, gap="small")

# ── Chart 3: Fatal & serious by time period ───────────────────────────────────
with row2_left:
    st.markdown(
        '<div style="color:#666;font-size:0.72rem;text-transform:uppercase;'
        'letter-spacing:0.06em;margin-bottom:0.25rem;">FATAL & SERIOUS BY TIME PERIOD</div>',
        unsafe_allow_html=True,
    )
    if period_agg is not None and len(period_agg) > 0:
        fig_sv = px.bar(
            period_agg, x="time_period", y=["fatal_count", "serious_count"],
            labels={"value": "Count", "variable": "Severity", "time_period": ""},
            color_discrete_map={"fatal_count": DANGER, "serious_count": WARNING},
            barmode="stack",
        )
        fig_sv.update_layout(
            **dark_layout(
                height=330,
                xaxis=dict(tickfont=dict(color=TEXT_DIM, size=9)),
                legend=dict(orientation="h", yanchor="bottom", y=1.01,
                            xanchor="right", x=1,
                            bgcolor="#1B1B1B", bordercolor=BORDER, borderwidth=1),
                margin=dict(l=8, r=8, t=10, b=30),
            )
        )
        st.plotly_chart(fig_sv, use_container_width=True, config={"displayModeBar": True, "displaylogo": False})
    else:
        st.info("No severity data available.")

# ── Chart 4: Monthly trend ────────────────────────────────────────────────────
with row2_right:
    st.markdown(
        '<div style="color:#666;font-size:0.72rem;text-transform:uppercase;'
        'letter-spacing:0.06em;margin-bottom:0.25rem;">MONTHLY ACCIDENT TREND</div>',
        unsafe_allow_html=True,
    )
    if len(monthly_df) > 0:
        month_agg = (
            monthly_df.groupby(["dimension", "year"])["accident_count"]
            .sum().reset_index().rename(columns={"dimension": "year_month"})
            .sort_values("year_month")
        )
        fig_m = px.line(
            month_agg, x="year_month", y="accident_count", color="year",
            markers=True,
            color_discrete_sequence=px.colors.qualitative.Pastel,
            labels={"year_month": "Month", "accident_count": "Accidents", "year": "Year"},
        )
        fig_m.update_layout(
            **dark_layout(
                height=330,
                xaxis=dict(tickangle=-45, tickfont=dict(color=TEXT_DIM, size=8)),
                legend=dict(orientation="h", yanchor="bottom", y=1.01,
                            xanchor="right", x=1,
                            bgcolor="#1B1B1B", bordercolor=BORDER, borderwidth=1),
                margin=dict(l=8, r=8, t=10, b=50),
            )
        )
        st.plotly_chart(fig_m, use_container_width=True, config={"displayModeBar": True, "displaylogo": False})
    else:
        st.info("No monthly data available.")

# ── Hour × weekday heatmap ────────────────────────────────────────────────────
st.markdown("<hr style='margin:0.3rem 0; border-color:#2A2A2A'>", unsafe_allow_html=True)
st.markdown(
    '<div style="color:#666;font-size:0.72rem;text-transform:uppercase;'
    'letter-spacing:0.06em;margin-bottom:0.25rem;">ACCIDENT DENSITY — HOUR × DAY OF WEEK</div>',
    unsafe_allow_html=True,
)
WEEKDAY_ORDER = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
if len(hourly_df) > 0:
    try:
        from dashboard.utils.data_loader import load_accidents_raw
        acc_raw = load_accidents_raw()
        acc_raw["hour_of_day"] = pd.to_numeric(acc_raw["hour_of_day"], errors="coerce")
        if selected_years:
            acc_raw = acc_raw[acc_raw["year"].isin(selected_years)]
        day_map = {2: "Monday", 3: "Tuesday", 4: "Wednesday", 5: "Thursday",
                   6: "Friday", 7: "Saturday", 1: "Sunday"}
        acc_hm = (
            acc_raw
            .assign(weekday_name=acc_raw.get(
                "day_of_week", pd.Series(dtype=float)).map(day_map))
            .groupby(["hour_of_day", "weekday_name"])
            .size().reset_index(name="count")
        )
        pivot = acc_hm.pivot(
            index="weekday_name", columns="hour_of_day", values="count"
        ).fillna(0)
        pivot = pivot.reindex([d for d in WEEKDAY_ORDER if d in pivot.index])
        fig_hm = px.imshow(
            pivot,
            color_continuous_scale="YlOrRd",
            labels=dict(x="Hour of Day", y="", color="Accidents"),
            aspect="auto",
        )
        fig_hm.update_layout(
            **dark_layout(
                height=280,
                coloraxis_colorbar=dict(
                    title=dict(text="Accidents", font=dict(color=TEXT_DIM)),
                    tickfont=dict(color=TEXT_DIM),
                ),
                margin=dict(l=80, r=8, t=10, b=30),
            )
        )
        st.plotly_chart(fig_hm, use_container_width=True, config={"displayModeBar": True, "displaylogo": False})
    except Exception:
        pass

# ── Key insights ──────────────────────────────────────────────────────────────
st.markdown("<hr style='margin:0.3rem 0; border-color:#2A2A2A'>", unsafe_allow_html=True)
st.markdown(
    '<div style="color:#666;font-size:0.72rem;text-transform:uppercase;'
    'letter-spacing:0.06em;margin-bottom:0.3rem;">KEY INSIGHTS</div>',
    unsafe_allow_html=True,
)
ins_cols = st.columns(4)
insights = [
    (ACCENT,   "Rush Hours (07–09 & 17–19)",
     "Elevated accident rates on weekdays, coinciding with peak cycling volumes."),
    (WARNING,  "Friday Evenings",
     "Consistently higher rates than other weekday evenings — likely social cycling trips."),
    (BLUE,     "Winter Months (Nov–Jan)",
     "Dip in absolute count but higher severity rate per journey."),
    (DANGER,   "Post-Midnight Weekends",
     "Disproportionately high severity ratios despite lower total volumes."),
]
for col, (clr, title, desc) in zip(ins_cols, insights):
    with col:
        st.markdown(
            f'<div class="arcgis-panel" style="border-left:3px solid {clr};">'
            f'<div style="color:{clr};font-size:0.75rem;font-weight:700;'
            f'text-transform:uppercase;margin-bottom:0.3rem;">{title}</div>'
            f'<div style="color:#A0A0A0;font-size:0.8rem;line-height:1.4;">{desc}</div>'
            f'</div>',
            unsafe_allow_html=True,
        )

st.caption("Source: DfT STATS19 road safety data, filtered to Greater London bounding box.")
