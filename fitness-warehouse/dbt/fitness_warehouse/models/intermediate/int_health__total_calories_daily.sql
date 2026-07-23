-- models/intermediate/int_health__total_calories_daily.sql

select
    civil_start_date as activity_date,
    total_calories_kcal
from {{ ref('stg_health__total_calories') }}