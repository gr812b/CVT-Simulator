# Contributing

Report problems through [GitHub issues](https://github.com/gr812b/CVT-Simulator/issues)
with reproduction steps, the affected page/API, expected behavior, and relevant
logs or screenshots. Remove credentials, session/reset tokens and personal data
from reports.

Create a branch from the target development branch and keep changes focused.
Follow the [backend](backend/README.md) and [frontend](frontend/README.md) setup
instructions. Install through their requirements/package files and use the
existing formatting and components.

- Keep mechanics and public model contracts in CINDER; backend adapters compose
  application inputs, and the frontend owns editing/display behavior.
- Keep authentication, ownership and CSRF checks on writes. Saved revisions and
  frozen run inputs must remain independent of later edits.
- Add Alembic migrations for database schema changes. Do not use a database reset
  as an upgrade path for user data.
- Regenerate API contracts locally after backend changes, but do not commit
  generated schemas/types, credentials, databases, caches or build output.

Before submitting, run `python -m pytest`, `python -m flake8 app` and
`python -m black --check app` from the backend environment. From `frontend/`, run
`npm run lint`, `npm run build` and the relevant `npm run test:helpers` /
`npm run test:browser` checks. The frontend guide describes browser installation.
For CINDER changes, also follow its [package guide](cvtModel/docs/GETTING_STARTED.md)
and run the relevant model tests.

In the pull request, explain the user-visible change, how it was checked, and
any migration or deployment steps. Distinguish automated adapter tests from
checks using the real application and model.
