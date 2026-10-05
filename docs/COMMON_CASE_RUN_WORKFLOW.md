# Common-case run workflow and durable progress

This increment follows `1196b1e`. It implements the October 2026 feedback and
supersedes older defaults and timeout notes. M5 test infrastructure and CI remain
deferred. The CINDER research preset, solver implementation, paper and recorded
simulation evidence are unchanged.

## Confirmed decisions and defaults

- Enduro 100 has an **11.5° half-angle**. Retain bottom width **16.8148 mm** and
  height **15.5702 mm**. Derive top width as **23.150385985 mm** using
  `bottom + 2 × height × tan(half-angle)`. CVT sheaves stay locked to the belt.
- One seeded CVT: **McMaster 2025**, linked to **Gaged Enduro 100**. One seeded
  engine: **Kohler CH440 (Baja Restricted)**. Other catalog belts remain available.
- Five tunes use section 4.5 and its case table in
  `docs/CVT_Module_Formulation/CVT_Module_Formulation.tex`: R00 (reference),
  W85 (85% tip mass), P300 (triple spring rate with matched engagement force),
  U55 (55% tip mass), D02 (65% tip mass and 115% primary spring compression).
  Replaceable tip adjustments preserve the 13.646 g flyweight body and update
  mass, first moment and second moment together. They use the corrected application
  belt and are examples, not reproductions of the paper's frozen result files.

## User workflow

1. Explicitly select a saved vehicle or create one. No vehicle is silently picked.
2. Select its CVT and belt. Saved vehicle, CVT and engine values appear as compact
   summaries; their editors open only when requested.
3. Select or adjust a tune in its own step after the CVT.
4. Select the primary boundary. The ordinary engine path is labelled
   **full-open-throttle (FOT)**. Advanced speed tracking shows speed against time.
5. Select or create a load case, review the persistent summary, name the run, submit.

Unchanged components retain their existing version references. Creating a vehicle
with an existing engine or CVT does not duplicate those components. New items need
an explicit name. Shared save-error alerts scroll into view, receive focus and
briefly shake; reduced-motion preferences suppress animation. Load-case creation
uses the same library header action and shared cards as other physical items.

Public cards and runs include display-name attribution, never email addresses.
Public run rows include a short setup/date summary and fixed status placement.
Pagination is centered with vertical padding. CVT cards offer **Browse tunes**;
the public CVT page places its attributed tune list near the top. Version history
stays available through secondary controls; ordinary summaries use short version
markers where necessary.

## Course and execution limits

Course finish is the default stopping mode. A maximum simulated duration still
bounds the job. The course also stops at approximately **5 m rollback from the
furthest accepted point**, or **5 s without forward progress**. A new high-water
mark of at least 5 cm resets the progress timer, avoiding numerical jitter.
Advanced controls can change or disable those two early-stop thresholds. Timed
mode runs for the specified duration and uses the selected road continuation.
Starting at or beyond the finish is rejected in course mode.

| Limit | Default |
| --- | --- |
| Wall-clock worker budget | 300 s, including child initialization |
| Maximum simulated duration | 300 s |
| New load-case maximum duration | 180 s |
| Maximum road length | 100 km |
| Maximum requested report samples | 40,000 |
| Concurrent queued/running jobs | One per account, unchanged |

Limits remain backend-owned and reach the UI through generated metadata. Queue
position is one-based among waiting jobs, ordered by submission time and ID. It
is a position, not a predicted start time; active workers are not counted.

## Partial results and recovery

The application gateway advances the existing CINDER integrator in accepted
chunks: an initial 0.1 s chunk, then up to 0.5 s each. Hybrid modes, transition
budgets and the live closure cache persist between chunks. Reporting uses a
separate system so report reconstruction cannot mutate the live solve. Cumulative
observer integrals carry forward across chunks.

Each checkpoint atomically replaces a child-side JSON file. The supervising worker
stores the latest full result and compact preview in one database transaction,
protected by its existing worker token. Saved results remain inspectable after a
wall timeout, solver failure, memory termination, cancellation or parent-worker
interruption. An interrupted worker is recovered after its hard deadline and
existing grace period, retaining its last database checkpoint.

A killed process can lose its unfinished chunk; failure before the first accepted
checkpoint has no trajectory to recover. Checkpoints are progress snapshots, not
resumable jobs. Rerun remains a new job using frozen inputs. Course finish and timed
completion are successful results. Rollback, no progress and a course time limit
keep a partial trajectory with an explicit reason. Playback and CSV use the saved
portion even when the job status is failed, cancelled or timed out. Notifications
mention available progress and **View run** retains the dismissal behavior.

## Procedural scene

The backend projects fixed-pivot roller/ramp coordinates and secondary helix
coordinates from the actual assembly. Generated API types carry these samples.
The frontend interpolates the poses and renders repeated flyweights, ramp rails,
helix rails and followers. It does not recreate their force or contact equations.
The cogs and structural thicknesses are schematic rendering details, not a
manufacturer CAD representation. Unsupported primary mechanisms omit flyweights.

The belt moves with integrated belt speed; 96 instanced cogs make travel visible.
Fixed and moving sheaves have distinct shared theme colors. Belt buffers are
reused, tension expressions are evaluated only when requested, and motion blur
uses 2–6 adaptive samples at 65% render resolution rather than up to 72 full-size
passes. Actual frame rate still depends on the user's GPU and viewport.

The landing has one fixed draggable sample with no input controls. Its corrected
belt and the retained demo's original assembly each have a small precomputed scene
artifact, so neither needs actuator initialization during a request. Input hashes
reject stale artifacts. If the assembly or visual projection changes, regenerate:

```bash
cd backend
python -m app.scripts.build_scenes
```

This does not run a simulation or alter the recorded demo. Explicit demo
regeneration also refreshes the scenes. Ordinary run playback projects its frozen
assembly and caches the result in a bounded backend cache. Appearance, renderer
options and playback controls remain shared.

## Local setup

Stop the API and worker first. This update intentionally needs a fresh development
database; there is no compatibility migration for old scenario/seed contracts.
From the repository root:

```bash
cd backend
source venv/bin/activate
python -m app.scripts.init_database --reset
uvicorn app.main:app --reload
```

The reset deletes accounts, saved items and runs in the selected development
SQLite database. Register again afterward. In a second backend terminal with the
same virtual environment and `CVT_DATABASE_URL`:

```bash
python -m app.scripts.run_worker
```

In a frontend terminal:

```bash
cd frontend
npm install
npm run dev
```

No new dependencies are required. Development/build regenerates transport types.
If an existing environment sets `CVT_RUN_TIMEOUT_SECONDS=120` or
`CVT_RUN_MAX_DURATION_SECONDS=120`, update it to 300. The example environment and
Compose worker/API configuration now use the increased default. `/demo` needs only
the API and frontend.

## Verification and maintenance

- Fresh database: one default CVT/engine, corrected belt, five valid sample tunes,
  unchanged component references reused on save.
- Real simulations: exact 2 m course finish; stationary stop at 5.0 s; uphill
  rollback stop at -5 m; hard wall timeout with retained playable progress.
- Real worker cancellation and forced parent interruption both retain checkpoints
  and publish their final stop reasons.
- Browser walkthrough at 1440 px and 390 px: empty vehicle selection gate,
  collapsed editors, separate tune selection, speed profile, review/queue/cancel,
  required load-case name, injected save failure focus, successful save, attributed
  public tunes, partial CSV/playback, scene modes and responsive layout.
- Generated contracts, TypeScript production build, targeted ESLint, Python
  syntax/import lint and patch whitespace checks. The existing large-bundle warning
  remains. Software-rendered 3D was inspected; hardware frame-rate targets were
  not asserted.

Maintain reusable Mantine components, centralized theme tokens, generated API
contracts and the existing backend/CINDER boundary. No unit-test suite, committed
E2E harness, CI changes, push or deployment is part of this increment.
