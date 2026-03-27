-- marts/mart_corridor_risk_score.sql
-- Final mart: corridors ranked by composite risk score.
-- composite_risk_score = severity-weighted crashes per million journey-km
--   (exposure-normalised rate; journey_count used as AADT proxy)
-- Used by the Corridor Risk dashboard page.

{{
  config(materialized='table', schema='marts')
}}

WITH corridors AS (
    SELECT * FROM {{ ref('int_corridor_risk') }}
)

SELECT
    risk_rank,
    station_a_id,
    station_b_id,
    station_a_name,
    station_b_name,
    CONCAT(station_a_name, ' ↔ ', station_b_name) AS corridor_label,
    journey_count,
    length_m,
    corridor_accident_count,
    risk_per_km,
    composite_risk_score,
    risk_category,
    lon_a,
    lat_a,
    lon_b,
    lat_b,
    mid_lon,
    mid_lat,

    -- Colour by risk category
    CASE risk_category
        WHEN 'Very High' THEN '#d73027'
        WHEN 'High'      THEN '#fc8d59'
        WHEN 'Medium'    THEN '#fee08b'
        ELSE                  '#91cf60'
    END AS corridor_colour

FROM corridors
ORDER BY risk_rank
