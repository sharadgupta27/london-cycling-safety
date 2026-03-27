-- staging/stg_bike_journeys.sql
-- Cleans and casts raw TFL journey data.
--
-- dlt schema defines duration_seconds as FLOAT64 (double) so BigQuery stores it
-- as a single FLOAT64 column. We cast it to INT64, falling back to duration_ms/1000.

{{
  config(materialized='view', schema='staging')
}}

WITH source AS (
    SELECT * FROM raw.tfl_journeys
),

{% if target.type == 'bigquery' %}
with_duration AS (
    SELECT
        *,
        CAST(
            COALESCE(
                duration_seconds,
                SAFE_DIVIDE(CAST(duration_ms AS FLOAT64), 1000.0)
            )
        AS INT64) AS dur_sec
    FROM source
),
{% else %}
with_duration AS (
    SELECT *, CAST(duration_seconds AS INT64) AS dur_sec
    FROM source
),
{% endif %}

renamed AS (
    SELECT
        CAST(rental_id         AS INT64)     AS rental_id,
        dur_sec                               AS duration_seconds,
        ROUND(dur_sec / 60.0, 1)             AS duration_minutes,
        {{ safe_cast('bike_id', 'STRING') }}     AS bike_id,
        -- bike_model present in newer TFL file vintages (2023+); NULL for older files
        {{ safe_cast('bike_model', 'STRING') }}       AS bike_model,

        -- start
        {{ safe_cast('start_date', 'TIMESTAMP') }} AS start_at,
        CAST(start_station_id       AS INT64)      AS start_station_id,
        TRIM(start_station_name)                   AS start_station_name,

        -- end
        {{ safe_cast('end_date', 'TIMESTAMP') }}   AS end_at,
        CAST(end_station_id         AS INT64)     AS end_station_id,
        TRIM(end_station_name)                    AS end_station_name,

        source_file

    FROM with_duration
    WHERE rental_id IS NOT NULL
      AND start_station_id IS NOT NULL
      AND end_station_id   IS NOT NULL
      AND start_station_id <> end_station_id
      AND dur_sec BETWEEN 60 AND 86400
)

SELECT * FROM renamed