# Loader — how it runs

Entry point: `python loader/load.py`. Everything else here is imported by it.

## `load.py` — orchestrator

Runs once per invocation:

1. **Setup (module level).** Adds this directory to `sys.path`, imports `read`/`chunks`/`point_time`
   from `ghealth_client.py` and `write_chunk`/`last_chunk_end`/`first_chunk_start` from
   `sink_files.py`. Loads `../config.yaml` into `cfg`, resolves `out = ../data/raw`, and reads
   today's date.

2. **`main()`**, for each source listed in `config.yaml` (steps, distance, floors,
   active-minutes, active-energy-burned, total-calories, exercise):
   - Reads that source's `type`, `method`, `window_size`, `chunk_days`.
   - Calls `first_chunk_start()` and `last_chunk_end()` to see what's already on disk for this
     type, by parsing dates out of existing filenames under `data/raw/<type>/`.
   - Works out what date ranges are missing:
     - Nothing on disk yet → pull everything from `backfill_start_date` to today.
     - Something on disk → check for a **backward gap** (config start date earlier than the
       earliest file on disk) and a **forward gap** (today later than the latest file on disk).
       Either, both, or neither can apply.
   - If nothing's missing: prints `"<type> up to date"` and moves on.
   - Otherwise: splits each missing range into `chunk_days`-sized windows via `chunks()`, and for
     each chunk calls `read()` to fetch the data and `write_chunk()` to save it, printing a line
     like:
     ```
     steps  2026-06-24..2026-06-24:  1440 -> data/raw/steps/rollup_2026-06-24_2026-06-24.ndjson
     ```

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

## `sink_files.py` — talks to disk

- `write_chunk(...)` — writes one `.ndjson` file named `<method>_<c0>_<c1>.ndjson` under
  `data/raw/<type>/`, one JSON line per point:
  `{data_type, method, point_time, ingested_at, payload}`, where `payload` is the untouched
  object returned by the API.
- `last_chunk_end(...)` / `first_chunk_start(...)` — scan existing filenames in
  `data/raw/<type>/` and parse out the max end-date / min start-date already covered. This is how
  `load.py` knows what's already done vs. what's missing.

## Dependency chain

```
load.py (orchestrator)
  ├── ghealth_client.py  (fetch from ghealth CLI)
  └── sink_files.py      (resume-state + write)
        └── data/raw/<type>/*.ndjson
```
