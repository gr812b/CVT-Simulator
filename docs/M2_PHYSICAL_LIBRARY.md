# M2 — Physical library and revisions

M2 adds private, reusable engines, belts, CVTs, and complete vehicle setups. It builds on [M1's application foundation and coding standards](M1_APPLICATION_FOUNDATION.md). CINDER 1.1.4 remains the authority for mechanics, document contracts, and engineering validation.

## Everyday workflow

Open **Physical library**, then create an item or browse the project samples. A new item starts with complete, explicitly illustrative baseline values. Copying a setup creates private copies of its engine, CVT, and belt so the entire physical configuration can be edited in one place.

- **Engine:** edit a torque table and preview its curve, or paste/upload two-column CSV data. Imports accept RPM or rad/s and N·m or lb·ft, sort speeds, and reject duplicate speeds, nonfinite values, and malformed rows. The preview connects the entered points; CINDER owns simulation interpolation. Braking extensions are in an advanced section.
- **Belt:** enter outer circumference, section dimensions, cord depth, and density. Belts have their own saved revisions and can be reused across CVTs.
- **CVT:** select a belt and edit pulley geometry, travel, masses, inertias, contact, and the existing actuator hardware and ramp/helix profiles. Numeric controls derive from CINDER's schema. Profile segments can be duplicated or removed; engineering validation checks the resulting configuration. Geometry compilation controls are hidden behind an advanced option.
- **Vehicle setup:** select or create an engine and CVT, then enter vehicle mass, wheel/final-drive properties, and road load. One **Save** commits changed components and the setup together. Users do not have to release internal component layers separately.

**Check inputs** runs CINDER preflight. Valid setups offer a resolved CINDER input download and **Tune & run this setup**, which opens the existing simulator with that saved setup selected. Readiness uses the baseline launch/execution configuration; the actual experiment is checked again before execution. Invalid engineering configurations can be saved for further work and remain marked **Needs attention**. Structurally malformed requests are rejected before persistence.

Inputs show units and useful measurement notes. Blank or out-of-range quantities block submission, and navigating away from an unsaved working copy asks whether to keep editing or discard it. Loading, conflict, and validation errors remain visible. Shared samples can be inspected but must be copied before editing.

## Measurement conventions

| Input | Convention |
| --- | --- |
| Belt length | Closed outer circumference; not pitch/cord length or an open span. |
| Cord depth | Depth inward from the belt's outer face, within the belt height. |
| Pulley reference radius | Radius to the belt outer surface at zero shift, not the sheave outside diameter or cord radius. |
| Sheave angle | Half the included angle between the two faces. |
| Flyweight properties | Mass and first/second moments must describe the same physical mass distribution. |
| Engine inertia | Equivalent inertia on the input shaft; avoid counting it again as CVT hardware. |
| Wheel inertia | Combined wheel inertia at the modeled wheel speed. CINDER handles final-drive reflection. |
| Other secondary inertia | Direct secondary-shaft inertia excluding separately entered CVT hardware and wheel inertia. |
| Stored quantities | Canonical SI; display conversion happens at the editor boundary. |

The selected belt is authoritative for its embedded CINDER geometry and density. Saving normalizes those values together, preventing conflicting belt copies. Existing static/kinetic contact coefficients remain physical inputs and are not overwritten by legacy execution-preset defaults.

## Revision behavior

Saved versions are immutable. Saving changed physical values or metadata appends a revision; an unchanged save does not create another one. **History** shows saved revisions and differences. **Restore** saves the selected historical state as a new current revision without rewriting history. **Duplicate** copies a fixed revision into a private item. Archiving removes an item from ordinary lists while preserving its history and pinned references.

Setups pin exact engine/CVT revisions, and CVTs pin an exact belt revision. New component revisions do not silently change existing setups. An available update has a review screen showing its differences and preflight result; applying it uses the ordinary transactional save and creates any necessary CVT/setup revisions. Differences use canonical field names and SI values.

Writes compare the expected current revision and acquire a database write lock before changing the object. A stale tab gets a conflict rather than overwriting a newer revision. Nested component writes share the request transaction, including rollback on a conflict. Editing an unchanged referenced component preserves its pinned revision; editing a component owned elsewhere creates a private copy. Every referenced revision is checked recursively for access.

## Default samples and optional fixtures

The normal seed adds a deterministic catalog alongside the existing application samples:

| Record | Example content |
| --- | --- |
| Project baseline engine curve | Complete engine curve and equivalent input inertia. |
| Project baseline rubber belt | Two revisions, with an illustrative 2% density increase in revision 2. |
| Illustrative denser rubber belt | A separate belt with 10% higher density. |
| Project fixed-pivot CVT | Original hardware pinned to belt revision 1, deliberately leaving an update available. |
| Illustrative lower-traction CVT | Kinetic friction coefficient 0.50 with the denser belt. |
| Baja baseline · 500 lb | History from the original 300 kg setup to the illustrative 500 lb configuration. |
| Baja alternative · 400 lb | Lighter vehicle with the alternative CVT/belt. |

These values are project examples, not manufacturer-certified measurements. Names, descriptions, and source fields preserve that distinction. Sample IDs and initial revision IDs are deterministic. Repeated seeding skips existing objects and preserves their edits and history; it no longer refreshes and overwrites legacy seed records. Future sample corrections should be explicit new versions or new sample IDs.

Optional development fixtures add two isolated passwordless accounts with private setups and private component graphs, plus access to the normal public samples. They are separate from ordinary seeding and cannot be enabled in production mode:

```bash
cd backend
source venv/bin/activate
python -m pip install -r requirements.txt
alembic upgrade head
python -m app.scripts.init_database --development-fixtures
```

Fixture emails are `m2-owner-a@example.test` and `m2-owner-b@example.test`. For local browser use, provision a password with the existing operator command, for example `python -m app.scripts.set_password m2-owner-a@example.test`. There are no default passwords or automatically authenticated sessions. Omit `--development-fixtures` for the normal sample seed.

## Implementation and maintenance

- `app/schemas/physical_library.py` owns the transport contracts. The assembly contract is embedded from CINDER's published schema and checked against that same schema with `jsonschema`; the frontend derives types from generated OpenAPI output.
- `app/application/physical_contracts.py` handles editor projections, canonical conversions, CSV import, metadata, and preflight through the gateway. It does not implement mechanics.
- `app/application/physical_library.py` handles transactional saves, copies, revision history, pinned updates, and access-aware reads over the existing version tables.
- `app/api/v1/physical_library.py` exposes authenticated `/api/v1/physical-library` routes. Existing library/run APIs remain available.
- `frontend/src/features/physicalLibrary` owns the library pages and focused engine/belt/CVT/vehicle components. Mantine, the central theme, shared quantity control, and shared generated transport remain the common UI foundations.
- Migration `20261004_0006` adds belt tables and an optional belt-version reference to CVT versions. Existing embedded belt payloads stay intact and are projected into an editable belt when needed. Run migrations before seeding an existing database.

From `frontend/`, `npm run dev` and `npm run build` regenerate contracts using the backend environment. Do not edit generated files. Runtime dependencies remain in `backend/requirements.txt`; CINDER's version has not changed. First-time fixed-pivot preflight can take several seconds; the editor shows a busy state, and identical subsequent preflight requests use a bounded in-process cache.

## Verification and remaining milestones

The implementation was checked with generated contracts, TypeScript/production build, frontend lint, targeted Python checks, focused API workflows, and local browser review. No unit-test suite, committed E2E suite, or testing CI changes were added.

Migration review covered fresh SQLite installation and upgrade from M1, with existing revision payloads unchanged. Repeated normal/fixture seeding preserved every existing row, including edited sample names and drafts. API review covered private copies, two-account isolation, immutable history, unchanged saves, stale-write conflicts, restoration, pinned references, reviewed updates, curve import failures, and malformed assembly rejection.

The browser walkthrough covered sample inspection/copying, save/reopen, unchanged saves, history restoration, empty quantity handling, unsaved-navigation prompts, curve import feedback and plotting, creating/selecting a reusable belt, reviewed engine and nested belt updates, resolved input export, a 390 px setup layout, and the simulator handoff. The downloaded case contained the updated belt density. Both default setup examples also passed CINDER validation through the existing library resolver with their exact stored assemblies, including the alternative contact coefficient. Frontend lint has no errors and retains two pre-existing hook-dependency warnings in the primary-design and validation screens.

Follow-up browser checks verified the exact setup selected by the simulator, mobile navigation, archive/unarchive, and a mobile engine edit/save. Engine rows now stack on narrow screens so torque inputs and remove controls remain visible without horizontal scrolling. The existing geometry screen was also checked after the shared quantity-control change: a millimetre edit reached the backend in canonical metres and passed CINDER validation.

Real PostgreSQL deployment verification and broad simulation/regression coverage remain release-environment/M5 work. M3 owns flexible scenarios/custom hills, durable queued work, completion notifications, and the per-user outstanding-run limit. M4 owns the wider public vehicle/CVT catalog and results workflow. Multi-run comparison and public tunes/runs remain lower priority as agreed.
