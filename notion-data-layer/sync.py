import os
from datetime import date, timedelta

from google.cloud import bigquery

from digest_query import DIGEST_SQL
from notion_sync import upsert_day

GCP_PROJECT = os.environ["GCP_PROJECT"]
NOTION_DATABASE_ID = os.environ["NOTION_DATABASE_ID"]
NOTION_TOKEN = os.environ["NOTION_API_TOKEN"]


def _run_digest(landing_date: date) -> dict | None:
    bq = bigquery.Client(project=GCP_PROJECT)
    job_config = bigquery.QueryJobConfig(
        query_parameters=[bigquery.ScalarQueryParameter("landing_date", "DATE", landing_date)]
    )
    rows = list(bq.query(DIGEST_SQL, job_config=job_config).result())
    return dict(rows[0]) if rows else None


def main():
    # SYNC_DATE lets you backfill a specific day manually (workflow_dispatch input);
    # defaults to "yesterday" for the daily scheduled run
    date_str = os.environ.get("SYNC_DATE", "").strip()
    landing_date = date.fromisoformat(date_str) if date_str else date.today() - timedelta(days=1)

    row = _run_digest(landing_date)
    if row is None:
        print(f"no data for {landing_date.isoformat()}")
        return

    upsert_day(NOTION_TOKEN, NOTION_DATABASE_ID, row)
    print(f"synced {landing_date.isoformat()}")


if __name__ == "__main__":
    main()
