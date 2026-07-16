-- models/intermediate/int_health__minute_spine.sql
{{ config(materialized='table') }}

with bounds as (

    select
        min(point_time) as min_time,
        max(point_time) as max_time
    from {{ ref('stg_health__steps') }}

),

spine as (

    select minute
    from bounds,
    unnest(generate_timestamp_array(
        timestamp_trunc(min_time, minute),
        timestamp_trunc(max_time, minute),
        interval 1 minute
    )) as minute

)

select * from spine