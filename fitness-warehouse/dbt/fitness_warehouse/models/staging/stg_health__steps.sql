select *
from {{ source('raw', 'steps') }}
