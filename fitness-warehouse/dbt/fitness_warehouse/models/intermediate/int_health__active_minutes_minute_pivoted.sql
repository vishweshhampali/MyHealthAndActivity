-- models/intermediate/int_health__active_minutes_minute_pivoted.sql

with active_minutes as (
    select * from {{ ref('int_health__active_minutes_minute') }}
)

select
    minute,
    sum(case when activity_level = 'LIGHT'    then active_minutes_count else 0 end) as light_minutes,
    sum(case when activity_level = 'MODERATE' then active_minutes_count else 0 end) as moderate_minutes,
    sum(case when activity_level = 'VIGOROUS' then active_minutes_count else 0 end) as vigorous_minutes
from active_minutes
group by minute