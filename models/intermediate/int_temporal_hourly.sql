-- intermediate/int_temporal_hourly.sql
-- Hourly and day-type accident aggregations for temporal analysis.

{{
  config(materialized='table', schema='intermediate')
}}

WITH accidents AS (
    SELECT * FROM {{ ref('stg_accidents') }}
),

hourly AS (
    SELECT
        hour_of_day,
        day_type,
        time_of_day_period,
        year,
        COUNT(*)                    AS accident_count,
        SUM(number_of_casualties)   AS casualty_count,
        SUM(severity_weight)        AS total_severity_weight,
        SUM(fatal_count)            AS fatal_count,
        SUM(serious_count)          AS serious_count
    FROM (
        SELECT
            a.*,
            CASE WHEN a.accident_severity = 1 THEN 1 ELSE 0 END AS fatal_count,
            CASE WHEN a.accident_severity = 2 THEN 1 ELSE 0 END AS serious_count
        FROM accidents a
    ) t
    WHERE hour_of_day IS NOT NULL
    GROUP BY hour_of_day, day_type, time_of_day_period, year
)

SELECT
    hour_of_day,
    day_type,
    time_of_day_period,
    year,
    accident_count,
    casualty_count,
    total_severity_weight,
    fatal_count,
    serious_count,
    ROUND(
        accident_count * 100.0 / SUM(accident_count) OVER (PARTITION BY year),
        2
    ) AS pct_of_year_accidents
FROM hourly
ORDER BY hour_of_day, day_type
