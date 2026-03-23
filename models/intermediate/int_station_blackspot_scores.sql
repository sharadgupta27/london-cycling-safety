-- intermediate/int_station_blackspot_scores.sql
--
-- DuckDB  (dev):  joins spatial_layer.station_blackspot_scores computed by
--                 spatial_transforms.py
-- BigQuery (prod): computes accident proximity inline using BigQuery GIS
--                  (ST_GEOGPOINT / ST_DISTANCE) — no Python transform step needed.

{{
  config(materialized='table', schema='intermediate')
}}

-- ── journey volumes per station (identical for both targets) ────────────────
-- This CTE is referenced at the bottom of both branches.

{% if target.type == 'bigquery' %}

-- ════════════════════════════════════════════════════════════════════════════
-- BIGQUERY BRANCH  –  spatial join computed via BigQuery GIS
-- ════════════════════════════════════════════════════════════════════════════

WITH accidents_geo AS (
    SELECT
        accident_index,
        accident_severity,
        CAST(number_of_casualties AS INT64) AS number_of_casualties,
        ST_GEOGPOINT(CAST(longitude AS FLOAT64),
                     CAST(latitude  AS FLOAT64)) AS geo_point
    FROM {{ ref('stg_accidents') }}
    WHERE latitude  IS NOT NULL
      AND longitude IS NOT NULL
),

station_geo AS (
    SELECT
        station_id,
        station_name,
        longitude,
        latitude,
        ST_GEOGPOINT(CAST(longitude AS FLOAT64),
                     CAST(latitude  AS FLOAT64)) AS geo_point
    FROM {{ ref('stg_bike_stations') }}
),

-- Spatial join: accidents within 500 m of each station
scores AS (
    SELECT
        s.station_id,
        COUNT(a.accident_index)                                       AS accident_count,
        COALESCE(SUM(a.number_of_casualties), 0)                      AS total_casualties,
        COUNTIF(a.accident_severity = 1)                              AS fatal_count,
        COUNTIF(a.accident_severity = 2)                              AS serious_count,
        COUNTIF(a.accident_severity = 3)                              AS slight_count,
        COALESCE(SUM(
            10 * IF(a.accident_severity = 1, 1, 0)
          +  3 * IF(a.accident_severity = 2, 1, 0)
          +      IF(a.accident_severity = 3, 1, 0)
        ), 0)                                                          AS weighted_risk_score,
        500                                                            AS search_radius_m
    FROM station_geo s
    LEFT JOIN accidents_geo a
           ON ST_DISTANCE(s.geo_point, a.geo_point) <= 500
    GROUP BY s.station_id
),

station_volumes AS (
    SELECT station_id, SUM(trip_count) AS total_trips
    FROM (
        SELECT start_station_id AS station_id, COUNT(*) AS trip_count
        FROM {{ ref('stg_bike_journeys') }}
        GROUP BY 1
        UNION ALL
        SELECT end_station_id AS station_id, COUNT(*) AS trip_count
        FROM {{ ref('stg_bike_journeys') }}
        GROUP BY 1
    ) t
    GROUP BY station_id
)

SELECT
    sg.station_id,
    sg.station_name,
    sg.longitude,
    sg.latitude,

    COALESCE(sc.accident_count,      0) AS nearby_accident_count,
    COALESCE(sc.total_casualties,    0) AS nearby_casualties,
    COALESCE(sc.fatal_count,         0) AS nearby_fatal_count,
    COALESCE(sc.serious_count,       0) AS nearby_serious_count,
    COALESCE(sc.slight_count,        0) AS nearby_slight_count,
    COALESCE(sc.weighted_risk_score, 0) AS weighted_risk_score,
    sc.search_radius_m,

    COALESCE(sv.total_trips, 0)         AS total_trips,

    CASE
        WHEN COALESCE(sv.total_trips, 0) > 0
        THEN ROUND(sc.weighted_risk_score * 1000.0 / sv.total_trips, 2)
        ELSE 0
    END AS risk_per_1000_trips,

    NTILE(10) OVER (ORDER BY COALESCE(sc.weighted_risk_score, 0)) AS risk_decile

FROM station_geo sg
LEFT JOIN scores         sc ON sc.station_id = sg.station_id
LEFT JOIN station_volumes sv ON sv.station_id = sg.station_id

{% else %}

-- ════════════════════════════════════════════════════════════════════════════
-- DUCKDB BRANCH  –  joins pre-computed spatial_layer tables
-- ════════════════════════════════════════════════════════════════════════════

WITH scores AS (
    SELECT * FROM spatial_layer.station_blackspot_scores
),

stations AS (
    SELECT * FROM {{ ref('stg_bike_stations') }}
),

station_volumes AS (
    SELECT station_id, SUM(trip_count) AS total_trips
    FROM (
        SELECT start_station_id AS station_id, COUNT(*) AS trip_count
        FROM {{ ref('stg_bike_journeys') }}
        GROUP BY 1
        UNION ALL
        SELECT end_station_id AS station_id, COUNT(*) AS trip_count
        FROM {{ ref('stg_bike_journeys') }}
        GROUP BY 1
    ) t
    GROUP BY station_id
)

SELECT
    s.station_id,
    s.station_name,
    s.longitude,
    s.latitude,

    COALESCE(sc.accident_count,      0) AS nearby_accident_count,
    COALESCE(sc.total_casualties,    0) AS nearby_casualties,
    COALESCE(sc.fatal_count,         0) AS nearby_fatal_count,
    COALESCE(sc.serious_count,       0) AS nearby_serious_count,
    COALESCE(sc.slight_count,        0) AS nearby_slight_count,
    COALESCE(sc.weighted_risk_score, 0) AS weighted_risk_score,
    sc.search_radius_m,

    COALESCE(sv.total_trips, 0)         AS total_trips,

    CASE
        WHEN COALESCE(sv.total_trips, 0) > 0
        THEN ROUND(sc.weighted_risk_score * 1000.0 / sv.total_trips, 2)
        ELSE 0
    END AS risk_per_1000_trips,

    NTILE(10) OVER (ORDER BY COALESCE(sc.weighted_risk_score, 0)) AS risk_decile

FROM stations s
LEFT JOIN scores  sc ON sc.station_id = s.station_id
LEFT JOIN station_volumes sv ON sv.station_id = s.station_id

{% endif %}
