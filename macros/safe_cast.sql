{#
  Adapter macro: BigQuery uses SAFE_CAST, DuckDB uses TRY_CAST.
  Also normalises type names so callers can use either dialect:
    DOUBLE  / FLOAT64  — mapped to FLOAT64  on BigQuery, DOUBLE  on DuckDB
    VARCHAR / STRING   — mapped to STRING   on BigQuery, VARCHAR on DuckDB
#}
{% macro safe_cast(value, type) %}
  {%- if target.type == 'bigquery' -%}
    {%- set t = type | upper | replace('DOUBLE', 'FLOAT64') | replace('VARCHAR', 'STRING') -%}
    SAFE_CAST({{ value }} AS {{ t }})
  {%- else -%}
    {%- set t = type | upper | replace('FLOAT64', 'DOUBLE') | replace('STRING', 'VARCHAR') -%}
    TRY_CAST({{ value }} AS {{ t }})
  {%- endif -%}
{% endmacro %}
