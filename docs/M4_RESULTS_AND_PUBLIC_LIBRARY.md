# M4 — Results and the public configuration library

M4 completes the results and vehicle/CVT publication workflows in the implementation baseline. It builds on M3's durable jobs and immutable inputs. CINDER remains pinned to 1.1.4; this milestone adds no mechanics, runtime dependencies, unit-test suite or testing CI.

## Finding and understanding a run

**Runs & results** (`/runs`) searches the signed-in workspace's run names, IDs and frozen setup/tune/scenario names. Status, source, local calendar dates, ordering and pagination are preserved in the URL. Active pages refresh while their jobs are queued or running. Each card shows the original references, timestamp, status and stored summary metrics. Private results are never exposed through the public library.

The saved run page supports renaming with stale-write detection, cancellation, explicit rerun, playback, frozen-input inspection and exports. Renaming changes the display name only; it does not change the canonical input or input hash. Setup/tune/scenario labels come from the frozen run record rather than today's editable objects. Older records without full labels remain identifiable by their revision IDs.

Time histories default to the reduced display preview. **Load full report data** requests every stored report-table sample; it does not claim to expose the adaptive solver trace. Signals use their stored labels and canonical units. Null gaps and duplicate transition timestamps are retained. Summary metrics come directly from the stored solver result, never from a downsampled chart. The details page also shows warnings, termination reason, transition events, and partial-result status.

Availability is explicit. A retained preview and summary remain useful when the full result artifact is missing, while full-data exports and playback become unavailable. A completed worker record is not presented as successful integration if the solver's own completion flag is false. Queued, failed, cancelled and timed-out records remain inspectable, with their frozen input available for a deliberate rerun.

| Download | Contents |
| --- | --- |
| Canonical input JSON | The exact frozen executable CINDER case. |
| Summary JSON | `cinder_run_summary_v1`: run/solver identity, provenance, frozen references, availability and original summary. |
| Full result JSON | The complete stored CINDER result, without a display-preview substitution. |
| Full report CSV | Every stored report-table column and row, with canonical units in the header. |

Downloads are authenticated attachments with `private, no-store` caching. A missing full artifact returns an explicit unavailable response rather than an empty success.

## Continuing an experiment

**Rerun frozen input** retains M3's exact-input behavior and creates a new run linked to its parent. It uses the installed solver and the existing account admission limits.

**New experiment from this run** creates an independently owned setup and scenario, then opens Tune & run with both selected. Effective tuned hardware and the run-only vehicle mass become values in the copied setup; the frozen road, initial conditions and numerical settings become the copied scenario. Submitting from this editor records the source run as the parent. Neither action changes the original run, setup, tune or scenario.

Before offering an editable copy, the backend reconstructs the candidate and requires exact equality of all five executable sections: assembly, shaft boundaries, host, scenario and execution. Older/direct/specialized runs without a representable editable scenario show an explanation and retain input export and exact rerun. This deliberately avoids silently dropping settings outside the current editor. Copy request keys make an identical retry return the same owned configuration.

## Publishing setups and CVTs

The public library (`/catalog`) is readable without signing in. It searches explicitly listed publications by name, description, author and source, with separate vehicle-setup and CVT views. Pages show attribution, useful physical properties, included components, input validation and the complete configuration through the existing read-only physical editors. Validation is described as compatibility with CINDER, not proof of measurement accuracy. Seed examples are labeled as illustrative.

Publishing is a separate action from saving a private item:

1. Save an owned setup or CVT, then open **Publish & sharing**.
2. Review the exact fixed revision and its required component values. Private measurement notes and internal dependency revision IDs are removed from the public bundle.
3. Choose link-only or public access, choose whether to list it, and explicitly consent to sharing the included configuration and component values.
4. Publish that revision. A later edit requires a new publication; it cannot rewrite an earlier snapshot.

The source item and its dependencies retain their existing private access. Publications contain self-contained values and supported tuning metadata, not access grants to private drafts or other source revisions. The backend checks ownership, current revision and the reviewed snapshot hash before publishing. The same source revision has at most one publication; retrying does not silently change its access settings.

| Access | Who can open the fixed page? | Public gallery/history discovery |
| --- | --- | --- |
| Public, listed | Anyone with the page URL. | Included. |
| Public, unlisted from gallery | Anyone with the page URL. | Excluded. |
| Unlisted | Anyone with the page URL. This is link sharing, not authentication. | Excluded, including sibling publication history. |
| Private / withdrawn | No public access; the owner can manage access in their editor. | Excluded. |

Public pages link to newer listed publications and offer revision differences. The page always retains its original values. Access changes use a version check; stale tabs receive a conflict. Withdrawal removes public access without deleting publication history or existing recipients' copies.

**Copy to My Library** requires sign-in and creates a private, independently owned setup/CVT and all required components. A persistent origin record links back to the publication, even if that link later becomes unavailable. Source edits, new publications and withdrawal never modify a recipient's copy or runs. Idempotent copy requests prevent duplicate items from an identical retry.

Public tunes, public runs, multi-run comparison and further Design Studio work remain deferred.

## Storage, migration and samples

Migration `20261004_0008` adds `physical_publications` and `configuration_copies`. Existing revisions, visibility, tunes, run inputs and artifacts are untouched. Publication values, attribution, source revision, validation and hash are frozen; only access/listing and its conflict version are mutable.

Back up the database, apply `alembic upgrade head`, and run the API and M3 worker with the same database. To add the new samples to an existing development installation, run `python -m app.scripts.init_database` after migration. Seeding is additive and preserves existing edits. There are four default listed publication snapshots: two setups and two CVTs. Opt-in `--development-fixtures` adds one listed and one unlisted setup publication in the isolated fixture accounts. Private fixture objects remain private.

The migration refuses a destructive downgrade. Restore a verified pre-M4 backup with the matching application version to roll back. No deployment, image publication or CI update is part of this milestone.

## Contracts and coding standards

- `schemas/results.py` and `schemas/publications.py` own the product API contracts; frontend types derive from generated OpenAPI. CINDER continues to own the executable and result schemas.
- `application/run_results.py` owns result projections, search, exports and exact-copy checks. `application/publications.py` owns fixed bundles and access rules. `configuration_copies.py` serializes idempotent copying per account. Routes handle transport and authenticated identity.
- `features/results` and `features/publicLibrary` use shared transport, Mantine controls, the centralized theme and existing physical editors. Downloads use one small shared browser helper. No new component/chart package is introduced.
- The legacy preview response schema now describes its actual column array and `preview_row_count`. Newly generated previews use the real CINDER effective-ratio key; old previews are retained unchanged.
- Apply the M1 coding standards: explicit ownership checks on every referenced resource, immutable scientific evidence, generated API types, reusable controls, canonical backend values and centralized display units/theme. Do not compute physics or result metrics in view components.

| API family (under `/api/v1`) | Purpose |
| --- | --- |
| `GET /run-history` | Owned, filtered and paginated run summaries. |
| `GET /runs/{id}/inspection`, `/series` | Stored result evidence and preview/full time histories. |
| `PATCH /runs/{id}/name` | Conflict-aware display rename. |
| `GET /runs/{id}/exports/{input\|summary\|result\|csv}` | Authenticated exact-data downloads. |
| `POST /runs/{id}/experiment-copy` | Independent editable copy of a representable frozen configuration. |
| `GET /publications`, `/{id}`, `/compare`, `/metadata` | Anonymous, access-filtered configuration discovery and inspection. |
| `/publications/preview`, `/publish`, `/manage` | Owned, reviewed publication creation and history. |
| `PATCH /publications/{id}/access`, `POST /{id}/copy`, `GET /origin/{kind}/{id}` | Sharing controls and independent-copy provenance. |

## Verification and milestone boundary

Focused acceptance walkthroughs run outside the repository; no committed test suite or CI gate is added. The verification record covers generated contracts, TypeScript/production build and lint; fresh SQLite migration and upgrade with existing data preserved; repeat normal/fixture seeding; explicit consent, note removal, private ownership, listing rules, fixed publications, independent copies and withdrawal; a real CINDER worker run; exact exports, frozen experiment reconstruction, rename conflicts and missing-artifact behavior.

Desktop and 390 px browser checks cover anonymous inspection, publishing, copying, results, exports, history, experiment reuse and playback. The existing frontend build chunk-size notice and two pre-existing hook lint warnings remain.

M1–M4 are implemented. M5 remains formal E2E coverage, CI integration, real PostgreSQL/container release verification, broader load/regression coverage and release hardening. This record does not claim those checks have passed.
