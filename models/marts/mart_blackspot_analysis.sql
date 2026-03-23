-- marts/mart_blackspot_analysis.sql
-- Final mart: every TFL bike station scored and ranked for accident risk.
-- Used by the Blackspot Map dashboard page.

{{
  config(materialized='table', schema='marts')
}}

WITH scored AS (
    SELECT * FROM {{ ref('int_station_blackspot_scores') }}
)

SELECT
    station_id,
    station_name,
    longitude,
    latitude,
    nearby_accident_count,
    nearby_casualties,
    nearby_fatal_count,
    nearby_serious_count,
    nearby_slight_count,
    weighted_risk_score,
    risk_per_1000_trips,
    total_trips,
    search_radius_m,
    risk_decile,

    CASE risk_decile
        WHEN 10 THEN '#d73027'   -- Dark Red   – highest risk
        WHEN 9  THEN '#f46d43'
        WHEN 8  THEN '#fdae61'
        WHEN 7  THEN '#fee08b'
        WHEN 6  THEN '#ffffbf'
        WHEN 5  THEN '#d9ef8b'
        WHEN 4  THEN '#a6d96a'
        WHEN 3  THEN '#66bd63'
        WHEN 2  THEN '#1a9850'
        ELSE         '#006837'   -- Dark Green – lowest risk
    END AS risk_colour,

    -- flag stations in top 10% risk
    (risk_decile = 10) AS is_blackspot

FROM scored
ORDER BY weighted_risk_score DESC
