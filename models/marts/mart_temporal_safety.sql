-- marts/mart_temporal_safety.sql
-- Final mart: temporal accident patterns for rush-hour / weekend analysis.
-- Used by the Temporal Patterns dashboard page.

{{
  config(materialized='table', schema='marts')
}}

WITH hourly AS (
    SELECT * FROM {{ ref('int_temporal_hourly') }}
),

{% if target.type == 'bigquery' %}
monthly AS (
    -- BigQuery: derive monthly totals directly from staging (no spatial_layer)
    SELECT
        FORMAT_DATE('%Y-%m', accident_date)  AS year_month,
        EXTRACT(YEAR FROM accident_date)     AS year,
        COUNT(*)                             AS accident_count,
        SUM(number_of_casualties)            AS casualty_count
    FROM {{ ref('stg_accidents') }}
    WHERE accident_date IS NOT NULL
    GROUP BY 1, 2
),
{% else %}
monthly AS (
    SELECT * FROM spatial_layer.monthly_accident_trend
),
{% endif %}

-- Overall rush-hour vs non-rush summary
time_period_summary AS (
    SELECT
        time_of_day_period,
        day_type,
        year,
        SUM(accident_count)             AS accident_count,
        SUM(casualty_count)             AS casualty_count,
        SUM(fatal_count)                AS fatal_count,
        SUM(serious_count)              AS serious_count,
        ROUND(AVG(total_severity_weight), 2) AS avg_severity_weight
    FROM hourly
    GROUP BY time_of_day_period, day_type, year
)

SELECT
    'hourly' AS grain,
    {{ safe_cast('hour_of_day', 'STRING') }} AS dimension,
    day_type,
    time_of_day_period,
    year,
    accident_count,
    casualty_count,
    fatal_count,
    serious_count,
    pct_of_year_accidents,
    NULL AS avg_severity_weight
FROM hourly

UNION ALL

SELECT
    'time_period' AS grain,
    time_of_day_period AS dimension,
    day_type,
    time_of_day_period,
    year,
    accident_count,
    casualty_count,
    fatal_count,
    serious_count,
    NULL AS pct_of_year_accidents,
    avg_severity_weight
FROM time_period_summary

UNION ALL

SELECT
    'monthly' AS grain,
    year_month AS dimension,
    NULL AS day_type,
    NULL AS time_of_day_period,
    year,
    accident_count,
    casualty_count,
    NULL AS fatal_count,
    NULL AS serious_count,
    NULL AS pct_of_year_accidents,
    NULL AS avg_severity_weight
FROM monthly

ORDER BY grain, year, dimension
