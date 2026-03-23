-- staging/stg_accidents.sql
-- Cleans and enriches raw UK STATS19 accident data.
-- NOTE: DfT renamed accident_index → collision_index and accident_severity →
-- collision_severity in the 2024 collision dataset. We alias them back here so
-- all downstream models keep using the historical names.

{{
  config(materialized='view', schema='staging')
}}

WITH source AS (
    SELECT * FROM raw.uk_accidents
),

cleaned AS (
    SELECT
        collision_index                                   AS accident_index,
        {{ safe_cast('date', 'DATE') }}                   AS accident_date,
        COALESCE(CAST(collision_year AS INT64), year)     AS year,
        CAST(hour_of_day    AS INT64)                     AS hour_of_day,
        CAST(day_of_week    AS INT64)                     AS day_of_week,
        CAST(collision_severity AS INT64)                 AS accident_severity,
        CASE CAST(collision_severity AS INT64)
            WHEN 1 THEN 'Fatal'
            WHEN 2 THEN 'Serious'
            ELSE 'Slight'
        END                                               AS severity_label,
        CAST(number_of_casualties AS INT64)   AS number_of_casualties,
        CAST(number_of_vehicles   AS INT64)   AS number_of_vehicles,
        CAST(road_type            AS INT64)   AS road_type,
        CAST(speed_limit          AS INT64)   AS speed_limit,
        CAST(light_conditions     AS INT64)   AS light_conditions,
        CAST(weather_conditions   AS INT64)   AS weather_conditions,
        {{ safe_cast('longitude', 'DOUBLE') }} AS longitude,
        {{ safe_cast('latitude',  'DOUBLE') }} AS latitude,

        -- derived
        {{ classify_time_of_day('hour_of_day') }}  AS time_of_day_period,

        CASE CAST(day_of_week AS INT64)
            WHEN 1 THEN 'Sunday'    WHEN 2 THEN 'Monday'   WHEN 3 THEN 'Tuesday'
            WHEN 4 THEN 'Wednesday' WHEN 5 THEN 'Thursday' WHEN 6 THEN 'Friday'
            WHEN 7 THEN 'Saturday'  ELSE 'Unknown'
        END AS weekday_name,

        CASE WHEN CAST(day_of_week AS INT64) IN (1, 7) THEN 'Weekend'
             ELSE 'Weekday' END AS day_type,

        -- severity weight for risk scoring
        CASE CAST(collision_severity AS INT64)
            WHEN 1 THEN 10
            WHEN 2 THEN 3
            ELSE 1
        END AS severity_weight

    FROM source
    WHERE collision_index IS NOT NULL
      AND longitude IS NOT NULL
      AND latitude  IS NOT NULL
      AND {{ safe_cast('longitude', 'DOUBLE') }} BETWEEN -0.55 AND 0.30
      AND {{ safe_cast('latitude',  'DOUBLE') }} BETWEEN 51.28 AND 51.70
)

SELECT * FROM cleaned
