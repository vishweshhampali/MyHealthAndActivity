# Sprint 2 — Load raw NDJSON into BigQuery

Status: **Built and run as a separate Load stage (2026-07-xx); superseded 2026-08-23.** The
standalone `loader/to_bigquery.py` script described below (full `WRITE_TRUNCATE` reload from
on-disk NDJSON files) was replaced when the loader was rearchitected: `to_bigquery.py` is now a
library of small functions (`latest_date`, `read_sync_state`, `synced_through`,
`write_sync_state`, `append_points`) imported by `loader/sync.py`, which extracts from `ghealth`
and appends each chunk into BigQuery in the same run — there's no separate NDJSON-loading step
anymore. See `fitness-warehouse/loader/README.md` for the current design. This document is kept
for the decisions that are still in effect (project ID, dataset naming, batch-load-only, ADC-only)
and as a record of what Sprint 2 actually built.

This document is the sprint plan for the Load step of the fitness data pipeline: take the
verbatim NDJSON already landed by Sprint 1's Extract loader and land it in BigQuery with the same
fidelity, one table per data type. It's kept here for the same reason as `sprint1/README.md`:
progress and decisions visible to anyone landing on the repo, not just chat history.

## Goal

Load-only, at the time this sprint was built. No parsing, typing, or reshaping here — that's
dbt's job (Sprint 3). Each BigQuery table mirrors the on-disk NDJSON line for line: `data_type`,
`method`, `point_time`, `ingested_at`, and a verbatim `payload` JSON column. This same fixed
5-column schema is still exactly what `to_bigquery.SCHEMA` and `sync.py` write today — only the
*source* of each row changed, from on-disk NDJSON to an in-memory batch built by `records.py`
inside the same run that fetched it from `ghealth`.

## Hard rules (do not violate)

1. **Batch load jobs only.** Never streaming inserts — batch loads are free; streaming is not.
   Still true: `append_points()` in the current `to_bigquery.py` uses
   `client.load_table_from_file(...)`, a batch load job, same as here.
2. **`WRITE_TRUNCATE` per table.** As originally built: NDJSON files on disk were the source of
   truth, and re-running the script rebuilt each table from whatever files currently existed.
   **This changed 2026-08-23**: `append_points()` now uses `WRITE_APPEND` (each chunk is appended
   once, resumed via `latest_date()`/`_sync_state`, not replayed from files), and only the tiny
   `_sync_state` table still uses `WRITE_TRUNCATE` (via `write_sync_state()`), since BigQuery DML
   is blocked on this project's free tier and the state table is cheap to rewrite whole.
3. **Fixed schema, autodetect off.** Same five columns for every table, `payload` typed as JSON,
   never inferred or flattened. Still true today.
4. **ADC only.** No key files, no credentials in code or the repo. `google-cloud-bigquery` reads
   Application Default Credentials automatically. Still true today.
5. **Project ID, not display name.** Use `vishactivitytracker` everywhere in code — the GCP
   console display name ("MyHealthAndFitness") is cosmetic only. Still true today.
6. **One job per data type per chunk.** Originally: all of a type's NDJSON files were concatenated
   and loaded in a single batch job per type. Now: one load job per chunk per type (the unit of
   work `sync.py` fetches and appends), since there's no on-disk file to concatenate first.
7. **The human runs anything credentialed.** The agent writes the script; the user executes it
   in their own authenticated shell. Still true today.

## Decisions made this sprint

- Dataset `raw` (location US) in project `vishactivitytracker` was created manually in the GCP
  console — a one-time setup step, not scripted. Still the dataset `sync.py` writes to today.
- `gcloud`/`bq` CLI installed and `gcloud auth application-default login` run outside this
  session; verified this sprint that ADC's `quota_project_id` and the active `gcloud config`
  project both match `vishactivitytracker`.
- Table naming replaces hyphens with underscores (`active-energy-burned` →
  `active_energy_burned`) since BigQuery table identifiers can't contain hyphens. Still how
  `to_bigquery.table_id()` names tables today.
- Files for a type were concatenated in memory (`io.BytesIO`) rather than via temp files on disk,
  since each NDJSON file already ended cleanly on a newline and personal-scale data fit in memory
  comfortably. The in-memory-bytes approach survived the rearchitecture — `records.build_ndjson()`
  now builds that same `io.BytesIO`-ready buffer directly from fetched points instead of from
  files on disk.

## File layout as originally built (Sprint 2 — since superseded)

Added one file to the existing `fitness-warehouse/` project from Sprint 1:

```
fitness-warehouse/
├── loader/
│   ├── ghealth_client.py       # Sprint 1
│   ├── sink_files.py           # Sprint 1 — removed 2026-08-23
│   ├── load.py                 # Sprint 1 — renamed to sync.py 2026-08-23
│   ├── run_log.py              # Sprint 1
│   └── to_bigquery.py          # Sprint 2 — this sprint; rewritten 2026-08-23 to append per chunk
├── requirements.txt             # + google-cloud-bigquery
└── data/raw/<type>/*.ndjson    # input, unchanged from Sprint 1 — removed 2026-08-23
```

For the current layout (`sync.py` calling `to_bigquery.py` and `records.py` directly, no
`data/raw/`), see `fitness-warehouse/loader/README.md`.

## Step-by-step plan (as run in Sprint 2 — commands are historical)

**Step 0 — prerequisites (human).** GCP project `vishactivitytracker` exists with billing
enabled; dataset `raw` created in the console (location US); `gcloud auth application-default
login` run so ADC is configured.

**Step 1 — install dependency.** `pip install -r requirements.txt` inside `fitness-warehouse/`
with `.venv` active — adds `google-cloud-bigquery`.

**Step 2 — run the loader.** `python loader/to_bigquery.py` from `fitness-warehouse/`. For each
data type present under `data/raw/`, concatenated its files and ran one `WRITE_TRUNCATE` batch
load job into `vishactivitytracker.raw.<type>`, printing a summary line per type. (Today,
`to_bigquery.py` has no `__main__` entry point of its own — its functions are called by
`python loader/sync.py`, which is the only entry point.)

**Step 3 — validate.**

- Confirmed one summary line per data type (7 expected: steps, distance, floors, active-minutes,
  active-energy-burned, total-calories, exercise), each with a plausible file/row count.
- Ran the reconciliation query below and confirmed it returns `31711` (same figure validated in
  Sprint 1 against the CLI's own daily rollup) — this query still works unchanged against today's
  `raw.steps` table:
  ```sql
  SELECT SUM(CAST(JSON_VALUE(payload,'$.steps.countSum') AS INT64)) AS steps
  FROM `vishactivitytracker.raw.steps`
  WHERE DATE(point_time) = '2026-06-30';
  ```
- Spot-checked `raw.exercise` has session-shaped rows, not per-minute buckets.
- Re-ran the script once more with no new local files; confirmed each table reloaded cleanly with
  the same row counts (idempotent, no duplication or errors) — under the `WRITE_TRUNCATE` design
  that was in effect at the time. Idempotency under the current `WRITE_APPEND` + resume-state
  design is validated differently: re-running `sync.py` with nothing new to fetch logs
  `"<type> up to date"` per source and appends zero rows.

## Definition of done

- [x] `loader/to_bigquery.py` ran from `fitness-warehouse/` and printed a summary line per type.
- [x] All 7 tables existed under `vishactivitytracker.raw` with the fixed 5-column schema.
- [x] Steps reconciliation query returned `31711` for 2026-06-30.
- [x] `raw.exercise` contained session-shaped rows.
- [x] Re-running the script was idempotent (same result, no duplicate rows, no errors).
- [x] No credentials or key files added to the repo; `google-cloud-bigquery` used ADC only.
- [x] (2026-08-23) Extract and Load merged into `loader/sync.py`; `to_bigquery.py` rewritten from
      a standalone truncate-and-reload script into a library of resume/append functions. See
      `fitness-warehouse/loader/README.md`.

## Out of scope / next sprint

- dbt project (staging → intermediate → marts → KPIs) — Sprint 3.
- Scheduling/automation of the daily Extract → Load → dbt run — later.
- Publishing the ghealth OAuth app to "In production" so its refresh token doesn't expire —
  later, unrelated to this sprint's BigQuery work.

## Troubleshooting

- **`Permission denied` / `403` on load:** ADC may be stale or missing `bigquery.dataEditor` on
  the `raw` dataset — re-run `gcloud auth application-default login` and confirm
  `gcloud config get-value project` is `vishactivitytracker`.
- **`404 Not found: Dataset`:** the `raw` dataset hasn't been created yet in the console, or was
  created in the wrong project/location.
- **Row count looks low/high vs a chunk's expected point count:** each NDJSON line is one row —
  compare against the per-chunk count `sync.py` logs (`<type> <c0>..<c1>: <N> -> raw.<type>`).
- **`payload` column errors on load:** confirm the NDJSON `payload` field is well-formed JSON on
  every line — `ghealth`'s `--raw` output and `records.build_ndjson()` should already guarantee
  this.
