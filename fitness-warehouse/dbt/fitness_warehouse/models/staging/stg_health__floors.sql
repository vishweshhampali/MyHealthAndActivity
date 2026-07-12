-- models/staging/stg_health__floors.sql
--
-- No floors data has landed yet (raw.floors is currently empty on this phone-only account), so
-- the payload shape below is inferred from `ghealth schema type floors` rather than an observed
-- sample. It mirrors stg_health__steps: floors' "count" field rolls up the same way steps' does,
-- to a "<type>.countSum" key. Re-check against a real payload once floors data actually lands.

with source as (

    select *
    from {{ source('raw', 'floors') }}

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
        cast(json_value(payload, '$.floors.countSum') as int64) as floors_count

    from source

)

select * from parsed
