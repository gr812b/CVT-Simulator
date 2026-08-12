# CVT Simulator black-box API E2E tests

This package is a standalone HTTP-only test harness for the updated black-box API testing guide. It assumes the backend app and database are already running, and it does not import backend code or inspect SQLite/Postgres directly.

The required product acceptance flow now uses persisted library runs and stored-input reruns:

1. `POST /runs/from-library`
2. `GET /runs/{run_id}`
3. `GET /runs/{run_id}/input`
4. `GET /runs/{run_id}/preview`
5. `GET /runs/{run_id}/result`
6. `POST /runs/{run_id}/rerun`

The legacy/direct `POST /runs` endpoint is treated as optional developer/debug regression only. It is **not called by default**.

## Files

- `cvt_black_box_api_e2e.py` — main Python harness, no third-party dependencies.
- `run_cvt_black_box_api_e2e.ps1` — PowerShell wrapper for Windows.
- `run_cvt_black_box_api_e2e.sh` — Bash wrapper for macOS/Linux/Git Bash.

## Normal run

From the folder containing the files:

```powershell
python .\cvt_black_box_api_e2e.py --api http://localhost:8000/api/v1
```

or:

```powershell
.\run_cvt_black_box_api_e2e.ps1 -Api http://localhost:8000/api/v1
```

The harness writes every request/response artifact, a `summary.json`, comparison JSON files, and `REPORT.md` under `black_box_api_artifacts/<run-tag>/` unless `--output-dir` is supplied.

## Fresh disposable dev DB run

Use this after reinitializing a throwaway SQLite dev database if you want seeded mutation checks:

```powershell
python .\cvt_black_box_api_e2e.py --api http://localhost:8000/api/v1 --full-mutating --strict
```

`--full-mutating` additionally patches a seeded tune and attempts to deprecate a pinned seeded version to verify stale/deprecated resolver behavior. Use it only on a disposable dev DB.

## Optional developer/debug direct regression

The updated guide says direct `POST /runs` is not required for product acceptance. To run it anyway:

```powershell
python .\cvt_black_box_api_e2e.py --api http://localhost:8000/api/v1 --run-direct-regression
```

This posts the frozen `/input` response to `POST /runs`, then compares the direct full result against the library result. You can override the endpoint:

```powershell
python .\cvt_black_box_api_e2e.py --run-direct-regression --direct-regression-endpoint /debug/runs
```

## Optional full-result eviction endpoint

The guide says V1 has no public admin eviction endpoint. The harness therefore treats actual eviction as a checklist/debug-only behavior unless you provide an endpoint template:

```powershell
python .\cvt_black_box_api_e2e.py --eviction-endpoint-template "/debug/runs/{run_id}/evict-full-result"
```

When supplied, the harness verifies that `/input`, `/preview`, and summary details survive eviction, then regenerates output through `POST /runs/{run_id}/rerun`.

## Useful flags

```text
--strict                       Treat soft warnings as failures.
--skip-runs                    Only test service, metadata, seed data, and lifecycle endpoints.
--skip-cache                   Skip repeated library-run cache reuse check.
--mutate-seeded-tune           Run only the seeded tune null-clear mutation.
--mutate-seeded-versions       Deprecate a pinned seeded version; disposable DB only.
--full-mutating                Run all mutation checks; disposable DB only.
--run-direct-regression        Opt in to optional direct POST /runs debug comparison.
--eviction-endpoint-template   Optional debug endpoint for full-result artifact eviction.
--no-cleanup-created           Leave created forked objects visible for inspection.
--output-dir PATH              Place artifacts somewhere specific.
--verbose                      Print tracebacks on failures.
--stop-on-first-failure        Stop immediately on the first failed check.
```

## What it validates

The harness covers the updated acceptance checklist:

- health endpoint returns HTTP 200;
- metadata endpoints return HTTP 200, with schema endpoints returning JSON objects;
- CORS permits PATCH preflight;
- seeded Baja-oriented institutions are present;
- public/default engines, CVTs, output systems, and vehicle assemblies are listed;
- archived objects are excluded from normal lists and included with `include_archived=true`;
- engine draft creation preserves draft payload and has no released version initially;
- explicit `null` clears fields while omitted fields are preserved;
- release creates an immutable version with schema/validation metadata, inertia, and visible boundary metadata;
- fork copies payload and provenance;
- deprecate updates version metadata without destroying retrievability;
- CVT fork/release preserves `tuning_schema` and avoids `cinder_assembly` nested inside `cinder_assembly`;
- output-system fork/release preserves direct secondary-shaft inertia and drivetrain/loss data;
- vehicle assembly versions visibly pin engine/CVT/output-system versions when the API exposes enough detail;
- tune/load-case/execution-preset selectors are usable;
- library-resolved runs complete and appear in persisted history;
- run detail exposes summary/stat data;
- frozen input, preview, and full result are retrievable;
- preview is downsampled relative to full output and includes first/last time points;
- persisted rerun through `POST /runs/{run_id}/rerun` reports library source, preserves the contract hash, preserves frozen input, and numerically matches original preview/result;
- repeated library run reuses cache and preserves contract hash/cache lineage when exposed;
- historical run input/preview/detail remain retrievable after archive/deprecate operations;
- optional debug eviction behavior preserves input/preview/summary and regenerates through product rerun;
- optional direct debug `POST /runs` comparison is opt-in only.

## Output interpretation

Exit code `0` means every required check passed. Warnings usually mean optional or API-detail-dependent checks were skipped or not fully visible. Exit code `1` means one or more required checks failed; open `REPORT.md` and the corresponding JSON artifact in the output folder.
