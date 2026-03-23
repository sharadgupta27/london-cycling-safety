{% macro classify_time_of_day(hour_col) %}
    CASE
        WHEN {{ hour_col }} BETWEEN 7  AND 9  THEN 'AM Rush (07-09)'
        WHEN {{ hour_col }} BETWEEN 17 AND 19 THEN 'PM Rush (17-19)'
        WHEN {{ hour_col }} BETWEEN 10 AND 16 THEN 'Midday (10-16)'
        WHEN {{ hour_col }} BETWEEN 20 AND 23 THEN 'Evening (20-23)'
        WHEN {{ hour_col }} BETWEEN 0  AND 6  THEN 'Night (00-06)'
        ELSE 'Unknown'
    END
{% endmacro %}
