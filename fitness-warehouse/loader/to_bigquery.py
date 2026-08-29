"""BigQuery state and loading: read the latest point already loaded per type, append new ones.

Auth via Application Default Credentials only.
"""
import io
import json

from google.api_core.exceptions import NotFound
from google.cloud import bigquery

PROJECT = "vishactivitytracker"
DATASET = "raw"
STATE_TABLE = f"{PROJECT}.{DATASET}._sync_state"

SCHEMA = [
    bigquery.SchemaField("data_type", "STRING"),
    bigquery.SchemaField("method", "STRING"),
    bigquery.SchemaField("point_time", "TIMESTAMP"),
    bigquery.SchemaField("ingested_at", "TIMESTAMP"),
    bigquery.SchemaField("run_id", "STRING"),
    bigquery.SchemaField("payload", "JSON"),
]


def table_id(data_type):
    return f"{PROJECT}.{DATASET}.{data_type.replace('-', '_')}"


def latest_date(client, data_type):
    """Latest date already loaded for this type, or None if the table is empty/missing."""
    try:
        rows = list(client.query(
            f"select max(date(point_time)) as d from `{table_id(data_type)}`"
        ).result())
    except NotFound:
        return None
    return rows[0]["d"] if rows and rows[0]["d"] else None


def read_sync_state(client):
    """All {data_type: synced_through} rows in _sync_state, or {} if the table doesn't exist yet."""
    try:
        rows = list(client.query(
            f"select data_type, synced_through from `{STATE_TABLE}`"
        ).result())
    except NotFound:
        return {}
    return {r["data_type"]: r["synced_through"] for r in rows}


def synced_through(client, data_type):
    """Latest date this type has been checked through, per _sync_state (may lag real data)."""
    return read_sync_state(client).get(data_type)


def write_sync_state(client, data_type, through_date):
    """Record that this type has been checked through through_date, regardless of point count.

    Needed alongside latest_date(): a type with zero data points (e.g. floors, on a
    phone-only account) never advances max(point_time), so without a separate "we checked
    through this date" marker every run would re-scan its entire history from scratch. Rewrites
    the whole (tiny) state table via a load job rather than MERGE/UPDATE, since this project's
    BigQuery free tier blocks DML queries.
    """
    state = read_sync_state(client)
    state[data_type] = through_date
    lines = "\n".join(
        json.dumps({"data_type": dt, "synced_through": d.isoformat()})
        for dt, d in state.items()
    ) + "\n"
    job_config = bigquery.LoadJobConfig(
        source_format=bigquery.SourceFormat.NEWLINE_DELIMITED_JSON,
        schema=[
            bigquery.SchemaField("data_type", "STRING"),
            bigquery.SchemaField("synced_through", "DATE"),
        ],
        write_disposition=bigquery.WriteDisposition.WRITE_TRUNCATE,
    )
    job = client.load_table_from_file(io.BytesIO(lines.encode("utf-8")), STATE_TABLE, job_config=job_config)
    job.result()


def append_points(client, data_type, ndjson_bytes):
    """Append an in-memory NDJSON buffer to raw.<type>, creating the table on first load.

    ALLOW_FIELD_ADDITION lets this add the new run_id column to tables that were
    created before it existed, without a manual ALTER TABLE first.
    """
    if not ndjson_bytes:
        return
    job_config = bigquery.LoadJobConfig(
        source_format=bigquery.SourceFormat.NEWLINE_DELIMITED_JSON,
        schema=SCHEMA,
        write_disposition=bigquery.WriteDisposition.WRITE_APPEND,
        schema_update_options=[bigquery.SchemaUpdateOption.ALLOW_FIELD_ADDITION],
    )
    job = client.load_table_from_file(io.BytesIO(ndjson_bytes), table_id(data_type), job_config=job_config)
    job.result()


RUN_LOG_TABLE = f"{PROJECT}.{DATASET}._pipeline_runs"

RUN_LOG_SCHEMA = [
    bigquery.SchemaField("run_id", "STRING"),
    bigquery.SchemaField("workflow", "STRING"),
    bigquery.SchemaField("trigger", "STRING"),
    bigquery.SchemaField("started_at", "TIMESTAMP"),
    bigquery.SchemaField("finished_at", "TIMESTAMP"),
    bigquery.SchemaField("duration_seconds", "FLOAT"),
    bigquery.SchemaField("status", "STRING"),           # 'success' or 'failure'
    bigquery.SchemaField("error_source", "STRING"),      # which source broke, if any
    bigquery.SchemaField("error_message", "STRING"),
    bigquery.SchemaField("run_url", "STRING"),           # link back to the GitHub Actions run
    bigquery.SchemaField("details", "JSON"),             # counts: sources completed, chunks, points
]


def write_run_log(client, record: dict):
    """Append one row to raw._pipeline_runs, creating the table on first use."""
    row = dict(record)
    row["details"] = json.dumps(row.get("details") or {})
    line = json.dumps(row) + "\n"
    job_config = bigquery.LoadJobConfig(
        source_format=bigquery.SourceFormat.NEWLINE_DELIMITED_JSON,
        schema=RUN_LOG_SCHEMA,
        write_disposition=bigquery.WriteDisposition.WRITE_APPEND,
    )
    job = client.load_table_from_file(io.BytesIO(line.encode("utf-8")), RUN_LOG_TABLE, job_config=job_config)
    job.result()
