-- models/intermediate/int_health__distance_minute.sql

with spine as (
    select * from {{ ref('int_health__minute_spine') }}
),

passive_distance as (
    select
        point_time as minute,
        distance_millimeters as passive_distance_millimeters
    from {{ ref('stg_health__distance') }}
),

exercise_distance as (
    select
        minute,
        exercise_distance_millimeters
    from {{ ref('int_health__exercise_minute') }}
)

select
    spine.minute,
    coalesce(
        exercise_distance.exercise_distance_millimeters,
        passive_distance.passive_distance_millimeters,
        0
    ) as distance_millimeters
from spine
left join passive_distance on spine.minute = passive_distance.minute
left join exercise_distance on spine.minute = exercise_distance.minute