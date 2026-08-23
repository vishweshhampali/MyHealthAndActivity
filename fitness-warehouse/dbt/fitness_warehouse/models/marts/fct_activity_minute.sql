-- models/marts/fct_activity_minute.sql

with spine as (
    select * from {{ ref('int_health__minute_spine') }}
),

steps as (
    select * from {{ ref('int_health__steps_minute') }}
),

distance as (
    select * from {{ ref('int_health__distance_minute') }}
),

energy as (
    select * from {{ ref('int_health__active_energy_burned_minute') }}
),

active_minutes as (
    select * from {{ ref('int_health__active_minutes_minute_pivoted') }}
),

exercise as (
    select * from {{ ref('int_health__exercise_minute') }}
)

select
    spine.minute,

    coalesce(steps.steps_count, 0) as steps_count,
    coalesce(distance.distance_millimeters, 0) as distance_millimeters,
    coalesce(energy.active_energy_kcal, 0) as active_energy_kcal,

    coalesce(active_minutes.light_minutes, 0) as light_minutes,
    coalesce(active_minutes.moderate_minutes, 0) as moderate_minutes,
    coalesce(active_minutes.vigorous_minutes, 0) as vigorous_minutes,

    exercise.session_id as exercise_session_id,
    exercise.exercise_type,
    exercise.recording_method,
    exercise.exercise_category

from spine
left join steps           on spine.minute = steps.minute
left join distance         on spine.minute = distance.minute
left join energy           on spine.minute = energy.minute
left join active_minutes   on spine.minute = active_minutes.minute
left join exercise         on spine.minute = exercise.minute