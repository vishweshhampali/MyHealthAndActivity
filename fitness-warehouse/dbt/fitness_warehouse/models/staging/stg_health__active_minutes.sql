-- models/staging/stg_health__active_minutes.sql
--
-- One row per activity-level bucket per rollup interval (payload nests a
-- activeMinutesRollupByActivityLevel array), rather than one row per source record.

with source as (

    select *
    from {{ source('raw', 'active_minutes') }}

),

parsed as (

    select
        data_type,
        method,
        point_time,
        ingested_at,

        -- payload fields, typed
        timestamp(json_value(payload, '$.startTime')) as start_time,
        timestamp(json_value(payload, '$.endTime'))   as end_time,
        json_value(level, '$.activityLevel') as activity_level,
        cast(json_value(level, '$.activeMinutesSum') as int64) as active_minutes_count

    from source,
    unnest(json_query_array(payload, '$.activeMinutes.activeMinutesRollupByActivityLevel')) as level

)

select * from parsed
