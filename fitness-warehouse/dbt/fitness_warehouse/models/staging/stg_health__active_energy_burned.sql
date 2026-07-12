-- models/staging/stg_health__active_energy_burned.sql

with source as (

    select *
    from {{ source('raw', 'active_energy_burned') }}

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
        cast(json_value(payload, '$.activeEnergyBurned.kcalSum') as float64) as active_energy_kcal

    from source

)

select * from parsed
