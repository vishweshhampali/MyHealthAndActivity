-- models/intermediate/int_health__steps_minute.sql

with spine as (
    select * from {{ ref('int_health__minute_spine') }}
),

steps as (
    select
        point_time as minute,
        steps_count
    from {{ ref('stg_health__steps') }}
)

select
    spine.minute,
    coalesce(steps.steps_count, 0) as steps_count
from spine
left join steps on spine.minute = steps.minute