# Database and revision model

SQLAlchemy stores application state in PostgreSQL for deployment and SQLite for
local development/tests. JSON payload columns use PostgreSQL JSONB or SQLite
JSON; identity, ownership, versions and job state remain relational.

## Stored records

| Records | Purpose |
| --- | --- |
| Accounts, users and memberships | Workspace identity, roles and credentials |
| Sessions, reset tokens and auth rate limits | Revocable authentication with hashed tokens |
| Institutions/affiliations | Optional self-reported school attribution, separate from account permissions |
| Engines, belts, CVT designs, output systems and vehicle assemblies | Reusable physical objects with immutable released versions |
| Experiments and experiment revisions | Named tunes and load cases with immutable JSON documents |
| CVT default tunes | Preferred tune for each CVT revision |
| Runs | Frozen executable input, selected references, runtime identity and queue state |
| Run artifacts and notifications | Retained preview/full result and per-user completion acknowledgement |

The current product APIs use `/physical-library` and `/experiments`. Legacy
`/library` resources and older tables remain for existing data/adapters; the
legacy `Tune` table is not the current revisioned tune model. Consult generated
OpenAPI for current request envelopes rather than sending account/user IDs as
identity.

## Physical and experiment revisions

A saved physical object points to an immutable version. Vehicle revisions pin
engine, CVT and output-system versions; CVT versions can pin a belt. CVT hardware
owns its own inertia, the input boundary owns engine/input inertia, and the output
system owns vehicle/final-drive/secondary-shaft data. Application services compose
these pieces into CINDER's executable case.

Tune documents belong to a CVT and pin a compatible CVT revision. Their values
can be reused across vehicle setups using that hardware. Load-case documents
store road features, stopping policy and initial/numerical settings. Saves append
revisions; restoring history creates a new revision rather than changing the old
one. Expected-revision checks reject stale edits.

Archiving removes an item from normal discovery without deleting its history.
Old explicit references and frozen run inputs remain available. Saving or choosing
a new default tune does not modify earlier run configurations. Public copies have
independent ownership and revisions with source attribution.

## Durable runs

`POST /api/v1/experiments/runs` resolves the selected configuration, validates it,
and inserts a queued run before returning HTTP 202. The legacy
`/runs/from-library`, direct `/runs`, and rerun paths use the same admission rules.
The database enforces a unique `(account_id, request_key)` pair; admission also
serializes the one-active-job rule for the account.

A run stores:

- the complete frozen `input_contract`, its contract hash, submitted tune/load
  case snapshots, source references and run-only overrides;
- `runtime_identity`, including CINDER package, input schema and result-contract
  versions, plus execution options;
- request key/hash, parent run, status, worker token, deadlines and cancellation;
- summary metrics, durable preview data and links to retained result artifacts.

The ORM's `input_schema_version` uses the historical physical column name
`contract_schema_version`; result schema versioning is separate. New contract
hashes include the canonical executable input, runtime identity and execution
options. A hash is provenance, not a promise that a queued run will reuse a cache.

New jobs execute independently of the legacy `run_cache_entries` table. Old
cache-linked artifacts can still be read. Full results and previews currently
use inline JSON artifacts; preview data is also retained on the run. Worker
checkpoints update the saved partial result and preview together. Do not assume
a terminal failure means there is no result data, or that evicting a full result
also removes frozen inputs and summaries.

**Rerun frozen inputs** creates a new job from the old input without resolving
new library revisions. **New experiment from this run** reconstructs editable
saved references/overrides and does not create copies merely by opening it.
These are different operations.

## Schema and seed maintenance

Run migrations and sample initialization with the same `CVT_DATABASE_URL` used
by API and worker:

```bash
alembic upgrade head
python -m app.scripts.init_database
```

Alembic owns deployed schema changes. The initializer's ORM table creation is a
convenience for disposable local files; it cannot upgrade existing table columns.
Normal initialization adds/updates built-in samples without deleting user data.
Changed sample load cases receive revisions; retired built-ins are archived.

Back up deployed databases before schema changes. Do not downgrade or delete
history to recover an application version; restore a verified backup with a
compatible application if rollback requires it. See the
[root deployment guide](../../README.md#persistence-and-backups) for PostgreSQL
backup/restore commands and the [backend guide](../README.md#samples-and-initialization)
for the explicitly destructive development SQLite reset.
