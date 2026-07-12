-- models/staging/stg_health__exercise.sql

with source as (

    select *
    from {{ source('raw', 'exercise') }}

),

parsed as (

    select
        data_type,
        method,
        point_time,
        ingested_at,

        -- payload fields, typed
        json_value(payload, '$.name') as data_point_name,
        json_value(payload, '$.exercise.displayName') as exercise_name,
        json_value(payload, '$.exercise.exerciseType') as exercise_type,
        timestamp(json_value(payload, '$.exercise.interval.startTime')) as start_time,
        timestamp(json_value(payload, '$.exercise.interval.endTime'))   as end_time,
        cast(
            regexp_extract(json_value(payload, '$.exercise.activeDuration'), r'^([\d.]+)s$')
            as float64
        ) as active_duration_seconds,
        cast(json_value(payload, '$.exercise.metricsSummary.distanceMillimeters') as int64)
            as distance_millimeters,
        cast(json_value(payload, '$.exercise.metricsSummary.steps') as int64) as steps_count,
        cast(json_value(payload, '$.exercise.metricsSummary.averagePaceSecondsPerMeter') as float64)
            as avg_pace_seconds_per_meter

    from source

)

select * from parsed
