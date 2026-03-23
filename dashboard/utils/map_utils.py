"""
map_utils.py
============
Folium helper functions shared across dashboard pages.
"""

from __future__ import annotations

import folium
from folium.plugins import HeatMap, MarkerCluster, MiniMap
import pandas as pd

# London centre
LONDON_LAT, LONDON_LON = 51.505, -0.09

TILE_CARTO = "CartoDB dark_matter"
TILE_OSM   = "OpenStreetMap"


def base_map(
    lat: float = LONDON_LAT,
    lon: float = LONDON_LON,
    zoom: int = 11,
    tiles: str = TILE_CARTO,
) -> folium.Map:
    """Create a base Folium map centred on London."""
    m = folium.Map(location=[lat, lon], zoom_start=zoom, tiles=tiles)
    MiniMap(toggle_display=True, position="bottomright").add_to(m)
    # Remove the black dashed bounding-box that browsers draw around the SVG
    # path element when a PolyLine / vector layer is clicked (focus ring).
    m.get_root().html.add_child(
        folium.Element(
            "<style>"
            ".leaflet-interactive:focus { outline: none !important; }"
            "path.leaflet-interactive:focus { outline: none !important; }"
            "</style>"
        )
    )
    return m


def add_heatmap_layer(
    m: folium.Map,
    df: pd.DataFrame,
    lat_col: str = "latitude",
    lon_col: str = "longitude",
    weight_col: str | None = None,
    name: str = "Heatmap",
    min_opacity: float = 0.3,
    radius: int = 12,
) -> folium.Map:
    """Add a HeatMap layer to an existing Folium map."""
    data = df[[lat_col, lon_col]].dropna()
    if weight_col and weight_col in df.columns:
        data = df[[lat_col, lon_col, weight_col]].dropna()
        heat_data = data.values.tolist()
    else:
        heat_data = data.values.tolist()

    HeatMap(
        heat_data,
        name=name,
        min_opacity=min_opacity,
        radius=radius,
        blur=15,
        gradient={
            "0.2": "#313695",
            "0.4": "#74add1",
            "0.6": "#fee090",
            "0.8": "#f46d43",
            "1.0": "#d73027",
        },
    ).add_to(m)
    return m


def add_station_circles(
    m: folium.Map,
    df: pd.DataFrame,
    lat_col: str = "latitude",
    lon_col: str = "longitude",
    colour_col: str = "risk_colour",
    popup_cols: list[str] | None = None,
    radius: int = 6,
    name: str = "Bike Stations",
) -> folium.Map:
    """Add circle markers for each bike station, coloured by risk."""
    layer = folium.FeatureGroup(name=name)
    for _, row in df.iterrows():
        colour = row.get(colour_col, "#3388ff") if colour_col in df.columns else "#3388ff"
        popup_html = ""
        if popup_cols:
            lines = [f"<b>{c.replace('_', ' ').title()}</b>: {row.get(c, '')}" for c in popup_cols if c in row]
            popup_html = "<br>".join(lines)

        folium.CircleMarker(
            location=[row[lat_col], row[lon_col]],
            radius=radius,
            color=colour,
            fill=True,
            fill_color=colour,
            fill_opacity=0.8,
            popup=folium.Popup(popup_html, max_width=280) if popup_html else None,
            tooltip=row.get("station_name", ""),
        ).add_to(layer)
    layer.add_to(m)
    return m


_RISK_WEIGHT:   dict[str, int]   = {"Very High": 9, "High": 6, "Medium": 4, "Low": 2}
_RISK_OPACITY:  dict[str, float] = {"Very High": 0.90, "High": 0.80, "Medium": 0.65, "Low": 0.55}


def add_corridor_lines(
    m: folium.Map,
    df: pd.DataFrame,
    name: str = "Corridors",
    show_midpoints: bool = False,
    use_road_routing: bool = True,
) -> folium.Map:
    """Draw corridor polylines on the map.

    When *use_road_routing* is True (default), each corridor is drawn by
    fetching the actual cycling road path from the OSRM public API so lines
    follow the real road network.  Falls back silently to a straight line when
    the API is unavailable or times out.
    """
    from dashboard.utils.data_loader import fetch_osrm_route

    layer = folium.FeatureGroup(name=name)
    for _, row in df.iterrows():
        colour  = row.get("corridor_colour", "#3388ff")
        cat     = row.get("risk_category", "Medium")
        weight  = _RISK_WEIGHT.get(cat, 4)
        opacity = _RISK_OPACITY.get(cat, 0.65)

        popup_html = (
            f"<b>{row.get('corridor_label','')}</b><br>"
            f"<b>Risk:</b> {cat}<br>"
            f"<b>Score:</b> {row.get('composite_risk_score', 0):.1f}<br>"
            f"<b>Journeys:</b> {int(row.get('journey_count', 0)):,}<br>"
            f"<b>Accidents Nearby:</b> {int(row.get('corridor_accident_count', 0)):,}<br>"
            f"<b>Risk/km:</b> {row.get('risk_per_km', 0):.2f}<br>"
            f"<b>Length:</b> {int(row.get('length_m', 0)):,} m"
        )

        # --- Road-following route via OSRM (cached per corridor pair) --------
        points: list[list[float]] | None = None
        if use_road_routing:
            try:
                points = fetch_osrm_route(
                    float(row["lon_a"]), float(row["lat_a"]),
                    float(row["lon_b"]), float(row["lat_b"]),
                )
            except Exception:
                points = None

        # Fallback: straight line between the two stations
        if not points:
            points = [[row["lat_a"], row["lon_a"]], [row["lat_b"], row["lon_b"]]]

        folium.PolyLine(
            locations=points,
            color=colour,
            weight=weight,
            opacity=opacity,
            popup=folium.Popup(popup_html, max_width=300),
            tooltip=f"■ {cat} – {row.get('corridor_label','')}",
        ).add_to(layer)

        if show_midpoints:
            folium.CircleMarker(
                location=[row["mid_lat"], row["mid_lon"]],
                radius=3,
                color=colour,
                fill=True,
                fill_color=colour,
                fill_opacity=0.85,
            ).add_to(layer)

    layer.add_to(m)
    return m


def add_legend(m: folium.Map, title: str, colour_labels: dict[str, str]) -> folium.Map:
    """Inject a simple HTML legend into the map."""
    items = "".join(
        f'<li><span style="background:{c};width:14px;height:14px;'
        f'display:inline-block;border-radius:50%;margin-right:6px;"></span>{label}</li>'
        for label, c in colour_labels.items()
    )
    legend_html = f"""
    <div style="
        position: fixed;
        bottom: 40px; left: 40px;
        background: #242424;
        border: 1px solid #3A3A3A;
        border-left: 3px solid #FF9800;
        border-radius: 3px;
        padding: 10px 14px;
        z-index: 9999;
        font-family: Arial, sans-serif;
        font-size: 12px;
        color: #E0E0E0;
        box-shadow: 0 2px 8px rgba(0,0,0,0.6);
    ">
        <b style='color:#FF9800;text-transform:uppercase;letter-spacing:.05em;font-size:11px;'>{title}</b><br>
        <ul style="list-style:none;padding:0;margin:6px 0 0 0;">{items}</ul>
    </div>
    """
    m.get_root().html.add_child(folium.Element(legend_html))
    return m
