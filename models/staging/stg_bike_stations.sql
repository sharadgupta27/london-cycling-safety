-- staging/stg_bike_stations.sql
-- Unique TFL docking stations with validated coordinates.

{{
  config(materialized='view', schema='staging')
}}

WITH source AS (
    SELECT * FROM raw.tfl_stations
),

cleaned AS (
    SELECT
        CAST(station_id   AS INT64)   AS station_id,
        TRIM(station_name)            AS station_name,
        CAST(longitude    AS FLOAT64) AS longitude,
        CAST(latitude     AS FLOAT64) AS latitude
    FROM source
    WHERE station_id  IS NOT NULL
      AND longitude BETWEEN -0.55 AND 0.30
      AND latitude  BETWEEN 51.28 AND 51.70
),

deduped AS (
    -- DISTINCT ON is PostgreSQL-only; use ROW_NUMBER for DuckDB compatibility
    SELECT station_id, station_name, longitude, latitude
    FROM (
        SELECT
            station_id, station_name, longitude, latitude,
            ROW_NUMBER() OVER (PARTITION BY station_id ORDER BY station_id) AS rn
        FROM cleaned
    ) sub
    WHERE rn = 1
)

SELECT * FROM deduped
