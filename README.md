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
worker starts after its health check succeeds.

The server needs Docker Engine, the Compose plugin, and an HTTPS reverse proxy
on an existing external Docker network. Only the frontend joins that external
network. PostgreSQL and the backend have no published host ports.

Copy `docker-compose.yaml` and [.env.example](.env.example) to the deployment
directory. Create `.env` from the example and set:

| Variable | Purpose |
| --- | --- |
| `POSTGRES_PASSWORD` | Random URL-safe database password; for example, generate with `openssl rand -hex 32` |
| `CVT_TAG` | Matching backend/frontend image tag; `latest` tracks published `develop` builds |
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

Pushes to `develop` publish `latest` and a commit tag. A manual workflow run can
publish a selected branch under a supplied non-`latest` tag. Set `CVT_TAG` to that
same tag for both application images; the worker uses the backend image too.

Back up the database before deploying a schema change. For a coordinated manual
update, pause automatic application updates if enabled, then:

```bash
docker compose pull cvt-backend cvt-worker cvt-frontend
docker compose stop cvt-worker cvt-backend cvt-frontend
docker compose run --rm cvt-backend sh -c "alembic upgrade head && python -m app.scripts.init_database"
docker compose up -d
```

Stopping an active worker can interrupt its job; allow current runs to finish
first when possible. Normal initialization updates built-in samples without a
database reset. Earlier sample revisions and user-owned copies remain available.
A restart alone does not install a newly pulled image; `up -d` recreates services
whose images changed.

Watchtower is optional. If used, include the API, worker and frontend in the
application update policy and keep their tags aligned. The PostgreSQL service is
labeled to opt out; upgrade its major version separately. Automatic container
replacement runs API migrations, but does not run the sample initializer above.

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
