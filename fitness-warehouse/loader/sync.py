"""Sync raw.* BigQuery tables with the ghealth API: pull only what's newer than what's loaded.

Run from anywhere:  python loader/sync.py
"""
import os
import sys
import yaml
from datetime import date, datetime, timedelta

from google.cloud import bigquery

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ghealth_client import read, chunks, point_time   # noqa: E402
from records import build_ndjson   # noqa: E402
from to_bigquery import (   # noqa: E402
    PROJECT, latest_date, append_points, synced_through, write_sync_state,
)
import run_log   # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
cfg = yaml.safe_load(open(os.path.join(ROOT, "config.yaml")))
today = date.today()
logger = run_log.setup(os.path.join(ROOT, "logs"))


def main():
    run_start = datetime.now()
    cfg_start = date.fromisoformat(cfg["backfill_start_date"])
    client = bigquery.Client(project=PROJECT)
    total_chunks = 0
    total_points = 0

    for s in cfg["sources"]:
        dtype, method = s["type"], s["method"]
        window, cdays = s.get("window_size"), s.get("chunk_days", 90)

        candidates = [d for d in (latest_date(client, dtype), synced_through(client, dtype)) if d]
        last = max(candidates) if candidates else None
        range_start = last + timedelta(days=1) if last else cfg_start

        if range_start > today:
            logger.info(f"{dtype:14} up to date")
            continue

        logger.info(f"{dtype:14} range to fill: {range_start}..{today}")

        source_chunks = 0
        source_points = 0
        for c0, c1 in chunks(range_start, today, cdays):
            pts = read(dtype, method, c0, c1, window_size=window)
            ndjson = build_ndjson(dtype, method, pts, point_time)
            append_points(client, dtype, ndjson)
            logger.info(f"{dtype:14} {c0}..{c1}: {len(pts):5} -> raw.{dtype.replace('-', '_')}")
            source_chunks += 1
            source_points += len(pts)

        # Record progress once per source (not per chunk) — the state table is tiny and this
        # is a full rewrite (load-job based; DML is blocked on this project's free tier).
        write_sync_state(client, dtype, today)

        logger.info(f"{dtype:14} done: {source_chunks} chunks, {source_points} points")
        total_chunks += source_chunks
        total_points += source_points

    run_end = datetime.now()
    logger.info(
        f"run summary: start={run_start.isoformat()} end={run_end.isoformat()} "
        f"duration={run_end - run_start} sources={len(cfg['sources'])} "
        f"total_chunks={total_chunks} total_points={total_points}"
    )


if __name__ == "__main__":
    main()
