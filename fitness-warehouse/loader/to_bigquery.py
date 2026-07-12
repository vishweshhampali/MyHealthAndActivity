"""Load verbatim NDJSON from data/raw/<type>/ into BigQuery, one table per data type.

Batch load only (free tier); WRITE_TRUNCATE per table so a re-run rebuilds each table from
whatever files currently exist on disk. Auth via Application Default Credentials only.

Run from fitness-warehouse/ with .venv active:  python loader/to_bigquery.py
"""
import glob
import io
import os

from google.cloud import bigquery

PROJECT = "vishactivitytracker"
DATASET = "raw"

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW_DIR = os.path.join(ROOT, "data", "raw")

SCHEMA = [
    bigquery.SchemaField("data_type", "STRING"),
    bigquery.SchemaField("method", "STRING"),
    bigquery.SchemaField("point_time", "TIMESTAMP"),
    bigquery.SchemaField("ingested_at", "TIMESTAMP"),
    bigquery.SchemaField("payload", "JSON"),
]


def load_type(client, data_type):
    """Concatenate every NDJSON file for this type and load it as one batch job."""
    files = sorted(glob.glob(os.path.join(RAW_DIR, data_type, "*.ndjson")))
    if not files:
        return None

    buf = io.BytesIO()
    for fp in files:
        with open(fp, "rb") as f:
            buf.write(f.read())
    buf.seek(0)

    table_name = data_type.replace("-", "_")
    table_id = f"{PROJECT}.{DATASET}.{table_name}"

    job_config = bigquery.LoadJobConfig(
        source_format=bigquery.SourceFormat.NEWLINE_DELIMITED_JSON,
        schema=SCHEMA,
        write_disposition=bigquery.WriteDisposition.WRITE_TRUNCATE,
    )
    job = client.load_table_from_file(buf, table_id, job_config=job_config)
    job.result()

    table = client.get_table(table_id)
    return table_name, len(files), table.num_rows


def main():
    client = bigquery.Client(project=PROJECT)
    data_types = sorted(
        d for d in os.listdir(RAW_DIR) if os.path.isdir(os.path.join(RAW_DIR, d))
    )
    for data_type in data_types:
        result = load_type(client, data_type)
        if result is None:
            continue
        table_name, n_files, n_rows = result
        print(f"{table_name:24} {n_files:3} files -> {n_rows:6} rows")


if __name__ == "__main__":
    main()
