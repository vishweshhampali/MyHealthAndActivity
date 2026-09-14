import os
import time
from datetime import date, timedelta

from google.cloud import bigquery

from digest_query import DIGEST_SQL
from notion_sync import upsert_day, latest_synced_date

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

    # Explicit single day, if asked for
    date_str = os.environ.get("SYNC_DATE", "").strip()
    if date_str:
        _sync_one(date.fromisoformat(date_str))
        return

    # Scheduled mode: sync forward from whatever Notion already has.
    # Normally that is exactly one day. If the loader was down for a stretch, the
    # sync did not run either, so those days are absent from Notion — this catches
    # them up in one pass rather than leaving holes that misalign the calendar.
    end = date.today() - timedelta(days=1)
    latest = latest_synced_date(NOTION_TOKEN, NOTION_DATABASE_ID)

    if latest is None:
        print("Notion is empty — run a backfill with start_date/end_date first.")
        return

    start = latest + timedelta(days=1)
    if start > end:
        print(f"already up to date through {latest.isoformat()}")
        return

    max_catchup = int(os.environ.get("MAX_CATCHUP_DAYS", "60"))
    if (end - start).days + 1 > max_catchup:
        raise SystemExit(
            f"gap of {(end - start).days + 1} days exceeds MAX_CATCHUP_DAYS={max_catchup}. "
            "Run an explicit backfill instead."
        )

    current = start
    while current <= end:
        _sync_one(current)
        current += timedelta(days=1)
        time.sleep(0.4)


if __name__ == "__main__":
    main()
