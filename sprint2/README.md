# Sprint 2 — Load raw NDJSON into BigQuery

Status: **Built, not yet run.** Script written; the human runs it (touches live credentials/cloud
state — never handed to the agent).

This document is the sprint plan for the Load step of the fitness data pipeline: take the
verbatim NDJSON already landed by Sprint 1's Extract loader and land it in BigQuery with the same
fidelity, one table per data type. It's kept here for the same reason as `sprint1/README.md`:
progress and decisions visible to anyone landing on the repo, not just chat history.

## Goal

Load-only. No parsing, typing, or reshaping here — that's dbt's job, next sprint. Each BigQuery
table mirrors the on-disk NDJSON line for line: `data_type`, `method`, `point_time`,
`ingested_at`, and a verbatim `payload` JSON column.

## Hard rules (do not violate)

1. **Batch load jobs only.** Never streaming inserts — batch loads are free; streaming is not.
2. **`WRITE_TRUNCATE` per table.** NDJSON files on disk are the source of truth. Re-running the
   script rebuilds each table from whatever files currently exist — idempotent by design, no
   append/dedupe logic needed here.
3. **Fixed schema, autodetect off.** Same five columns for every table, `payload` typed as JSON,
   never inferred or flattened.
4. **ADC only.** No key files, no credentials in code or the repo. `google-cloud-bigquery` reads
   Application Default Credentials automatically.
5. **Project ID, not display name.** Use `vishactivitytracker` everywhere in code — the GCP
   console display name ("MyHealthAndFitness") is cosmetic only.
6. **One job per data type.** All of a type's NDJSON files are concatenated and loaded in a
   single batch job, avoiding per-file job overhead.
7. **The human runs anything credentialed.** The agent writes the script; the user executes it
   in their own authenticated shell.

## Decisions made this sprint

- Dataset `raw` (location US) in project `vishactivitytracker` was created manually in the GCP
  console — a one-time setup step, not scripted.
- `gcloud`/`bq` CLI installed and `gcloud auth application-default login` run outside this
  session; verified this sprint that ADC's `quota_project_id` and the active `gcloud config`
  project both match `vishactivitytracker`.
- Table naming replaces hyphens with underscores (`active-energy-burned` →
  `active_energy_burned`) since BigQuery table identifiers can't contain hyphens.
- Files for a type are concatenated in memory (`io.BytesIO`) rather than via temp files on disk,
  since each NDJSON file already ends cleanly on a newline and personal-scale data fits in memory
  comfortably.

## Planned file layout

Adds one file to the existing `fitness-warehouse/` project from Sprint 1:

```
fitness-warehouse/
├── loader/
│   ├── ghealth_client.py       # Sprint 1
│   ├── sink_files.py           # Sprint 1
│   ├── load.py                 # Sprint 1
│   ├── run_log.py              # Sprint 1
│   └── to_bigquery.py          # Sprint 2 — this sprint
├── requirements.txt             # + google-cloud-bigquery
└── data/raw/<type>/*.ndjson    # input, unchanged from Sprint 1
```

## Step-by-step plan

**Step 0 — prerequisites (human).** GCP project `vishactivitytracker` exists with billing
enabled; dataset `raw` created in the console (location US); `gcloud auth application-default
login` run so ADC is configured.

**Step 1 — install dependency.** `pip install -r requirements.txt` inside `fitness-warehouse/`
with `.venv` active — adds `google-cloud-bigquery`.

**Step 2 — run the loader.** `python loader/to_bigquery.py` from `fitness-warehouse/`. For each
data type present under `data/raw/`, concatenates its files and runs one `WRITE_TRUNCATE` batch
load job into `vishactivitytracker.raw.<type>`, printing a summary line per type.

**Step 3 — validate.**

- Confirm one summary line per data type (7 expected: steps, distance, floors, active-minutes,
  active-energy-burned, total-calories, exercise), each with a plausible file/row count.
- Run the reconciliation query below and confirm it returns `31711` (same figure validated in
  Sprint 1 against the CLI's own daily rollup):
  ```sql
  SELECT SUM(CAST(JSON_VALUE(payload,'$.steps.countSum') AS INT64)) AS steps
  FROM `vishactivitytracker.raw.steps`
  WHERE DATE(point_time) = '2026-06-30';
  ```
- Spot-check `raw.exercise` has session-shaped rows, not per-minute buckets.
- Re-run the script once more with no new local files; confirm each table reloads cleanly with
  the same row counts (idempotent, no duplication or errors).

## Definition of done

- [ ] `loader/to_bigquery.py` runs from `fitness-warehouse/` and prints a summary line per type.
- [ ] All 7 tables exist under `vishactivitytracker.raw` with the fixed 5-column schema.
- [ ] Steps reconciliation query returns `31711` for 2026-06-30.
- [ ] `raw.exercise` contains session-shaped rows.
- [ ] Re-running the script is idempotent (same result, no duplicate rows, no errors).
- [ ] No credentials or key files added to the repo; `google-cloud-bigquery` uses ADC only.

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
- **Row count looks low/high vs Sprint 1's on-disk file count:** each NDJSON line is one row —
  compare against `wc -l` on the concatenated files for that type, not file count alone.
- **`payload` column errors on load:** confirm the NDJSON `payload` field is well-formed JSON on
  every line — the loader's `--raw` output should already guarantee this from Sprint 1.
