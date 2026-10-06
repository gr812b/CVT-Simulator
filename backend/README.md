# CVT Simulator backend

FastAPI provides authentication, the public configuration library, versioned
tunes/load cases, and durable simulation jobs. CINDER supplies the mechanics,
validation and result contracts. The backend freezes submitted inputs, runs them
in a separate worker, and stores results for playback and export.

See [Architecture](docs/ARCHITECTURE.md), [Database](docs/DATABASE.md), and
[API acceptance checks](docs/BLACK_BOX_TESTING.md) for the application boundaries
and maintenance workflows. Production Compose deployment is documented in the
[root README](../README.md#production-deployment).

## Local development

Use Python 3.10 or newer. From `backend/`, create and activate a virtual environment:

```bash
python -m venv venv
source venv/bin/activate
```

On Windows PowerShell, activation is `venv\Scripts\Activate.ps1` instead.
Then install the checked-out branch's requirements and initialize its database:

```bash
python -m pip install --upgrade pip
python -m pip install -r requirements-dev.txt
alembic upgrade head
python -m app.scripts.init_database
uvicorn app.main:app --reload
```

`requirements-dev.txt` includes the runtime requirements and developer tools.
`requirements.txt` is the authority for the CINDER dependency; install it from
`backend/` rather than separately choosing a model source or package version.
Reinstall requirements, or rebuild containers, after dependency changes.

In another activated backend terminal on Linux/macOS, run:

```bash
python -m app.scripts.run_worker
```

API, worker, migration and initialization commands must use the same database and
configuration. `--once` processes at most one queued job and is useful for a
controlled local check. Native Windows cannot run the worker; use WSL or the
Linux container setup below. Without a worker, accepted simulations remain queued.

The API is at `http://localhost:8000`, its health check at `/api/v1/health`, and
its current interactive reference at `/docs`. Start the frontend separately as
shown in [frontend/README.md](../frontend/README.md).

### Configuration

Defaults use `sqlite:///./cvt_simulator_dev.db`, the web origin
`http://localhost:5173`, and a local email outbox. SQLite and outbox paths are
relative to the process working directory, so run local commands from `backend/`.

[.env.example](.env.example) lists settings and limits. Python does **not** load
that file automatically. Export needed values in every API/worker/migration shell,
for example `export CVT_DATABASE_URL='sqlite:////absolute/path/cinder.db'` on
Linux/macOS or `$env:CVT_DATABASE_URL = 'sqlite:///C:/path/cinder.db'` in PowerShell.
Uvicorn also accepts `--env-file .env`, but that only configures the API process;
the worker and command-line scripts still need the same environment.

For PostgreSQL, use a `postgresql+psycopg://...` SQLAlchemy URL. Apply
`alembic upgrade head` before initializing or starting an existing database.
The initializer creates tables for disposable local databases but does not replace
Alembic's schema upgrades. Database details are in [DATABASE.md](docs/DATABASE.md).

### Linux containers on Windows or other hosts

From the repository root, with Docker running in Linux-container mode:

```text
docker build -f backend/Dockerfile -t cinder-local .
docker volume create cinder-local-data
docker run --rm -v cinder-local-data:/data -e CVT_DATABASE_URL=sqlite:////data/cinder.db cinder-local alembic upgrade head
docker run --rm -v cinder-local-data:/data -e CVT_DATABASE_URL=sqlite:////data/cinder.db cinder-local python -m app.scripts.init_database
docker run -d --name cinder-local-api -p 8000:8000 -v cinder-local-data:/data -e CVT_DATABASE_URL=sqlite:////data/cinder.db cinder-local
docker run -d --name cinder-local-worker -v cinder-local-data:/data -e CVT_DATABASE_URL=sqlite:////data/cinder.db cinder-local python -m app.scripts.run_worker
```

For an update, stop and remove both named application containers, rebuild the
image, run migrations/initialization, and recreate both using the same volume.
Removing the containers preserves `cinder-local-data`. Follow worker errors with
`docker logs -f cinder-local-worker`; a stopped Docker Desktop engine must be
started before these commands can work.

The frontend can generate contracts from an installed local backend environment.
For a Docker-only Python setup, export them from the image; this PowerShell example
runs from the repository root:

```powershell
New-Item -ItemType Directory -Force backend/generated | Out-Null
docker run --rm --mount "type=bind,source=$($PWD.Path)/backend/generated,target=/contracts" cinder-local python -m app.scripts.export_contract_artifacts --output-dir /contracts
cd frontend
$env:CINDER_SKIP_BACKEND_EXPORT = "1"
npm ci
npm run dev
```

Repeat the export after backend or CINDER contract changes.

## Accounts and password-reset email

Register a personal account through the app. The public **CINDER** sample account
has no default login password. Account identity comes from a revocable browser
session; authenticated mutations require the client and CSRF headers supplied by
the frontend. Saved library items and run content are public, while credentials,
email addresses and sessions remain private.

Local development uses `CVT_MAIL_MODE=outbox`: no email is sent. After requesting
a reset for a registered password-backed account, open the newest `.eml` file in
`backend/.local/mail` with a mail reader. To decode the latest message from a
backend terminal on any platform:

```text
python -c "from pathlib import Path; from email import policy; from email.parser import BytesParser; p=max(Path('.local/mail').glob('*.eml'),key=lambda p:p.stat().st_mtime); print(BytesParser(policy=policy.default).parsebytes(p.read_bytes()).get_content())"
```

Decode the MIME body rather than copying a possibly wrapped raw URL. The link
uses `CVT_WEB_URL`, defaults to a 30-minute lifetime, and works once. A newer
request invalidates earlier reset links. Unknown emails and passwordless accounts
receive the same generic response without generating a message. If no file is
created, check the account, the API's working directory, and `CVT_MAIL_OUTBOX`.
In the local container setup the default outbox is inside the API container at
`/app/.local/mail`; `docker cp cinder-local-api:/app/.local/mail ./local-mail`
can retrieve it. Treat these files as temporary credentials.

Production uses `CVT_MAIL_MODE=smtp` and requires an HTTPS `CVT_WEB_URL`.
Configure `CVT_SMTP_HOST`, `CVT_SMTP_FROM`, the provider's credentials, and
`CVT_SMTP_PORT`/`CVT_SMTP_SECURITY` (`587`/`starttls` or `465`/`tls`). Reset delivery
runs as an API background task, independently of the simulation worker. A generic
success response does not prove delivery; SMTP failures are logged by the API.

For an existing passwordless user, an operator who has verified ownership can
provision a password interactively:

```bash
python -m app.scripts.set_password existing-owner@example.com
```

This prompts without putting the password in command history and revokes existing
sessions/reset links. It does not create a new user. Registration and reset do
not claim an existing passwordless account.

## Samples and initialization

The initializer seeds CINDER's public library: the Kohler CH440 (Baja Restricted)
engine, McMaster 2025 CVT with Enduro 100 belt, McMaster 500 lb vehicle setup,
belt catalog, baseline/paper-inspired tunes and an execution preset.

| Load case | Road definition |
| --- | --- |
| Flat | 200 m |
| Uphill/downhill | Separate 200 m routes at +15°, +30°, −15° and −30° |
| Climb and descent | 20 m flat, 90 m at +20°, 90 m at −20° |
| Whoops | 5 m flat, eight 0.8 m-high waves at 4 m spacing, then flat to 200 m |
| Demo | 160 m retained demonstration course |

Distances follow the road surface. Whoops affect grade load; they do not simulate
suspension or jumps. The anonymous recording uses its frozen simulation input,
which remains independent of later edits to saved samples.

Run `python -m app.scripts.init_database` after migrations to add/update built-in
samples. Changed load cases receive new revisions. Old 5°/10° samples are archived
from normal pickers, while prior references and runs remain readable. Repeating
initialization does not duplicate those revisions or overwrite user copies.
Optional `--development-fixtures` adds labeled local test accounts/items; those
accounts are passwordless until provisioned.

For a disposable development SQLite database only, stop all API/worker/database
clients and use `python -m app.scripts.init_database --reset`. This deletes its
accounts, saved items and runs, including SQLite sidecar files. It refuses
production, PostgreSQL and in-memory URLs. Open-handle detection is best effort;
keep clients stopped until it finishes. A healthy database needs no reset for a
normal sample update.

## Jobs, progress and failures

Submissions freeze validated inputs and return HTTP 202. The worker claims jobs
from the database and runs CINDER in a bounded child process. One queued/running
job is allowed per account. Reusing a request key with identical content returns
the existing job; changed content with that key is rejected.

Defaults allow 300 seconds of worker wall time, 300 seconds simulated duration,
40,000 requested report samples and 4,096 MiB child memory. Course mode can finish
at the road end or stop on rollback/no progress. Actual configured limits are
exposed through API metadata; change them consistently for API and worker.

Ordinary runs and validation use a zero-clearance slotted secondary helix by
default, supporting reaction through either slot flank. CINDER's native
`contact_topology` field also permits explicit `unilateral` hardware. Older
installed wheels use the application's slotted compatibility adapter during
execution; the native package change applies the default during initial-state
classification as well. Primary flyweight contact constraints still apply.
The runtime identity records the execution policy and default helix topology,
so new runs record which policy produced their data.

Checkpoints preserve completed progress when a later timeout, cancellation or
failure occurs. An interrupted worker is recovered after its deadline and grace
period. An unfinished chunk can be lost, and failure before the first checkpoint
leaves no trajectory. Checkpoints are viewable partial results, not resumable
jobs; **Rerun frozen inputs** creates a new job. Worker logs contain the detailed
startup/solver error. New jobs do not reuse the legacy global result cache.

Run responses include a structured `outcome`: course completion or deliberate
course stop, model limit, numerical error, configuration problem, internal or
service error, cancellation, or resource limit. This is separate from the job's
lifecycle status. A course rollback/no-progress stop is a completed computation
with an incomplete course; an unfinished checkpoint or solver failure cannot be
reported as a successful run. The UI shows the last saved time/road position,
labels partial playback and exports, and explicitly identifies runs with no
saved data. Only confirmed input errors ask the user to correct configuration;
unexpected exceptions retain their detailed traceback in worker logs and show
a run ID for investigation. A handled child error exits nonzero and returns a
structured error envelope that the worker preserves.

## Contracts and checks

Generate OpenAPI and CINDER assembly/input/result schemas with:

```bash
python -m app.scripts.export_contract_artifacts --output-dir generated
```

These are generated build artifacts. Frontend scripts consume them; do not
commit generated TypeScript or create a parallel model schema.

From the activated backend environment:

```bash
python -m pytest
python -m pytest test/test_library_api.py test/test_api_journeys.py test/test_tune_preview_adapter.py
python -m pytest test/test_catalog_defaults.py test/test_scene_tip_mass.py test/test_tune_tip_mass_limits.py
python -m flake8 app
python -m black --check app
```

The preview adapter checks use explicit geometry/persistence doubles. The scene
mass and tip-limit tests use actual CINDER. Editing uses a lightweight sampled
contact preview; complete preview coverage enables submission but is not a full
construction audit. Save and run admission retain independent CINDER validation.
Manual application acceptance is described in
[BLACK_BOX_TESTING.md](docs/BLACK_BOX_TESTING.md).
