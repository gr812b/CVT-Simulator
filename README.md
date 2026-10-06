# CVT-Simulator

CVT-Simulator is a web application for building CVT configurations, tuning them,
simulating a vehicle on a road, and reviewing the results. The React frontend
uses a FastAPI backend and the CINDER simulation package.

Saved physical configurations, tunes, load cases and runs are public. Sign in to
save your own items, copy another author's configuration, or submit a run.
Account email, credentials and sessions are not public. The recorded **View Demo**
page needs no account or running simulation worker.

**Authors:** [Kai Arseneau](https://github.com/gr812b),
[Travis Wing](https://github.com/t-wing11),
[Cameron Dunn](https://github.com/camdnnn), and
[Grace McKenna](https://github.com/gr4cem).
Project started September 10, 2024.

## Development

Use Python 3.10 or newer and Node.js 22. Install the backend requirements before
starting the frontend: frontend development and builds generate API types from
backend OpenAPI and CINDER schemas.

- [Backend setup, email and worker operation](backend/README.md)
- [Frontend setup, generated contracts and checks](frontend/README.md)
- [Contributing](CONTRIBUTING.md)
- [CINDER package guide](cvtModel/docs/GETTING_STARTED.md)

Run the API and a separate worker against the same database. The worker needs
Linux/macOS or a Linux Docker container; the frontend and API can run on Windows.
The normal local addresses are `http://localhost:5173` for the app and
`http://localhost:8000/docs` for the API reference.

## Production deployment

The image-only [docker-compose.yaml](docker-compose.yaml) runs PostgreSQL 17,
`cvt-backend`, `cvt-worker`, and `cvt-frontend`. The API and worker use the same
backend image. The API applies Alembic migrations before serving requests; the
worker waits for a healthy API with the same image revision before claiming jobs.

The server needs Docker Engine, the Compose plugin, and an HTTPS reverse proxy
on an existing external Docker network. Only the frontend joins that external
network. PostgreSQL and the backend have no published host ports.

Copy `docker-compose.yaml` and [.env.example](.env.example) to the deployment
directory. Create `.env` from the example and set:

| Variable | Purpose |
| --- | --- |
| `POSTGRES_PASSWORD` | Random URL-safe database password; for example, generate with `openssl rand -hex 32` |
| `CVT_TAG` | Matching backend/frontend image tag; `latest` tracks published `develop` builds |
| `CVT_WORKER_MAX_CONCURRENCY` | Maximum simultaneous simulations in the single worker container, default `1` |
| `WEB_NETWORK` | Existing reverse-proxy Docker network, default `web` |
| `CVT_WEB_URL` | Public HTTPS application origin used by sessions and reset links |
| `CVT_SMTP_HOST`, `CVT_SMTP_FROM` | SMTP server and verified sender |
| `CVT_SMTP_PORT`, `CVT_SMTP_SECURITY` | Usually `587` / `starttls`, or `465` / `tls` |
| `CVT_SMTP_USERNAME`, `CVT_SMTP_PASSWORD` | Provider credentials, when required |

Keep the real `.env` outside version control. Compose reads it automatically;
this differs from running Python directly, which reads exported environment
variables. Production requires HTTPS and SMTP. Confirm password-reset delivery
through the deployed app after configuring the provider.

The reverse proxy must share `WEB_NETWORK` and route the public hostname to
`cvt-frontend:80`. If this network does not exist, create it deliberately with
`docker network create <network-name>`. Keep an existing proxy's network name and
routing configuration when upgrading.

### First deployment

From the deployment directory:

```bash
docker compose pull
docker compose up -d postgres
docker compose run --rm cvt-backend sh -c "alembic upgrade head && python -m app.scripts.init_database"
docker compose up -d
docker compose ps
```

The initializer creates the public CINDER sample library. It does not create a
login password; register your own account. The frontend serves the app, proxies
`/api` to the backend, and exposes the backend API reference at `/docs`.
Check `https://YOUR-HOST/api/v1/health` and the worker logs after startup.

### Updates and image tags

The `Containerize` workflow publishes backend and frontend images to:

```text
ghcr.io/gr812b/cvt-simulator-backend
ghcr.io/gr812b/cvt-simulator-frontend
```

Pushes to `develop` publish `latest` and a commit tag after the reusable CI suite
and both image builds succeed. A manual workflow run uses the same checks and
can publish a selected branch under a supplied non-`latest` tag. Set `CVT_TAG` to
that same tag for both application images; the worker uses the backend image too.
Running publications finish before another release starts, so a new push cannot
cancel a release between publishing its backend and frontend tags.

### Worker capacity

`cvt-worker` is one supervisor container. It starts an isolated simulation process
for each claimed job, up to `CVT_WORKER_MAX_CONCURRENCY`, and reuses a slot as soon
as that run finishes. With no jobs there are no simulation processes. Excess jobs
remain queued in PostgreSQL. This scales compute processes inside the container;
it does not create Docker replicas or choose capacity from host CPU utilization.

For a maximum of five simultaneous runs, set this in the deployment `.env`:

```dotenv
CVT_WORKER_MAX_CONCURRENCY=5
```

Apply the environment change with:

```bash
docker compose up -d --no-deps --pull never --scale cvt-worker=1 cvt-worker
```

This also removes extra worker replicas from an earlier manual scaling setup.
Keep one worker container: the limit is per container, so extra replicas multiply
capacity. Changing `.env` requires container recreation; Watchtower preserves
the environment that the container was created with.

The default maximum is one. Choose a higher value for the host's CPU and memory;
each active child can use up to 4,096 MiB with the current settings, so five can
need roughly 20 GiB plus the API, PostgreSQL and other services. One queued or
running job per workspace remains the admission policy; parallel capacity serves
different workspaces. On SIGTERM the supervisor stops claiming new jobs and lets
all current runs finish within their existing deadlines.

### Automatic image updates with Watchtower

Keep `CVT_TAG=latest` for ordinary automatic releases. The application Compose
file opts the API, worker and frontend into Watchtower and specifies dependency
labels using Compose's existing project name. Keep the current deployment
directory/project name when upgrading; it also determines the database volume.

Merge these settings into the **existing Watchtower service's** environment,
preserving its current schedule, credentials and selection policy:

```yaml
environment:
  WATCHTOWER_LIFECYCLE_HOOKS: "true"
  WATCHTOWER_TIMEOUT: "330s"
  WATCHTOWER_ROLLING_RESTART: "false"
  WATCHTOWER_INCLUDE_RESTARTING: "true"
```

Recreate Watchtower once after editing its configuration. If its command line
already supplies the equivalent options, update those too: command-line values
take precedence over environment variables. Ensure any container-name or scope
filter includes all three application containers. PostgreSQL remains opted out.
These variables belong to Watchtower's own container, not the CINDER `.env`.

For a backend update, the dependency order stops the frontend first, then drains
the worker while the old API/database remain available, then stops the API.
Watchtower's 330-second stop timeout allows the 300-second job deadline and child
cleanup; the Compose `stop_grace_period` alone does not configure Watchtower.
On startup, the API runs `alembic upgrade head` before serving requests. Its
post-update hook waits for health; the worker independently checks health and
the baked image revision before each claim, so a failed readiness hook cannot
make it start work against a missing or mismatched API.

This provides automatic ordinary image updates, including migrations shipped in
the backend. There is a brief service interruption during replacement. A failed
migration leaves the API unavailable and jobs queued; investigate the API logs.
Watchtower does not roll back migrations. Its lifecycle hooks also need to be
enabled explicitly; a hook failure is logged but does not abort its update.

Backend/frontend tags are separate registry operations. Watchtower can briefly
see one new image before the other, and existing browser tabs can keep older
frontend code. Keep normal HTTP and database changes compatible across that
transition. Changes needing a coordinated breaking cutover, new Compose/env
settings, or sample seeding use the manual process below. Automatic replacement
does not edit the server's Compose/`.env` files or run the sample initializer.

### Manual maintenance updates

Keep database backups, especially before schema changes. For a release that
also changes Compose/configuration or built-in samples, pause automatic
application updates, apply the configuration edits, and run:

```bash
docker compose pull cvt-backend cvt-worker cvt-frontend
docker compose stop cvt-worker cvt-backend cvt-frontend
docker compose run --rm cvt-backend sh -c "alembic upgrade head && python -m app.scripts.init_database"
docker compose up -d --pull never --scale cvt-worker=1
```

The worker drains current jobs on an ordinary stop. Forced termination, host
failure, or an insufficient stop timeout can still interrupt a run; saved
checkpoints remain available. Normal initialization updates built-in samples
without a database reset. Earlier sample revisions and user-owned copies remain
available. A restart alone does not install a newly pulled image; `up -d`
recreates services whose images changed. Resume automatic updates after checking
health and logs. Upgrade PostgreSQL major versions separately.

### Persistence and backups

The Compose-managed `cvt-postgres-data` volume stores the database. Ordinary
container replacement and `docker compose down` preserve it. **`docker compose
down -v` deletes the managed volume and its accounts, configurations and runs.**
Changing `POSTGRES_PASSWORD` in `.env` does not change the password in an existing
database volume; rotate database credentials and service configuration together.

Create a SQL backup:

```bash
docker compose exec -T postgres pg_dump -U cvt -d cvt_simulator > cinder-backup.sql
```

To replace the database with that backup, stop application services first. The
following commands delete the current database before restoring the saved one:

```bash
docker compose stop cvt-worker cvt-backend cvt-frontend
docker compose exec -T postgres psql -U cvt -d postgres -c "DROP DATABASE IF EXISTS cvt_simulator;"
docker compose exec -T postgres psql -U cvt -d postgres -c "CREATE DATABASE cvt_simulator OWNER cvt;"
docker compose exec -T postgres psql -v ON_ERROR_STOP=1 -U cvt -d cvt_simulator < cinder-backup.sql
docker compose up -d
```

Use a compatible application version when restoring. For a deliberately fresh
PostgreSQL installation, create an empty database and run the migration and
initializer commands from First deployment. The initializer's `--reset` option
is only for disposable development SQLite files, not PostgreSQL.

### Diagnostics

```bash
docker compose ps
docker compose logs --tail=100 cvt-backend cvt-worker cvt-frontend
docker compose logs -f cvt-worker
docker compose exec cvt-backend alembic current
docker compose exec postgres pg_isready -U cvt -d cvt_simulator
```

If runs remain queued, check that the worker is running with the same database
and image as the API. Startup and simulation tracebacks are in the worker log;
password-reset delivery errors are in the API log. See the
[backend guide](backend/README.md) for local email and execution details.

## License

This project uses the **Creative Commons Attribution-NonCommercial 4.0
International (CC BY-NC 4.0)** license. Personal, educational and non-commercial
use is permitted under its terms. Commercial use requires a separate license;
contact the authors. See [LICENSE](LICENSE).
