# Sprint 1 — Local Fitness Data Loader (ghealth → NDJSON files)

Status: **Built and validated as an Extract-only stage (2026-07-05); superseded 2026-08-23.** The
file-based design below (`load.py` + `sink_files.py`, writing NDJSON to `data/raw/`) was replaced
when the loader was rearchitected to extract from `ghealth` and load into BigQuery in the same
step — see `fitness-warehouse/loader/README.md` for how the loader actually works today. This
document is kept for the Extract-side decisions and rules that are still honored by the current
`sync.py`, and as a record of what Sprint 1 actually built and validated at the time.

**Loader enhancement made during Step 4:** the original resume logic (`last_chunk_end` only)
assumed backfill dates only ever move forward. Widening `backfill_start_date` to an earlier date
than what was already on disk would have silently no-opped (every source would report "up to
date" without pulling the older gap). Added `first_chunk_start` in `sink_files.py` and updated
`load.py` to fill both a backward gap (config start → earliest chunk on disk) and a forward gap
(latest chunk on disk → today) per source, so widening the backfill after an initial validation
window actually worked as intended. (The equivalent backward/forward-gap logic in the current
`sync.py` is BigQuery-based: `latest_date()` + `synced_through()` instead of filename parsing —
see `loader/README.md`.)

**Post-Step-4 addition: per-run logging.** Added `loader/run_log.py`, which configures a logger
that writes every run's output to both the console (unchanged) and a timestamped file at
`fitness-warehouse/logs/run_<YYYYmmdd>_<HHMMSS>.log` (gitignored). Each run's log captures the
existing per-chunk write lines and "up to date" lines, a new debug line per source showing the
computed backward/forward `ranges to fill` (previously invisible, making the resume logic hard to
debug), a per-source `done: N chunks, M points` line, and a final run summary (start/end time,
duration, total chunks/points written). `run_log.py` is unchanged by the later rearchitecture and
is still used as-is by `sync.py`.

This document is the sprint plan for the Extract step of the fitness data pipeline: pull personal
fitness data from the Google Health API via the local `ghealth` CLI and land it verbatim as local
NDJSON files. It's kept here so progress and decisions are visible to anyone landing on the repo,
not just tracked in chat history. This directory holds only planning documentation — no code or
config lives here.

## Goal

Extract-only, at the time this sprint was built. No warehouse, database, cloud auth, or scheduling
in this sprint — a warehouse (BigQuery or DuckDB) was chosen in Sprint 2, and by 2026-08-23 the
Extract and Load steps described in Sprints 1–2 had been merged into a single script (`sync.py`)
that reads from `ghealth` and appends straight into BigQuery per chunk, with no NDJSON files on
disk at all. This section describes the original, file-based scope as it was actually built and
validated in Sprint 1.

## Hard rules (do not violate)

Still enforced by the current `sync.py` / `ghealth_client.py` / `records.py`, even though the
on-disk mechanics changed:

1. **Verbatim raw.** Always call ghealth with `--raw`. Store each returned data point object
   untouched inside a `payload` field. Never rename, convert units, or reshape it.
2. **Correct method per metric.** steps/distance/floors/active-minutes use
   `rollup --window-size 60s` (their `list` returns valueless intervals). total-calories uses
   `daily-rollup` (API offers nothing finer). exercise uses `list`.
3. **Granularity.** steps/distance/floors/active-minutes are per-minute buckets. Do not aggregate
   in the loader.
4. **Missing days ≠ zeros.** If a date returns no points, it is simply absent. Never fabricate
   0-value rows.
5. **Idempotent + resumable.** Originally: one NDJSON file per (type, chunk); re-running
   overwrites that file, resuming from whatever chunks already exist on disk. Now: `sync.py`
   resumes from the latest `point_time` already loaded into BigQuery (or `_sync_state` for
   zero-point types) instead of parsing filenames — same idempotency guarantee, different
   mechanism.
6. **No secrets in git.** Credentials are gitignored. ghealth owns auth; do not write auth code.
7. **Do not auto-run the full multi-year backfill.** Validate on a small recent range first, and
   stop for human confirmation before widening.

## Decisions made this sprint (verified against the live `ghealth.exe` binary)

Before committing to the original draft spec, its assumptions were checked against
`ghealth.exe` directly (`--help`, `--dry-run`, `schema types --raw`) rather than trusted blindly:

- Confirmed `--raw` and `--format json` are valid global flags; `rollup` takes `--window-size`,
  `daily-rollup` takes `--window-days` instead; raw wrapper key for both is `rollupDataPoints`;
  per-type `operations`/`rollupOnly` in `schema types` matches every method chosen below
  (`floors`, `active-minutes`, `total-calories` are rollup-only; `total-calories` supports only
  `daily-rollup`; `exercise` supports `list`; `active-energy-burned` supports `rollup`).
- **Bug caught and fixed:** `total-calories daily-rollup` is capped by the live API at **14 days
  per request**, not 90 — confirmed via a live dry-run, which returned exit code 3:
  `"requested range is 91 days; the API caps total-calories rollups at 14 days per request"`.
  The original draft used `chunk_days: 90` for this source, which would have passed the small
  Step 3 validation window but broken the moment the backfill widened. Fixed to `chunk_days: 14`.
  This cap and fix are still reflected in `config.yaml` today.
- **Minor correction:** an earlier note referenced `spo2` as an example wearable-only type; the
  real registry ID is `oxygen-saturation` (no `spo2` exists in `ghealth schema types`).

## Agent Skills

Two Agent Skills from the `google-health-cli` repo are installed at
`.claude/skills/ghealth/SKILL.md` and `.claude/skills/ghealth-shared/SKILL.md` — shared
prerequisites (auth, setup, global flags) and full coverage of all 40 data types/operations. They
were copied from the local `google-health-cli/skills/` checkout, so no Node.js/npx was needed.

## File layout as originally built (Sprint 1 — since superseded)

```
fitness-warehouse/
├── config.yaml
├── requirements.txt
├── .gitignore
├── loader/
│   ├── __init__.py
│   ├── ghealth_client.py
│   ├── sink_files.py       # removed 2026-08-23
│   └── load.py             # renamed to sync.py 2026-08-23, rewritten to write BigQuery directly
└── data/raw/                # created at runtime, gitignored — no longer written; removed 2026-08-23
```

For the current layout (`sync.py`, `records.py`, `to_bigquery.py`, `run_log.py`, no `data/raw/`),
see `fitness-warehouse/loader/README.md`.

### Sources (final, corrected)

Unchanged since this sprint — still exactly what `config.yaml` runs today:

| type | method | window_size | chunk_days | note |
|---|---|---|---|---|
| steps | rollup | 60s | 1 | |
| distance | rollup | 60s | 1 | |
| floors | rollup | 60s | 1 | rollupOnly |
| active-minutes | rollup | 60s | 1 | rollupOnly |
| active-energy-burned | rollup | 60s | 1 | granular kcal; total-calories is daily-only |
| total-calories | daily-rollup | — | **14** | rollupOnly, daily-only; API caps range at 14 days/request |
| exercise | list | — | 90 | no rollup; list only |

Optional phone-available extras (not enabled yet): `activity-level` (list), `sedentary-period`
(list), `altitude` (rollup, 60s). HR-derived types (`heart-rate`, `*-zone*`, `vo2-max`, `sleep`,
`oxygen-saturation`, etc.) need a wearable and will be empty on a phone-only account — do not add
them yet.

## Step-by-step plan (as run in Sprint 1 — commands are historical)

**Step 0 — verify prerequisites.** Run
`ghealth data steps daily-rollup --from 2026-06-30 --to 2026-06-30` and confirm a data point with
`countSum` = `31711`. Exit code 2 means auth expired — run `ghealth auth login`.

**Step 1 — create project files** per the layout above.

**Step 2 — install & first run (small range).** `pip install -r requirements.txt`, then
`python loader/load.py`. With `backfill_start_date: "2026-06-24"` this pulled ~1 week; confirmed
files appeared under `data/raw/steps/`, `data/raw/exercise/`, etc. (Today: `python loader/sync.py`
loads the same range straight into BigQuery — no local files.)

**Step 3 — validate (must pass before widening).**
- Inspected a written file — each line had `data_type`, `point_time`, and a verbatim `payload`.
- Reconciliation: summed `payload.steps.countSum` across all per-minute buckets for 2026-06-30 and
  confirmed it equals `31711` (the Step 0 daily total). A short sum would suggest dropped
  pagination or too large a chunk. (The same reconciliation query, now run against
  `raw.steps` in BigQuery, is documented in `sprint2/README.md`.)

**Step 4 — widen the backfill (only after confirming Step 3).** Set `backfill_start_date` to the
earliest available date (e.g. `2024-01-01`) and re-ran; it resumed from existing files and only
pulled new chunks. Per-minute grain at `chunk_days: 1` means one API call per metric per day — a
multi-year backfill is thousands of calls. Once a real day is confirmed to return well under 1,440
buckets, `chunk_days` for the 60s metrics may be raised (e.g. to 7) to reduce call count.

## Definition of done

- [x] Project files created per the layout above (at `fitness-warehouse/`); `pip install` succeeds.
- [x] `python loader/load.py` wrote NDJSON under `data/raw/<type>/` for all 7 sources.
- [x] Lines contained verbatim `payload` + keying metadata.
- [x] June 30 per-minute step buckets summed to 31711.
- [x] Re-running resumed without re-pulling existing chunks (confirmed: all sources "up to date").
- [x] No warehouse/DB/cloud code added; `data/` was gitignored.
- [x] Backfill widened to `2026-01-01` (186 daily files for the five per-minute types, 14
      total-calories files, 3 exercise files); re-run confirmed all sources "up to date".
- [x] (2026-08-23) Extract and Load steps merged into `loader/sync.py`; `data/raw/` and
      `sink_files.py` removed. See `fitness-warehouse/loader/README.md`.

## Troubleshooting

- **Auth (exit 2):** `ghealth auth login`.
- **Empty result for a metric:** expected for wearable-only types on a phone (heart-rate, sleep,
  etc.) — those aren't in `sources`. For configured types, an empty result means no data that day
  (not an error).
- **`rollup` rejects the range:** window×span exceeds the API cap — lower `chunk_days`.
- **`daily-rollup` rejects the range:** date span exceeds that type's per-request cap (14 days for
  `total-calories`) — lower `chunk_days`.
- **Wrong values via `list`:** don't use `list` for steps/distance — use `rollup`.
