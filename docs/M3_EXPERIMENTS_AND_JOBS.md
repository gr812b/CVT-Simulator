# M3 — Revisioned experiments and durable simulation jobs

> Current setup and visibility policy: [Public workspace refinements](PUBLIC_WORKSPACE_REFINEMENTS.md). This historical milestone document may describe superseded private-data or migration behavior.

M3 completes the tune/scenario/run milestone from the implementation baseline. CINDER 1.1.4 remains pinned and owns the mechanics. This milestone does not change the research formulation, add a unit-test suite, or change testing CI.

## User workflow

**Tune & run** separates a saved vehicle setup, tuning values, and a scenario. A tune pins an exact setup revision. Selecting an older tune does not silently upgrade its hardware; the editor shows the pinned revision and offers an explicit fresh tune on the latest setup.

Tunes and scenarios support named saves, rename through the name field, Save as/Duplicate, archive/unarchive, revision differences, and restore as a new revision. Saved revisions are immutable. Unchanged saves do not add duplicates. Stale saves receive a conflict. Sample records are read-only until copied; personal records remain private.

The tuning surface comes from the selected assembly's supported parameters. Fixed-pivot flyweight mass scales all first/second/product mass moments by the same factor, preserving the existing shape and mass distribution. It is not the old point-mass slider. Ramp/helix fields derive from CINDER's assembly schema. Unsupported legacy tuning keys are rejected explicitly; **Reset values to setup defaults** is a deliberate way to start from supported values.

| Run action | Tune behavior | Scenario and run-only overrides |
| --- | --- | --- |
| Run unsaved values | Does not write a tune revision. | Frozen exactly as submitted. |
| Save and Run | Saves the current owned tune, then submits it. | Frozen; not implicitly saved as a named scenario. |
| Save as New Tune and Run | Creates a separate named tune, then submits it. | Frozen; not implicitly saved as a named scenario. |

The scenario has its own Save action. A failed admission after Save and Run does not undo a successful tune save; the saved tune and run submission are explicit separate operations. Empty or invalid quantities block submission. Unsaved navigation asks before discarding work; a successful run submission can leave immediately because its values have been frozen.

## Road contract

The backend resolves the same road definition for both the editor preview and the frozen CINDER input. The frontend never substitutes its own interpolation or hill formulas.

| Convention | Definition |
| --- | --- |
| Distance | Signed vehicle travel along the road, consistent with CINDER's wheel/final-drive coordinate; not horizontal map distance. |
| Elevation | Relative to the route start. Each section starts at local `(0, 0)`. |
| Section joins | Continuous position/elevation. Resizing or reordering a section translates later sections. |
| Interpolation | Straight elevation segments in road distance. Each segment becomes `asin(Δelevation / Δdistance)`, a constant grade. |
| Rounded features | Eight linear segments per crest/dip/whoop cycle. These are construction samples, not hidden spline smoothing. |
| Triangular features | Two linear segments per cycle. |
| Before the start | The first grade extends backwards, matching CINDER. |
| After the end | Explicit choice: flat road (default) or continuation of the final grade. |
| Physics scope | Road grade load only. No suspension dynamics, tire lift, impacts, or airborne motion. |

Users can add flat, climb, descent, crest, dip, repeated whoops, or custom-point sections. Whoops expose height, spacing, count and shape together. Sections can be reordered, duplicated, deleted and edited. Points support dragging, keyboard arrows, an exact-coordinate picker, insertion and removal. Editing a generated feature's points converts only that section to custom points; Undo restores its parameterized definition. Undo/redo retains up to 60 local edit states. The road chart pans horizontally on narrow screens; numerical editing remains accessible without dragging.

Grade changes are abrupt at joins. Short features can need a smaller maximum solver step. Plot axes use different physical scales and should not be interpreted as a scale drawing of slope. Initial engine/secondary/belt speeds, shift state and road distance are editable, with advanced numerical controls separate from ordinary physical inputs.

## Durable execution

All simulation endpoints—experiment, legacy library, direct/debug, validation and rerun—use one database queue. Submission performs bounded-input checks and CINDER preflight, freezes input, commits a queued run, and returns HTTP 202 with its ID. Integration is never performed by the HTTP request or API process. First-time fixed-pivot preflight can still take several seconds; identical pure preflight reports use a bounded in-process cache, not a simulation-result cache.

The frozen record contains the canonical executable case, source revisions, submitted tuning values, editable scenario, resolved road, temporary mass override, numerical controls, execution-profile options and CINDER package/input/result contract versions. Its hash includes canonical host and shaft boundaries, solver identity and execution options. Rerunning uses the original frozen input, creates a new run with a parent link, and records the currently installed solver. A worker with a different solver version from submission fails clearly instead of mislabeling the result.

There is **one queued or running job per account/workspace**, including requests from different users in that workspace. The account row serializes admission; a second tab or concurrent request cannot allocate another slot. A request key (16–64 characters; UUID recommended) is unique per account: the same key and payload return the same run, while reuse with different content returns 409. Accepted submissions have a rolling rate limit; rejected/invalid attempts also have a separate, independently committed fixed-window throttle. Ordinary previewing/saving is not a job submission.

The standalone worker claims queued jobs with compare-and-swap, then executes one isolated child process. Multiple workers can share the queue. A worker token fences all completion writes. The database clock owns lease deadlines; each child gets a conservative local monotonic deadline, avoiding cross-host wall-clock skew. The child arms POSIX `SIGALRM` before importing CINDER, applies output-file limits, disables core dumps, and uses one BLAS thread. Linux additionally caps address space and kills the child when its worker parent dies. The [post-M4 worker fix](DEMO_AND_WORKER_TROUBLESHOOTING.md) adds resident-memory monitoring on Linux and macOS, with bounded startup diagnostics in the worker log.

Lifecycle states are `queued`, `running`, `completed`, `failed`, `timed_out` and `cancelled` (the old `validating` transport value remains readable). Queued cancellation is immediate. Running cancellation requests shutdown and retains the slot until the child has been killed and reaped. An orphaned running record is failed only after its hard deadline plus recovery grace; stale workers cannot overwrite a terminal result. Expired queued work is also released. Retries are deliberate new runs, not an automatic retry loop. There is no invented progress percentage.

Results and lightweight previews are persisted with the existing artifact contract. Old cached artifacts remain readable, but new jobs do not reuse the old global cache or expose another account's private result. If a full result is unavailable, the frozen input remains available for a new rerun.

## Activity and results

An app-wide Activity control shows active work, recent runs and unread completion/failure/cancellation updates. Updates are persisted per user, including separate read state for users sharing one workspace. Reading someone else's notice is denied. Polling refreshes the UI; closing a tab or restarting the API does not cancel execution. Returning users can open the saved run and reload `/playback?run=<id>` directly.

`/runs/:runId` provides honest status, cancellation, a frozen-input/solver identity panel, a parent-run link and result playback or rerun. [M4 adds the searchable results/history/export workflow](M4_RESULTS_AND_PUBLIC_LIBRARY.md). Multi-run comparison, public tune/run discovery, email and browser-push delivery remain deferred.

## Run locally and deploy

After installing the existing pinned dependencies, use the same `CVT_DATABASE_URL` for all processes:

```bash
cd backend
source venv/bin/activate
alembic upgrade head
python -m app.scripts.init_database
uvicorn app.main:app --reload
```

In a second backend terminal:

```bash
source venv/bin/activate
python -m app.scripts.run_worker
```

In a frontend terminal:

```bash
cd frontend
npm ci
npm run dev
```

`python -m app.scripts.run_worker --once` processes at most one queued job. The worker requires POSIX hard-deadline support; on Windows, use the Linux backend container or a Linux development environment. The deprecated `CVT_RUN_EXECUTOR_MODE` compatibility option no longer enables inline execution. If no worker is running, jobs remain visibly queued until a worker starts, the user cancels, or the queue timeout expires.

Production Compose adds `cvt-worker` using the same backend image/environment, sharing PostgreSQL. It starts after the API's migration/health check and drains a bounded active child during normal shutdown. Keep API and worker images/configuration aligned. No Redis or extra runtime package is required. Follow worker logs with `docker compose logs -f cvt-worker`.

### Central limits

Configuration lives in `app/core/settings.py`; `backend/.env.example` lists the environment names. API metadata exposes user-facing limits rather than requiring frontend copies.

| Setting (`CVT_` prefix) | Default |
| --- | --- |
| `RUN_TIMEOUT_SECONDS` | 120 s wall time, including child startup |
| `RUN_QUEUE_TIMEOUT_SECONDS` | 3,600 s |
| `RUN_RECOVERY_GRACE_SECONDS` | 15 s after hard deadline |
| `RUN_SUBMISSION_LIMIT` / `RUN_SUBMISSION_WINDOW_SECONDS` | 6 accepted jobs / 60 s; attempts capped at four times that limit |
| `RUN_MAX_DURATION_SECONDS` | 120 simulated seconds |
| `RUN_MAX_REPORT_SAMPLES` | 20,000 |
| `RUN_MAX_INPUT_BYTES` / `RUN_MAX_RESULT_BYTES` | 2,000,000 / 64,000,000 |
| `RUN_MEMORY_LIMIT_MB` | 4,096 per child resident memory; Linux also caps address space |
| `ROAD_MAX_FEATURES` / `ROAD_MAX_SEGMENTS` | 64 / 512, including any flat endpoint segment |
| `ROAD_MAX_DISTANCE_M` / `ROAD_MAX_GRADE_DEGREES` | 100,000 m / 60° |
| `WORKER_POLL_SECONDS` | 1 s |

Structural schema bounds also apply: up to 32 whoops per section, finite ordered points, and explicit tolerance/initial-state ranges. Configuration can tighten the structural feature limit, not expand past the schema cap. Resource limits apply to worker execution; production load testing and broader preflight/service hardening remain release work.

### Upgrade and rollback

Take a verified database backup and stop/drain the pre-M3 API processes before applying migration `20261004_0007`. Do not perform this first upgrade underneath still-running synchronous M2 computations. The migration preserves old design revisions, run inputs/artifacts and original tune rows. It copies legacy named tunes to immutable revision 1, pinned to the setup current at upgrade. Unsupported legacy values are preserved for review, not silently discarded. Interrupted pre-M3 active records become failed with a migration notice so they cannot block a workspace forever.

Start the new API and worker after migration. Normal seeding adds flat, climb/descent and whoops scenarios plus a two-revision illustrative tune; the whoops example also has revision history. Repeated seeding skips existing objects. Optional `--development-fixtures` adds passwordless private accounts and clearly labeled queued/failed/cancelled records. A queued fixture is real work that the worker may execute; no completed result is fabricated. Existing fixture records are never reset.

Downgrade deliberately refuses to discard durable history. Rollback means restoring the verified pre-M3 backup with the compatible application version. The migration was exercised on fresh SQLite and an M2 database; real PostgreSQL/container release verification remains outstanding.

## Contracts and maintenance

- `schemas/experiments.py` and `schemas/runs.py`: generated API contracts. The ramp union is embedded from CINDER, not copied into TypeScript.
- `application/roads.py`: one deterministic intent-to-grade resolver for preview and execution.
- `application/experiment_tuning.py` and `experiments.py`: effective tuning fields, strict value application, immutable saves and access-aware resolution.
- `application/jobs.py`: atomic admission, lifecycle fencing, recovery and per-user notices. `scripts/run_worker.py` and `run_child.py`: supervision and bounded computation.
- `database/runs.py`: result/artifact storage and read-only legacy-cache compatibility. The old synchronous runner and process-local run store have been removed.
- `features/experiments`: reusable editor/history/activity components; Mantine controls, the shared quantity validator, shared transport and centralized theme remain in use. Signed-in dashboard shortcuts submit background jobs. The public demo now opens a retained result without submitting work.

Old `POST/PATCH /library/tunes` writes now return 410 with a pointer to the revisioned API; old reads are retained for compatibility. Every run submission/rerun requires `request_key`. Regenerate contracts through the ordinary frontend build; do not edit generated files. Existing legacy black-box scripts must be adapted to these contracts and a real worker during M5, not treated as current passing coverage.

## Verification record and milestone boundary

Focused disposable acceptance checks were run outside the repository; no test suite or CI was added.

- Generated contracts, TypeScript/production build, frontend lint and targeted Python lint/format checks. Two existing hook warnings remain in the primary-design/validation views; there are no new lint errors or warnings.
- Tune saves, no-op/stale saves, immutable restore/diffs, private access, resolved preview equality, exact frozen road/mass overrides and an actual completed CINDER worker run.
- Two simultaneous users in one account; simultaneous idempotent retries; debug/validation admission bypass attempts; accepted-job throttling; private run access; independent per-user notice read state.
- Queued and running cancellation, independent child timeout, killed-worker recovery, stale completion rejection and queued expiry.
- Fresh migration and M2 upgrade with original revision/tune/run/artifact fields preserved; repeated normal and opt-in fixture seeding preserving every existing row and local edit.
- Desktop and 390 px browser walkthrough: tune history and generated ramp fields; whoops parameters; section duplicate/reorder/delete; undo/redo; mouse dragging; keyboard and numeric point edits; save/reopen; blank-input blocking and unsaved-navigation confirmation; all three run actions, including an unsaved run without overwriting its saved tune; exact mass-override persistence; queued cancellation; archive/unarchive and tune duplication; closing the tab; returning to a persistent completion notice; playback and playback reload.

M1–M3 are implemented. [M4 implements the wider results and public vehicle/CVT library workflow](M4_RESULTS_AND_PUBLIC_LIBRARY.md). M5 remains broad E2E coverage, CI integration, release-environment verification and hardening. This milestone does not publish images, push the branch, or deploy the application.
