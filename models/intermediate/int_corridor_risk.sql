-- intermediate/int_corridor_risk.sql
--
-- DuckDB  (dev):  joins spatial_layer.corridor_risk computed by
--                 spatial_transforms.py
-- BigQuery (prod): builds corridors from journey data and computes accident
--                  proximity using ST_MAKELINE / ST_DWITHIN — no Python step.

{{
  config(materialized='table', schema='intermediate')
}}

{% if target.type == 'bigquery' %}

-- ════════════════════════════════════════════════════════════════════════════
-- BIGQUERY BRANCH
-- ════════════════════════════════════════════════════════════════════════════

WITH station_geo AS (
    SELECT
        station_id,
        station_name,
        CAST(longitude AS FLOAT64) AS longitude,
        CAST(latitude  AS FLOAT64) AS latitude,
        ST_GEOGPOINT(CAST(longitude AS FLOAT64),
                     CAST(latitude  AS FLOAT64)) AS geo_point
    FROM {{ ref('stg_bike_stations') }}
),

-- Unique directed corridors with journey volume
-- NOTE: journey CSVs use station IDs 959+ which differ from BikePoint IDs (1-888).
--       Station NAMES are identical in both datasets, so we carry names from the
--       journey data and join to station_geo using station_name.
corridor_pairs AS (
    SELECT
        LEAST(start_station_id,    end_station_id)    AS station_a_id,
        GREATEST(start_station_id, end_station_id)    AS station_b_id,
        -- Carry station names matching the LEAST/GREATEST ID ordering
        ANY_VALUE(
            CASE WHEN start_station_id <= end_station_id
                 THEN TRIM(start_station_name)
                 ELSE TRIM(end_station_name)   END
        )                                              AS station_a_name_raw,
        ANY_VALUE(
            CASE WHEN start_station_id <= end_station_id
                 THEN TRIM(end_station_name)
                 ELSE TRIM(start_station_name) END
        )                                              AS station_b_name_raw,
        COUNT(*)                                       AS journey_count
    FROM {{ ref('stg_bike_journeys') }}
    WHERE start_station_id IS NOT NULL
      AND end_station_id   IS NOT NULL
      AND start_station_id <> end_station_id
      AND start_station_name IS NOT NULL
      AND end_station_name   IS NOT NULL
    GROUP BY 1, 2
    HAVING COUNT(*) >= 100  -- minimum exposure: exclude corridors with < 100 journeys
),

-- Attach station geometry to each corridor (join on name, not ID)
corridor_lines AS (
    SELECT
        cp.station_a_id,
        cp.station_b_id,
        cp.journey_count,
        a.station_name                         AS station_a_name,
        b.station_name                         AS station_b_name,
        a.longitude                            AS lon_a,
        a.latitude                             AS lat_a,
        b.longitude                            AS lon_b,
        b.latitude                             AS lat_b,
        (a.longitude + b.longitude) / 2        AS mid_lon,
        (a.latitude  + b.latitude)  / 2        AS mid_lat,
        ST_DISTANCE(a.geo_point, b.geo_point)  AS length_m,
        ST_MAKELINE(a.geo_point, b.geo_point)  AS corridor_line
    FROM corridor_pairs cp
    JOIN station_geo a ON a.station_name = cp.station_a_name_raw
    JOIN station_geo b ON b.station_name = cp.station_b_name_raw
),

accidents_geo AS (
    SELECT
        accident_index,
        accident_severity,
        ST_GEOGPOINT(CAST(longitude AS FLOAT64),
                     CAST(latitude  AS FLOAT64)) AS geo_point
    FROM {{ ref('stg_accidents') }}
    WHERE latitude  IS NOT NULL
      AND longitude IS NOT NULL
),

-- Accidents within 200 m of the corridor line
corridor_risk_raw AS (
    SELECT
        cl.station_a_id,
        cl.station_b_id,
        COUNT(a.accident_index)   AS corridor_accident_count,
        COALESCE(SUM(
            10 * IF(a.accident_severity = 1, 1, 0)
          +  3 * IF(a.accident_severity = 2, 1, 0)
          +      IF(a.accident_severity = 3, 1, 0)
        ), 0)                     AS corridor_risk_raw_score
    FROM corridor_lines cl
    LEFT JOIN accidents_geo a
           ON ST_DWITHIN(cl.corridor_line, a.geo_point, 200)
    GROUP BY 1, 2
),

enriched AS (
    SELECT
        cl.station_a_id,
        cl.station_b_id,
        cl.station_a_name,
        cl.station_b_name,
        cl.journey_count,
        cl.lon_a,
        cl.lat_a,
        cl.lon_b,
        cl.lat_b,
        cl.mid_lon,
        cl.mid_lat,
        ROUND(cl.length_m, 0)                                 AS length_m,
        cr.corridor_accident_count,
        cr.corridor_risk_raw_score                             AS corridor_risk_raw,

        -- risk per km
        ROUND(SAFE_DIVIDE(cr.corridor_risk_raw_score,
                          cl.length_m / 1000.0), 2)            AS risk_per_km,

        -- exposure-normalised risk: severity-weighted crashes per million journey-km
        -- Formula: Risk = severity_crashes / (length_km × journey_count) × 1,000,000
        -- Uses journey_count as AADT proxy; dividing by exposure avoids inflating
        -- scores for high-volume corridors (replaces old: raw × ln(journeys+1))
        ROUND(
            SAFE_DIVIDE(
                cr.corridor_risk_raw_score,
                (cl.length_m / 1000.0) * cl.journey_count
            ) * 1000000,
        2)                                                     AS composite_risk_score
    FROM corridor_lines cl
    JOIN corridor_risk_raw cr
      ON cr.station_a_id = cl.station_a_id
     AND cr.station_b_id = cl.station_b_id
),

-- Percentile thresholds using APPROX_QUANTILES
thresholds AS (
    SELECT
        APPROX_QUANTILES(composite_risk_score, 10)[OFFSET(4)] AS p40,
        APPROX_QUANTILES(composite_risk_score, 10)[OFFSET(7)] AS p70,
        APPROX_QUANTILES(composite_risk_score, 10)[OFFSET(9)] AS p90
    FROM enriched
)

SELECT
    e.*,
    RANK() OVER (ORDER BY e.composite_risk_score DESC) AS risk_rank,
    CASE
        WHEN e.composite_risk_score > t.p90 THEN 'Very High'
        WHEN e.composite_risk_score > t.p70 THEN 'High'
        WHEN e.composite_risk_score > t.p40 THEN 'Medium'
        ELSE                                     'Low'
    END AS risk_category
FROM enriched e CROSS JOIN thresholds t

{% else %}

-- ════════════════════════════════════════════════════════════════════════════
-- DUCKDB BRANCH  –  joins pre-computed spatial_layer tables
-- ════════════════════════════════════════════════════════════════════════════

WITH cr AS (
    SELECT * FROM spatial_layer.corridor_risk
),

thresholds AS (
    SELECT
        quantile_cont(composite_risk_score, 0.4) AS p40,
        quantile_cont(composite_risk_score, 0.7) AS p70,
        quantile_cont(composite_risk_score, 0.9) AS p90
    FROM cr
)

SELECT
    cr.station_a_id,
    cr.station_b_id,
    cr.station_a_name,
    cr.station_b_name,
    cr.journey_count,
    cr.lon_a,
    cr.lat_a,
    cr.lon_b,
    cr.lat_b,
    cr.mid_lon,
    cr.mid_lat,
    ROUND(cr.length_m, 0)             AS length_m,
    cr.corridor_accident_count,
    cr.corridor_risk_raw,
    ROUND(cr.risk_per_km, 2)          AS risk_per_km,
    ROUND(cr.composite_risk_score, 2) AS composite_risk_score,
    RANK() OVER (ORDER BY cr.composite_risk_score DESC) AS risk_rank,
    CASE
        WHEN cr.composite_risk_score > t.p90 THEN 'Very High'
        WHEN cr.composite_risk_score > t.p70 THEN 'High'
        WHEN cr.composite_risk_score > t.p40 THEN 'Medium'
        ELSE                                       'Low'
    END AS risk_category
FROM cr CROSS JOIN thresholds t

{% endif %}
