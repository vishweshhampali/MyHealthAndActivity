-- models/marts/fct_activity_daily.sql

with minute_agg as (

    select
        date(minute) as activity_date,
        sum(steps_count) as steps_count,
        sum(distance_millimeters) as distance_millimeters,
        sum(active_energy_kcal) as active_energy_kcal,
        sum(light_minutes) as light_minutes,
        sum(moderate_minutes) as moderate_minutes,
        sum(vigorous_minutes) as vigorous_minutes,
        count(distinct exercise_session_id) as exercise_session_count,
        array_agg(distinct exercise_type ignore nulls) as exercise_types,

        sum(case when exercise_category = 'running' then 1 else 0 end) as running_minutes,
        sum(case when exercise_category = 'walking' then 1 else 0 end) as walking_minutes,
        sum(case when exercise_category = 'gym'     then 1 else 0 end) as gym_minutes,
        sum(case when exercise_category = 'sports'  then 1 else 0 end) as sports_minutes

    from {{ ref('fct_activity_minute') }}
    group by 1

),

calories as (
    select * from {{ ref('int_health__total_calories_daily') }}
)

select
    minute_agg.activity_date,
    date_trunc(minute_agg.activity_date, week)  as week_start,
    date_trunc(minute_agg.activity_date, month) as month_start,

    minute_agg.steps_count,
    minute_agg.distance_millimeters,
    minute_agg.active_energy_kcal,
    minute_agg.light_minutes,
    minute_agg.moderate_minutes,
    minute_agg.vigorous_minutes,
    minute_agg.light_minutes + minute_agg.moderate_minutes + minute_agg.vigorous_minutes as total_active_minutes,
    minute_agg.exercise_session_count,
    minute_agg.exercise_types,

    minute_agg.running_minutes,
    minute_agg.walking_minutes,
    minute_agg.gym_minutes,
    minute_agg.sports_minutes,

    minute_agg.running_minutes > 0 as did_run,
    minute_agg.walking_minutes > 0 as did_walk,
    minute_agg.gym_minutes > 0     as did_gym,
    minute_agg.sports_minutes > 0  as did_sport,

    -- Looker-safe 0/1 versions — charts can SUM directly, no calculated fields needed
    cast(minute_agg.running_minutes > 0 as int64) as run_day,
    cast(minute_agg.walking_minutes > 0 as int64) as walk_day,
    cast(minute_agg.gym_minutes > 0     as int64) as gym_day,
    cast(minute_agg.sports_minutes > 0  as int64) as sport_day,

    -- Discipline = deliberate training only (excludes passively-detected walking)
    (minute_agg.running_minutes > 0 or minute_agg.gym_minutes > 0 or minute_agg.sports_minutes > 0) as trained_deliberately,
    cast(minute_agg.running_minutes > 0 or minute_agg.gym_minutes > 0 or minute_agg.sports_minutes > 0 as int64) as trained_day,

    calories.total_calories_kcal

from minute_agg
left join calories on minute_agg.activity_date = calories.activity_date