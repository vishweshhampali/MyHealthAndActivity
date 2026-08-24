import os
import time
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


def _sync_one(landing_date: date):
    row = _run_digest(landing_date)
    if row is None:
        print(f"no data for {landing_date.isoformat()}")
        return
    upsert_day(NOTION_TOKEN, NOTION_DATABASE_ID, row)
    print(f"synced {landing_date.isoformat()}")


def main():
    # Backfill mode: loop a whole range in one run if both dates are given
    start_str = os.environ.get("SYNC_START_DATE", "").strip()
    end_str = os.environ.get("SYNC_END_DATE", "").strip()

    if start_str and end_str:
        start = date.fromisoformat(start_str)
        end = date.fromisoformat(end_str)
        if start > end:
            raise ValueError(f"start_date {start} is after end_date {end}")
        current = start
        while current <= end:
            _sync_one(current)
            current += timedelta(days=1)
            time.sleep(0.4)  # stay comfortably under Notion's rate limit
        return

    # Normal mode: a single day (defaults to "yesterday")
    date_str = os.environ.get("SYNC_DATE", "").strip()
    landing_date = date.fromisoformat(date_str) if date_str else date.today() - timedelta(days=1)
    _sync_one(landing_date)


if __name__ == "__main__":
    main()
