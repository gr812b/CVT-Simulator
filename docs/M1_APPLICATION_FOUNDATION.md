# M1 — Application foundation

This milestone implements the account and application foundation in the agreed CINDER web application baseline. CINDER remains the mechanics authority. The existing solver and research formulations are unchanged.

## Delivered scope

- Email/password registration creates one free personal account with an owner membership.
- Sign-in, server-side sessions, sign-out, profile editing, password changes, and password reset.
- Password changes rotate the current session and revoke other sessions and reset links. Reset links are single-use and expire after 30 minutes by default.
- Protected application routes, responsive navigation, workspace landing page, account screens, visible loading/error states, and return to the requested page after sign-in.
- Mantine (MIT) supplies shared controls and accessible form primitives. `frontend/src/styles/theme.ts` owns the palette, typography, component defaults, and aliases used by the existing engineering views.
- The OpenAPI-generated client covers every frontend API call. Backend response projections now describe engineering results and editor metadata; frontend API types derive from generated contracts. Assembly, simulation-case, and result types still come from CINDER's own schemas.
- Ownership checks cover library drafts, released versions and their dependencies, tunes, load cases, execution presets, persisted and direct runs, validation workspaces/snapshots, and cached primary-design analyses.
- Public/unlisted released designs can be read or forked where permitted. Other users cannot read private drafts, mutate shared objects, or access someone else's runs. Cross-account failures use not-found responses. Viewer memberships cannot perform writes.
- The server derives account and author identity from the session. API writes reject submitted identity overrides. Seed/demo identity constants are removed from the frontend.
- New validation workspaces use an accessible sample baseline. Bundled legacy presets are normalized through the existing contract adapter before reaching the generated frontend types. Legacy tuning paths follow the assembly’s actual mount names and omit fields that its hardware does not support; fixed-pivot mass geometry is not treated as the old point-mass slider.

## Run locally

Requires Python 3.12 and Node 20 or later. From the repository root:

```bash
cd backend
python3 -m venv venv
source venv/bin/activate
python -m pip install -r requirements.txt
alembic upgrade head
python -m app.scripts.init_database
uvicorn app.main:app --reload
```

In another terminal:

```bash
cd frontend
npm ci
npm run dev
```

Open `http://localhost:5173` and create an account. Vite proxies `/api` to port 8000. `VITE_API_BASE_URL` can stay unset; there are no user/account IDs to configure.

`npm run dev` and `npm run build` regenerate OpenAPI and CINDER types. The generator uses `backend/venv`, or `CINDER_BACKEND_PYTHON` when explicitly set. Generated files are build artifacts and must not be edited by hand.

The existing seed adds public vehicle baselines and load cases plus a system execution preset. Personal tunes remain private. A newly registered account starts with baseline tuning and can create a personal tune from the published parameter paths. [M2 now provides the physical library editors, expanded sample seed, and revision workflows](M2_PHYSICAL_LIBRARY.md).

### Local password-reset mail

Development defaults to a private outbox at `backend/.local/mail`. Open the latest `.eml` file in a mail reader, or decode its message body with Python:

```bash
python - <<'PY'
from email import policy
from email.parser import BytesParser
from pathlib import Path
latest = max(Path('.local/mail').glob('*.eml'), key=lambda p: p.stat().st_mtime)
print(BytesParser(policy=policy.default).parsebytes(latest.read_bytes()).get_content())
PY
```

Use the link in that message. Raw MIME files can wrap a long URL; decode the message instead of copying an encoded line. Reset tokens travel in the URL fragment, are removed from the browser address after capture, and are never put in HTTP access-log query strings. Outbox files are excluded from git and created with owner-only permissions.

### Existing accounts and migrations

`alembic upgrade head` preserves existing users and data. Old users have no password until an operator provisions one. Registration and password reset cannot claim a legacy passwordless account. After verifying ownership, an operator can run:

```bash
python -m app.scripts.set_password existing-owner@example.com
```

This prompts for a password without putting it in shell history. It revokes existing sessions and reset links. There is no default seed password.

The migration stops if existing email addresses collide after case normalization; resolve those accounts deliberately before retrying. Fresh installs are handled despite the original migration's use of live ORM metadata. Downgrading the auth migration removes credentials and sessions; it is not a routine rollback procedure.

## Production configuration

The existing Compose configuration now requires:

- `CVT_WEB_URL`: the public HTTPS application origin.
- `CVT_SMTP_HOST`, `CVT_SMTP_FROM`, and provider credentials when needed.
- `CVT_SMTP_PORT` and `CVT_SMTP_SECURITY` (`starttls` on 587 by default, or `tls` on 465).

Examples are in the root `.env.example` and `backend/.env.example`. Keep secrets outside git. Compose sets production mode, requires SMTP, runs migrations before startup, and stops startup if migration fails. The frontend and API should share an origin behind the existing reverse proxy. CORS origins must be explicit for a separate development origin.

Production cookies are HttpOnly, Secure, and SameSite=Lax, scoped to `/api`. Sessions expire after seven days by default and are stored as hashed random tokens. Passwords use Argon2. Unsafe authenticated requests require a session-bound CSRF token and the client header; auth mutations also check the browser origin. Password-reset responses do not reveal whether an email is registered. Auth limits are stored in the database, so failures and worker restarts do not reset them. Configure trusted proxy forwarding correctly so IP limits identify clients rather than an arbitrary forwarded header.

Production SMTP delivery and the real deployment database must be checked in the deployment environment before release. This branch does not deploy the application.

## Coding standards for subsequent milestones

1. Keep physics and mechanics in CINDER. Backend code owns transport, application workflows, authorization, and persistence; UI code owns interaction and presentation.
2. Define API request/response contracts in the backend, regenerate the client, and derive frontend view models with indexed types, `Pick`, or `Omit`. Do not re-declare transport interfaces or bypass the shared API transport with raw fetch calls. Local editing state is allowed; it must not invent a second mechanics model.
3. Use Mantine controls and the central theme. Prefer a small reusable composition over copied button, form, loading, and error implementations. Existing engineering views can migrate incrementally.
4. Derive identity from the session and check every referenced resource before resolving or mutating it. Filtering a list alone is not authorization. Shared releases must not expose private drafts or dependency payloads.
5. Keep private snapshots out of unscoped persistent browser storage. Account changes must reset private UI state. Never log passwords, tokens, or reset links.
6. Add explicit migrations. Preserve existing data unless a separately authorized migration requires otherwise. Keep setup commands reproducible and fail clearly when prerequisites are missing.
7. Prefer focused changes and clear failure states. Document material limits and decisions in the repository.
8. Do not add a unit-test suite or change testing CI during M1–M4. Use builds, type checking, linting, and focused manual checks while implementing. Establish E2E coverage and CI in M5 once the workflows exist.

## Milestone boundaries

| Milestone | Scope |
| --- | --- |
| M1 | Accounts, ownership, application shell, shared theme/components, generated API contracts. |
| M2 | Physical library editors, belts, immutable revisions, and a useful set of default sample records. |
| M3 | Revisioned tunes/scenarios and custom hills, approachable point/feature editing (including repeated whoops), durable jobs independent of HTTP requests, completion notifications, and one outstanding queued/running job per account/workspace. Implemented in [M3](M3_EXPERIMENTS_AND_JOBS.md). |
| M4 | Results workflow and public vehicle/CVT library. Implemented in [M4](M4_RESULTS_AND_PUBLIC_LIBRARY.md). Multi-run comparison is future work; public tunes/runs are lower priority. |
| M5 | E2E coverage, CI integration, and release hardening. Unit tests are not the focus. |

M1 originally retained synchronous persisted-run execution. [M3](M3_EXPERIMENTS_AND_JOBS.md) replaces it with a standalone durable worker, completion notices and the one-outstanding-run policy; local simulation development now requires that worker. Process-local engineering-study caches remain separate. Email verification, teams/invitations, billing, social login, and account deletion are outside these milestones.

## Verification record

- Frontend contract generation and production build.
- Frontend lint: no errors; two existing hook-dependency warnings in the engineering/validation screens.
- Fresh SQLite migration and upgrade of a legacy-schema database; legacy user data preserved.
- Local API checks for registration, duplicate email handling, sign-in/session, CSRF/origin rejection, viewer restrictions, rate limiting, password change/reset, reset replay rejection, revoked sessions, and logout.
- Two-account private-resource checks, author/account override rejection, shared baseline resolution, private cached-analysis rejection, and typed metadata/geometry/primary-design responses.
- Browser review of registration, refresh/session recovery, profile/password changes, cross-tab logout, sign-in return paths, password reset, responsive navigation, personal baseline tune creation, and the existing validation route. A copied baseline tune was also resolved and checked to preserve the exact assembly and pass CINDER validation.

No automated test suite or CI changes are included. Real SMTP delivery, PostgreSQL deployment verification, and broad simulation/regression E2E coverage remain release-environment/M5 work.
