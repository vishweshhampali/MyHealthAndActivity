"""Sync raw.* BigQuery tables with the ghealth API: pull only what's newer than what's loaded.

Run from anywhere:  python loader/sync.py

Every data row written to raw.* carries the run_id of the raw._pipeline_runs row for
this run, and error_source is precise to the chunk (source + date range), not just
the source. On failure this still re-raises after logging, so the CI step fails
exactly as it did before.

MANUAL TARGETED RELOAD: set RELOAD_SOURCE, RELOAD_FROM, and RELOAD_TO (all three,
or none) to force-fetch one source's exact date range from the API, bypassing the
normal resume logic entirely. This APPENDS -- it does not delete any rows already
in that range (this project's BigQuery tier blocks DML), so reloading a range
you've already loaded will produce duplicate rows for that window. Exposed as
workflow_dispatch inputs (source / from_date / to_date) in the GitHub Actions UI.
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


def _reload_request():
    """Read RELOAD_SOURCE/RELOAD_FROM/RELOAD_TO from the environment. Returns
    (source, from_date, to_date) as parsed date objects, or (None, None, None)
    if none were set. Raises ValueError if only some were set."""
    src = (os.environ.get("RELOAD_SOURCE") or "").strip()
    frm = (os.environ.get("RELOAD_FROM") or "").strip()
    to = (os.environ.get("RELOAD_TO") or "").strip()
    provided = [x for x in (src, frm, to) if x]
    if not provided:
        return None, None, None
    if len(provided) != 3:
        raise ValueError(
            "Targeted reload requires source, from_date, AND to_date all set together "
            f"(got source={src!r} from_date={frm!r} to_date={to!r})"
        )
    try:
        return src, date.fromisoformat(frm), date.fromisoformat(to)
    except ValueError as e:
        raise ValueError(f"from_date/to_date must be YYYY-MM-DD: {e}")


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
    mode = "scheduled_sync"

    try:
        reload_source, reload_from, reload_to = _reload_request()

        if reload_source:
            mode = "targeted_reload"
            error_source = f"{reload_source} {reload_from}..{reload_to}"
            src_cfg = next((s for s in cfg["sources"] if s["type"] == reload_source), None)
            if not src_cfg:
                valid = ", ".join(s["type"] for s in cfg["sources"])
                raise ValueError(f"unknown source '{reload_source}' — valid sources: {valid}")

            logger.info(f"TARGETED RELOAD: {reload_source} {reload_from}..{reload_to} (manual, bypassing resume logic)")
            method = src_cfg["method"]
            window, cdays = src_cfg.get("window_size"), src_cfg.get("chunk_days", 90)
            for c0, c1 in chunks(reload_from, reload_to, cdays):
                error_source = f"{reload_source} {c0}..{c1} (targeted reload)"
                pts = read(reload_source, method, c0, c1, window_size=window)
                ndjson = build_ndjson(reload_source, method, pts, point_time, run_id=run_id)
                append_points(client, reload_source, ndjson)
                logger.info(f"{reload_source:14} {c0}..{c1}: {len(pts):5} -> raw.{reload_source.replace('-', '_')} [targeted reload]")
                total_chunks += 1
                total_points += len(pts)

            # No write_sync_state here — a targeted reload may cover a range in the
            # past and must never overwrite the real synced_through marker used by
            # the normal scheduled path.
            sources_completed = 1
            logger.info(f"{reload_source:14} targeted reload done: {total_chunks} chunks, {total_points} points")
            error_source = None  # made it through cleanly

        else:
            # Only ever sync fully-elapsed calendar days — never "today," which is
            # still accumulating sensor data at whatever time the cron happens to
            # fire. write_sync_state() marks a date permanently done, so syncing a
            # still-live "today" would lock in a partial-day undercount forever.
            sync_through = today - timedelta(days=1)

            for s in cfg["sources"]:
                dtype, method = s["type"], s["method"]
                error_source = dtype  # if we die below, this is where we were
                window, cdays = s.get("window_size"), s.get("chunk_days", 90)

                candidates = [d for d in (latest_date(client, dtype), synced_through(client, dtype)) if d]
                last = max(candidates) if candidates else None
                range_start = last + timedelta(days=1) if last else cfg_start

                if range_start > sync_through:
                    logger.info(f"{dtype:14} up to date")
                    sources_completed += 1
                    continue

                logger.info(f"{dtype:14} range to fill: {range_start}..{sync_through}")

                source_chunks = 0
                source_points = 0
                for c0, c1 in chunks(range_start, sync_through, cdays):
                    error_source = f"{dtype} {c0}..{c1}"  # precise to the chunk, not just the source
                    pts = read(dtype, method, c0, c1, window_size=window)
                    ndjson = build_ndjson(dtype, method, pts, point_time, run_id=run_id)
                    append_points(client, dtype, ndjson)
                    logger.info(f"{dtype:14} {c0}..{c1}: {len(pts):5} -> raw.{dtype.replace('-', '_')}")
                    source_chunks += 1
                    source_points += len(pts)

                # Record progress once per source (not per chunk) — the state table is tiny and this
                # is a full rewrite (load-job based; DML is blocked on this project's free tier).
                write_sync_state(client, dtype, sync_through)

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
            f"run summary: mode={mode} start={run_start.isoformat()} end={run_end.isoformat()} "
            f"duration={run_end - run_start} total_chunks={total_chunks} "
            f"total_points={total_points} status={status}"
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
                "mode": mode,
                "sources_completed": sources_completed,
                "sources_total": 1 if mode == "targeted_reload" else len(cfg["sources"]),
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
