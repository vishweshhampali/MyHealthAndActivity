-- models/intermediate/int_health__active_minutes_minute.sql

with spine as (
    select * from {{ ref('int_health__minute_spine') }}
),

active_minutes as (
    select
        point_time as minute,
        activity_level,
        active_minutes_count
    from {{ ref('stg_health__active_minutes') }}
)

select
    spine.minute,
    active_minutes.activity_level,
    coalesce(active_minutes.active_minutes_count, 0) as active_minutes_count
from spine
left join active_minutes on spine.minute = active_minutes.minute