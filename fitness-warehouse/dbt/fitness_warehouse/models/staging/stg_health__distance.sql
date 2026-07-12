-- models/staging/stg_health__distance.sql

with source as (

    select *
    from {{ source('raw', 'distance') }}

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
        cast(json_value(payload, '$.distance.millimetersSum') as int64) as distance_millimeters

    from source

)

select * from parsed
