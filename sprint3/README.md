# Sprint 3 — dbt: install, connect, scaffold staging

Status: **Done.** dbt is installed, connected, and the real staging layer builds successfully.

This document is the sprint plan for standing up dbt against the BigQuery data Sprint 2 loaded.
Kept here for the same reason as `sprint1/README.md` and `sprint2/README.md`: progress and
decisions visible to anyone landing on the repo, not just chat history.

## Goal

Get dbt installed, connected to BigQuery, and structured with a real (if minimal) staging layer.
No parsing, typing, or aggregation logic yet — that's next sprint. This sprint proves the pipe
works: `raw.steps` in BigQuery → a dbt `source` → a trivial `stg_health__steps` view.

## Hard rules

1. **dbt's venv stays isolated.** `fitness-warehouse/dbt/.venv` is separate from
   `fitness-warehouse/.venv` (the loader's), so dbt's pinned dependencies (jinja2, click, etc.)
   never collide with the loader's.
2. **The service-account keyfile never enters the repo.** It lives outside the workspace
   entirely, at `D:\MyTracker\dbtCloud\vishactivitytracker-fdabb572e72a.json`.
3. **`~/.dbt/profiles.yml` is shared across unrelated projects.** It already held a `maven_fuzzy`
   (DuckDB) profile before this sprint touched it. Only ever append a new named profile —
   never overwrite the file.
4. **No model logic yet.** `stg_health__steps` is `select * from source(...)` — a connectivity
   proof, not a transformation. Parsing `payload` is explicitly out of scope this sprint.

## Decisions made this sprint

- **Separate `dbt/.venv`** rather than reusing the loader's `fitness-warehouse/.venv` — the
  user's explicit call, for dependency isolation.
- **VS Code dbt Power User extension** (`innoverio.vscode-dbt-power-user`) installed for model
  previews, lineage, and source/ref autocomplete.
- **Service-account auth chosen over oauth/ADC** — a deliberate deviation from Sprint 2's
  ADC-only convention. The user already had a service-account key downloaded; using it means
  dbt authenticates as a standalone identity rather than the user's own Google login. Tradeoff:
  a static credential now exists (mitigated by keeping it outside the repo) in exchange for an
  auth path that doesn't depend on interactive browser login — useful if `dbt run` is ever
  scheduled unattended.
- **`dbt_vish` is dbt's build dataset**, separate from Sprint 2's `raw` dataset — `raw` stays
  load-only (loader writes there), dbt only ever reads from `raw` and writes to `dbt_vish`.
- **`models/example/` removed.** `dbt init` scaffolds a placeholder model; deleted once the real
  `staging/` layer existed, so nothing dummy ships in the repo.

## Planned file layout

Adds a `dbt/` subtree to the existing `fitness-warehouse/` project:

```
fitness-warehouse/
├── loader/                          # Sprint 1 + 2
├── data/raw/<type>/*.ndjson         # Sprint 1
├── requirements.txt                 # Sprint 1 + 2 (loader's venv)
└── dbt/
    ├── .venv/                       # Sprint 3 — dbt's own venv, gitignored
    ├── requirements.txt             # Sprint 3 — pins dbt-bigquery
    └── fitness_warehouse/           # Sprint 3 — the actual dbt project (from `dbt init`)
        ├── dbt_project.yml
        ├── models/
        │   ├── staging/
        │   │   ├── sources.yml      # declares raw.* as dbt sources
        │   │   └── stg_health__steps.sql
        │   ├── intermediate/.gitkeep
        │   └── marts/.gitkeep
        ├── seeds/.gitkeep
        ├── macros/.gitkeep
        ├── snapshots/.gitkeep
        ├── tests/.gitkeep
        ├── analyses/.gitkeep
        └── .gitignore               # target/, dbt_packages/, logs/ (from dbt init)
```

## Step-by-step plan

**Step 0 — prerequisites.** BigQuery `raw` dataset populated (Sprint 2); a GCP service account
created with **BigQuery Data Editor** + **BigQuery Job User** on project `vishactivitytracker`,
its JSON key downloaded to a location outside any repo.

**Step 1 — install dbt.** `python -m venv dbt/.venv` inside `fitness-warehouse/`, then
`pip install -r dbt/requirements.txt` inside that venv.

**Step 2 — `dbt init`.** From `fitness-warehouse/dbt/`, run `dbt init`: project name
`fitness_warehouse`, database `bigquery`, auth method `service_account`, keyfile path to the
downloaded key, project `vishactivitytracker`, dataset `dbt_vish`, location `US`. This scaffolds
`fitness-warehouse/dbt/fitness_warehouse/` and writes (appends) a `fitness_warehouse:` profile
into `~/.dbt/profiles.yml`.

**Step 3 — verify connection.** `dbt debug` from the project folder — must end `All checks
passed!`.

**Step 4 — build the real staging layer.** Remove `models/example/`; add `models/staging/
sources.yml` (declares all 7 `raw` tables) and `models/staging/stg_health__steps.sql`
(`select * from {{ source('raw','steps') }}`); add empty `models/intermediate/`,
`models/marts/` folders for later sprints; update `dbt_project.yml`'s model config from
`example:` to `staging:`.

**Step 5 — validate.** `dbt run` builds `stg_health__steps` as a view in `dbt_vish`; row count
matches Sprint 2's `raw.steps`.

## Definition of done

- [x] `dbt-core`/`dbt-bigquery` installed in `fitness-warehouse/dbt/.venv`.
- [x] VS Code dbt Power User extension installed.
- [x] `dbt init` scaffolded `fitness-warehouse/dbt/fitness_warehouse/`.
- [x] `~/.dbt/profiles.yml` has a working `fitness_warehouse` profile; `maven_fuzzy` untouched.
- [x] `dbt debug` passes.
- [x] `models/example/` removed; `models/staging/sources.yml` + `stg_health__steps.sql` added;
      `models/intermediate/`, `models/marts/` scaffolded empty.
- [x] `dbt run` builds `stg_health__steps` successfully.
- [x] Row count in `dbt_vish.stg_health__steps` matches `raw.steps`.

## Out of scope / next sprint

- Staging models for the other 6 sources (distance, floors, active-minutes,
  active-energy-burned, total-calories, exercise).
- Intermediate daily-aggregation models, marts, KPI seeds/models.
- Scheduling/automation of `dbt run`.

## Troubleshooting

- **`dbt debug` fails with `'NoneType' object has no attribute 'close'`:** this bit us this
  sprint. Cause: `dbt init`'s keyfile prompt saved the path with **literal embedded quote
  characters** into `profiles.yml` — `keyfile: '"C:\...\key.json"'` instead of
  `keyfile: 'C:\...\key.json'` — because the quotes typed at the prompt were taken as part of
  the string rather than stripped. dbt then silently failed to load credentials, leaving the
  BigQuery client `None`. **Fix:** open `~/.dbt/profiles.yml` and remove the embedded `"`
  characters from the `keyfile:` line, leaving only the outer YAML quoting.
- **`403 Forbidden` on `dbt run`:** the service account likely lacks IAM roles on the project —
  needs at least `roles/bigquery.dataEditor` and `roles/bigquery.jobUser` on
  `vishactivitytracker` (a service account has zero access by default, unlike a user's own oauth
  login which already had access from Sprint 2).
- **`404 Not found: Dataset dbt_vish`:** expected on first run — dbt creates the dataset
  automatically if the service account has `bigquery.datasets.create` (typically included in
  `roles/bigquery.dataEditor` at the project level, but not if the role was granted narrowly on
  the `raw` dataset only).
