-- models/intermediate/int_health__exercise_minute.sql

with sessions as (

    select
        data_point_name as session_id,
        exercise_type,
        recording_method,
        start_time,
        end_time,
        distance_millimeters as session_distance_millimeters

    from {{ ref('stg_health__exercise') }}

),

exploded as (

    select
        session_id,
        exercise_type,
        recording_method,
        session_distance_millimeters,
        minute,
        count(*) over (partition by session_id) as minutes_in_session,

        -- explicit tracking (manual entry or GPS-active recording) outranks
        -- passive auto-detection for overlapping minutes
        case
            when recording_method = 'PASSIVELY_MEASURED' then 2
            else 1
        end as recording_priority

    from sessions,
    unnest(generate_timestamp_array(
        timestamp_trunc(start_time, minute),
        timestamp_trunc(end_time, minute),
        interval 1 minute
    )) as minute

),

resolved as (

    select *
    from exploded
    qualify row_number() over (
        partition by minute
        order by recording_priority asc, session_id
    ) = 1

)

select
    minute,
    session_id,
    exercise_type,
    recording_method,
    case
        when session_distance_millimeters is not null
            then session_distance_millimeters / minutes_in_session
        else null
    end as exercise_distance_millimeters

from resolved