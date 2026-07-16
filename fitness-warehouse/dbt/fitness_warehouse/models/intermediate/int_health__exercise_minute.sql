-- models/intermediate/int_health__exercise_minute.sql

with sessions as (

    select
        data_point_name as session_id,
        exercise_type,
        start_time,
        end_time,
        distance_millimeters as session_distance_millimeters

    from {{ ref('stg_health__exercise') }}

),

exploded as (

    select
        session_id,
        exercise_type,
        session_distance_millimeters,
        minute,
        count(*) over (partition by session_id) as minutes_in_session

    from sessions,
    unnest(generate_timestamp_array(
        timestamp_trunc(start_time, minute),
        timestamp_trunc(end_time, minute),
        interval 1 minute
    )) as minute

)

select
    minute,
    session_id,
    exercise_type,
    -- spread the session's total distance evenly across its minutes,
    -- only when the session actually recorded a distance (e.g. not strength training)
    case
        when session_distance_millimeters is not null
            then session_distance_millimeters / minutes_in_session
        else null
    end as exercise_distance_millimeters

from exploded