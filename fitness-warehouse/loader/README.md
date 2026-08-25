# Loader — how it runs

Entry point: `python loader/sync.py` (run from anywhere — it locates `config.yaml` relative to
itself). Everything else here is imported by it. There's no intermediate file storage: each run
reads from the `ghealth` CLI and appends straight into BigQuery `raw.*` tables.

## `sync.py` — orchestrator

Runs once per invocation:

1. **Setup (module level).** Adds this directory to `sys.path`, loads `../config.yaml` into
   `cfg`, sets up a logger via `run_log.setup()` writing to `../logs/run_<timestamp>.log`.

2. **`main()`**, for each source listed in `config.yaml` (steps, distance, floors,
   active-minutes, active-energy-burned, total-calories, exercise):
   - Reads that source's `type`, `method`, `window_size`, `chunk_days`.
   - Calls `latest_date()` (max `point_time` already in `raw.<type>`) and `synced_through()`
     (last date recorded in `_sync_state`, in case a type has zero data points and never
     advances `latest_date`) to find where to resume from.
   - `range_start` = the later of those two, plus one day — or `backfill_start_date` from
     `config.yaml` if the table is empty/missing and no sync state exists yet.
   - If `range_start` is already past today: logs `"<type> up to date"` and moves on.
   - Otherwise: splits `[range_start, today]` into `chunk_days`-sized windows via `chunks()`,
     and for each chunk calls `read()` to fetch the data, `build_ndjson()` to encode it, and
     `append_points()` to load it into BigQuery, logging a line like:
     ```
     steps          2026-06-24..2026-06-24:  1440 -> raw.steps
     ```
   - After all chunks for a source, calls `write_sync_state()` once to record `synced_through =
     today` for that type (not per chunk — the state table is rewritten in full each time, since
     this project's BigQuery free tier blocks DML/MERGE).
   - Logs a run summary (duration, sources, total chunks, total points) at the end.

## `ghealth_client.py` — talks to the CLI

- `_run(args)` — shells out to `ghealth <args> --raw --format json`, parses the JSON response.
  Raises on non-zero exit (auth errors specifically flagged at exit code 2).
- `chunks(start, end, days)` — pure date-math generator; splits a range into `days`-sized
  inclusive windows.
- `read(dtype, method, c0, c1, window_size)` — builds the CLI command
  (`data <type> <method> --from ... --to ...`), adds `--window-size` only for `rollup`, adds
  `--limit` only for `list`, then loops on `--page-token`/`nextPageToken` until pagination is
  exhausted, collecting every point from whichever wrapper key (`dataPoints` or
  `rollupDataPoints`) is present. Decorated with `@retry` (exponential backoff, 4 attempts) for
  transient failures.
- `point_time(dtype, p)` — best-effort ISO timestamp per point (rollup `startTime`,
  daily-rollup's `civilStartTime`, etc.), used only as a keying/sort field — never touches the
  actual `payload`.

## `records.py` — builds the payload

- `build_ndjson(data_type, method, points, point_time_fn)` — encodes each point as one JSON line:
  `{data_type, method, point_time, ingested_at, payload}`, where `payload` is the untouched
  object returned by the API. Returns the whole batch as in-memory NDJSON bytes, ready for a
  BigQuery load job.

## `to_bigquery.py` — talks to BigQuery

Auth via Application Default Credentials only. Project is `vishactivitytracker`, dataset `raw`.

- `latest_date(client, data_type)` — `max(date(point_time))` already loaded for this type, or
  `None` if the table is empty/missing.
- `read_sync_state(client)` / `synced_through(client, data_type)` — read the `_sync_state` table
  (`{data_type: synced_through}`), or `{}`/`None` if it doesn't exist yet.
- `write_sync_state(client, data_type, through_date)` — rewrites the whole `_sync_state` table
  (load job with `WRITE_TRUNCATE`, not `MERGE`/`UPDATE` — DML is blocked on this project's free
  tier) with this type's `through_date` updated.
- `append_points(client, data_type, ndjson_bytes)` — loads an NDJSON buffer into
  `raw.<type>` (table name is `data_type` with `-` replaced by `_`), creating the table on first
  load. No-ops if `ndjson_bytes` is empty.

## `run_log.py` — logging setup

- `setup(logs_dir)` — creates `logs_dir` if needed, returns a logger that writes to both the
  console and a timestamped `run_<timestamp>.log` file.

## Dependency chain

```
sync.py (orchestrator)
  ├── ghealth_client.py  (fetch from ghealth CLI)
  ├── records.py         (encode points as NDJSON)
  ├── to_bigquery.py     (resume-state + load into BigQuery)
  │     └── raw.<type>, raw._sync_state   (BigQuery tables)
  └── run_log.py         (console + file logging)
```
