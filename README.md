# CVT-Simulator

**Authors:**
- [Kai Arseneau](https://github.com/gr812b)
- [Travis Wing](https://github.com/t-wing11)
- [Cameron Dunn](https://github.com/camdnnn)
- [Grace McKenna](https://github.com/gr4cem)

**Date of project start:** September 10, 2024

CVT-Simulator is a CVT simulation application with a React frontend, a FastAPI
backend, and the CINDER simulation model. Published deployments run entirely
from Docker images; the application source repository does not need to be
checked out on the server.

## Production Docker deployment

The repository publishes two public images to GitHub Container Registry:

```text
ghcr.io/gr812b/cvt-simulator-backend
ghcr.io/gr812b/cvt-simulator-frontend
```

The root `docker-compose.yaml` is the canonical production deployment. It runs:

```text
reverse proxy
    |
    v
cvt-frontend
    |
    | /api/v1/*
    v
cvt-backend
    |
    v
PostgreSQL 17
    |
    v
Docker named volume
```

PostgreSQL is fully containerized. You do **not** install PostgreSQL, Python,
Node, Alembic, or the CVT-Simulator repository on the server.

### Prerequisites

The deployment machine needs:

- Docker Engine
- the Docker Compose plugin (`docker compose`)
- an external Docker network used by the reverse proxy; the default name is `web`
- a reverse proxy attached to that external network
- optionally Watchtower, if automatic image updates are desired

The backend and PostgreSQL are not exposed as host ports. The frontend joins
the external `web` network so an existing reverse proxy can reach it directly.

If your reverse-proxy network is not named `web`, set `WEB_NETWORK` in `.env`
to its actual name.

### Files needed on the server

Only these deployment files are required:

```text
docker-compose.yaml
.env
```

The server does not need a Git checkout. Copy `docker-compose.yaml` from this
repository and create `.env` from `.env.example`.

For example:

```bash
mkdir -p /opt/cvt-simulator
cd /opt/cvt-simulator

# Copy docker-compose.yaml and .env.example here by your preferred method.
cp .env.example .env
```

Edit `.env`:

```dotenv
POSTGRES_PASSWORD=replace-with-a-random-url-safe-password
CVT_TAG=latest
WEB_NETWORK=web
```

A clean URL-safe password can be generated with:

```bash
openssl rand -hex 32
```

Do not commit the real `.env` file.

The PostgreSQL password is used when the database is initialized. Do not simply
change `POSTGRES_PASSWORD` later on an existing database volume; changing the
Compose variable does not automatically change the password stored inside an
already-initialized PostgreSQL database.

### Reverse-proxy network

If `web` already exists, nothing needs to be done.

Check it with:

```bash
docker network inspect web
```

If you intentionally use `web` and it does not exist yet:

```bash
docker network create web
```

If your reverse proxy already uses a differently named external Docker network,
leave that network alone and set `WEB_NETWORK` in `.env` to its name instead.

## First deployment

### 1. Pull the published images

```bash
cd /opt/cvt-simulator
docker compose pull
```

### 2. Start PostgreSQL

```bash
docker compose up -d postgres
```

Check that it becomes healthy:

```bash
docker compose ps
```

### 3. Create the schema and seed the initial library

This is the one special step for a brand-new database:

```bash
docker compose run --rm cvt-backend   sh -c "alembic upgrade head && python -m app.scripts.init_database"
```

The initializer creates the deterministic demo account and the released library
objects currently used by the frontend.

Do this once for a new database. Do **not** rerun database initialization as a
normal update step.

### 4. Start the application

```bash
docker compose up -d
```

The backend waits for PostgreSQL, applies any pending Alembic migrations, and
then starts the API. The frontend waits for the backend health check.

Check the stack:

```bash
docker compose ps
docker compose logs --tail=100 cvt-backend
docker compose logs --tail=100 cvt-frontend
```

PostgreSQL can be checked directly with:

```bash
docker compose exec postgres pg_isready -U cvt -d cvt_simulator
```

Through the configured public hostname, the API health endpoint is:

```text
https://YOUR-HOST/api/v1/health
```

The backend documentation is available at:

```text
https://YOUR-HOST/docs
```

## Normal startup and restart

Once the database has been initialized:

```bash
docker compose up -d
```

There is no separate migration command to remember. The backend container runs:

```text
alembic upgrade head
```

before starting Uvicorn on every container start. If there are no new
migrations, Alembic simply leaves the schema at the current revision.

## Automatic updates with Watchtower

Normal production uses:

```dotenv
CVT_TAG=latest
```

The existing GitHub Actions container workflow publishes new `latest` backend
and frontend images whenever `develop` is pushed.

Watchtower can continue to update those two containers exactly as before. When
a new backend image is recreated, its startup command applies pending database
migrations before the API starts.

The PostgreSQL service has this label:

```text
com.centurylinklabs.watchtower.enable=false
```

so a normal Watchtower configuration ignores the database container. PostgreSQL
is intentionally pinned to the major-version image `postgres:17-alpine`; update
the database image deliberately rather than as part of an application release.

No Git pull, source build, or server-side repository checkout is involved in
normal deployment.

## Publishing and testing an unmerged branch

The `Containerize` GitHub Actions workflow supports two paths:

- a push to `develop` publishes `latest` plus the commit SHA;
- a manual run publishes the manually supplied tag plus the commit SHA.

A manual build is not allowed to overwrite `latest`.

For PR 459, after this workflow change exists on the branch:

1. Open **Actions -> Containerize -> Run workflow**.
2. Select `model-fixes-and-contract-update`.
3. Set the image tag to `pr-459`.
4. Run the workflow.

GitHub will publish:

```text
ghcr.io/gr812b/cvt-simulator-backend:pr-459
ghcr.io/gr812b/cvt-simulator-frontend:pr-459
```

To deploy those images on the server, change:

```dotenv
CVT_TAG=pr-459
```

then run:

```bash
docker compose pull cvt-backend cvt-frontend
docker compose up -d
```

Watchtower will subsequently follow the `pr-459` tag while the containers use
that tag.

To return to the normal `develop` images:

```dotenv
CVT_TAG=latest
```

then:

```bash
docker compose pull cvt-backend cvt-frontend
docker compose up -d
```

## Updating manually without Watchtower

If Watchtower is disabled or you want to update immediately:

```bash
cd /opt/cvt-simulator
docker compose pull cvt-backend cvt-frontend
docker compose up -d
```

The backend startup handles migrations automatically.

## PostgreSQL persistence

Database files live in the Docker named volume:

```text
cvt-postgres-data
```

Normal container replacement does not delete it.

These are safe with respect to the database volume:

```bash
docker compose restart
docker compose down
docker compose up -d
```

Do **not** use this casually:

```bash
docker compose down -v
```

`-v` deletes the Compose-managed named volume and therefore deletes the
PostgreSQL database.

## Database backup

Create a plain SQL backup:

```bash
cd /opt/cvt-simulator
docker compose exec -T postgres   pg_dump -U cvt -d cvt_simulator   > "cvt_simulator_$(date +%Y%m%d_%H%M%S).sql"
```

For releases containing meaningful database migrations, making a backup before
the new backend image is deployed is recommended.

### Restore a backup

Stop application traffic first:

```bash
docker compose stop cvt-frontend cvt-backend
```

Recreate the database:

```bash
docker compose exec -T postgres   psql -U cvt -d postgres   -c "DROP DATABASE IF EXISTS cvt_simulator;"

docker compose exec -T postgres   psql -U cvt -d postgres   -c "CREATE DATABASE cvt_simulator OWNER cvt;"
```

Restore:

```bash
docker compose exec -T postgres   psql -U cvt -d cvt_simulator   < your-backup.sql
```

Start the application again:

```bash
docker compose up -d
```

## Useful operations

View all services:

```bash
docker compose ps
```

Follow backend logs:

```bash
docker compose logs -f cvt-backend
```

Follow frontend logs:

```bash
docker compose logs -f cvt-frontend
```

Follow PostgreSQL logs:

```bash
docker compose logs -f postgres
```

Restart only the application:

```bash
docker compose restart cvt-backend cvt-frontend
```

See the current database migration revision:

```bash
docker compose exec cvt-backend alembic current
```

## Development setup

The production Compose file is intentionally image-only. Local source
development remains documented by the component-specific guides:

- [`backend/README.md`](backend/README.md)
- [`frontend/README.md`](frontend/README.md)
- [`cvtModel/docs/GETTING_STARTED.md`](cvtModel/docs/GETTING_STARTED.md)

## License

This project is licensed under the **Creative Commons
Attribution-NonCommercial 4.0 International (CC BY-NC 4.0)** license.

- Free for use in personal, educational, or non-commercial projects.
- **Commercial use requires a separate license.** Please contact Kai Arseneau,
  Cameron Dunn, Travis Wing, or Grace McKenna for commercial licensing.

For more details, see the [LICENSE](./LICENSE) file.
