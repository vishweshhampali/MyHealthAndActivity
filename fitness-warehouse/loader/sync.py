"""Sync raw.* BigQuery tables with the ghealth API: pull only what's newer than what's loaded.

Run from anywhere:  python loader/sync.py

Step 2 of the data-quality pipeline: every data row written to raw.* now carries
the same run_id as the raw._pipeline_runs row for this run, so a suspicious row
can be traced straight back to the run that wrote it. error_source is now precise
to the chunk (source + date range), not just the source. On failure this still
re-raises after logging, so the CI step fails exactly as it did before.
"""
import os
import sys
import yaml
from datetime import date, datetime, timedelta, timezone

from google.cloud import bigquery

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ghealth_client import read, chunks, point_time   # noqa: E402
from records import build_ndjson   # noqa: E402
from to_bigquery import (   # noqa: E402
    PROJECT, latest_date, append_points, synced_through, write_sync_state, write_run_log,
)
import run_log   # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
cfg = yaml.safe_load(open(os.path.join(ROOT, "config.yaml")))
today = date.today()
logger = run_log.setup(os.path.join(ROOT, "logs"))


def _run_id():
    # GITHUB_RUN_ID is stable and unique per Actions run; local runs get a
    # timestamp-based id so two local test runs are still distinguishable.
    return os.environ.get("GITHUB_RUN_ID") or f"local-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"


def _run_url():
    server = os.environ.get("GITHUB_SERVER_URL")
    repo = os.environ.get("GITHUB_REPOSITORY")
    run_id = os.environ.get("GITHUB_RUN_ID")
    if server and repo and run_id:
        return f"{server}/{repo}/actions/runs/{run_id}"
    return None


def main():
    run_id = _run_id()
    run_start = datetime.now()
    log_started_at = datetime.now(timezone.utc).isoformat()
    cfg_start = date.fromisoformat(cfg["backfill_start_date"])
    client = bigquery.Client(project=PROJECT)
    total_chunks = 0
    total_points = 0
    sources_completed = 0
    error_source = None
    caught = None

    try:
        for s in cfg["sources"]:
            dtype, method = s["type"], s["method"]
            error_source = dtype  # if we die below, this is where we were
            window, cdays = s.get("window_size"), s.get("chunk_days", 90)

            candidates = [d for d in (latest_date(client, dtype), synced_through(client, dtype)) if d]
            last = max(candidates) if candidates else None
            range_start = last + timedelta(days=1) if last else cfg_start

            if range_start > today:
                logger.info(f"{dtype:14} up to date")
                sources_completed += 1
                continue

            logger.info(f"{dtype:14} range to fill: {range_start}..{today}")

            source_chunks = 0
            source_points = 0
            for c0, c1 in chunks(range_start, today, cdays):
                error_source = f"{dtype} {c0}..{c1}"  # precise to the chunk, not just the source
                pts = read(dtype, method, c0, c1, window_size=window)
                ndjson = build_ndjson(dtype, method, pts, point_time, run_id=run_id)
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
            sources_completed += 1

        error_source = None  # made it through every source cleanly
    except Exception as e:
        caught = e
    finally:
        run_end = datetime.now()
        log_finished_at = datetime.now(timezone.utc).isoformat()
        status = "failure" if caught else "success"

        logger.info(
            f"run summary: start={run_start.isoformat()} end={run_end.isoformat()} "
            f"duration={run_end - run_start} sources={len(cfg['sources'])} "
            f"total_chunks={total_chunks} total_points={total_points} status={status}"
        )

        record = {
            "run_id": run_id,
            "workflow": "load",
            "trigger": os.environ.get("GITHUB_EVENT_NAME", "manual"),
            "started_at": log_started_at,
            "finished_at": log_finished_at,
            "duration_seconds": (run_end - run_start).total_seconds(),
            "status": status,
            "error_source": error_source,
            "error_message": str(caught) if caught else None,
            "run_url": _run_url(),
            "details": {
                "sources_completed": sources_completed,
                "sources_total": len(cfg["sources"]),
                "total_chunks": total_chunks,
                "total_points": total_points,
            },
        }
        try:
            write_run_log(client, record)
        except Exception as log_err:
            logger.warning(f"failed to write run log to BigQuery: {log_err}")

    if caught:
        raise caught


if __name__ == "__main__":
    main()
