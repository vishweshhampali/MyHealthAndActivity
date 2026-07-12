-- models/staging/stg_health__total_calories.sql
--
-- daily-rollup only: payload carries civil dates (no time-of-day), not startTime/endTime
-- timestamps like the other rollup types.

with source as (

    select *
    from {{ source('raw', 'total_calories') }}

),

parsed as (

    select
        data_type,
        method,
        point_time,
        ingested_at,

        -- payload fields, typed
        date(
            cast(json_value(payload, '$.civilStartTime.date.year') as int64),
            cast(json_value(payload, '$.civilStartTime.date.month') as int64),
            cast(json_value(payload, '$.civilStartTime.date.day') as int64)
        ) as civil_start_date,
        date(
            cast(json_value(payload, '$.civilEndTime.date.year') as int64),
            cast(json_value(payload, '$.civilEndTime.date.month') as int64),
            cast(json_value(payload, '$.civilEndTime.date.day') as int64)
        ) as civil_end_date,
        cast(json_value(payload, '$.totalCalories.kcalSum') as float64) as total_calories_kcal

    from source

)

select * from parsed
