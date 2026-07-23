-- models/intermediate/int_health__active_energy_burned_minute.sql

with spine as (
    select * from {{ ref('int_health__minute_spine') }}
),

energy as (
    select
        point_time as minute,
        active_energy_kcal
    from {{ ref('stg_health__active_energy_burned') }}
)

select
    spine.minute,
    coalesce(energy.active_energy_kcal, 0) as active_energy_kcal
from spine
left join energy on spine.minute = energy.minute