-- models/intermediate/int_health__distance_minute.sql

with spine as (
    select * from {{ ref('int_health__minute_spine') }}
),

distance as (
    select
        point_time as minute,
        distance_millimeters
    from {{ ref('stg_health__distance') }}
)

select
    spine.minute,
    coalesce(distance.distance_millimeters, 0) as distance_millimeters
from spine
left join distance on spine.minute = distance.minute