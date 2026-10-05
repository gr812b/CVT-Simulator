# Workspace, belts and course playback

This update follows `5da25d0` (landing/procedural scenes). It supersedes the earlier workspace notes where they describe standalone load-case/tune tabs, an optional recommended belt angle, source-entry forms, or prominent revision labels. M5 test infrastructure remains deferred.

## User-facing changes

- Physical library contains Vehicle setups, Engines, Belts, CVTs and Load cases. The old `/load-cases` URL redirects there.
- Physical and experiment selectors group My library, CINDER defaults and Community. Seeded engineering examples have explicit CINDER Default names; catalog manufacturer/series/part names remain intact.
- Library filters reserve their layout during loading, ignore stale responses and prevent interaction with stale cards. Shared navigation stays mounted during lazy page loads. Public catalog, item, tune, run and playback pages retain the same sidebar, with separate Design & simulation, Explore and Account sections.
- CVTs select a saved belt and show a compact dimensional summary. **New belt** opens a reusable editor in a modal, saves the belt, selects it and preserves the CVT draft.
- Belt creation/editing accepts any three of top width, bottom width, height and **half-angle**. The fourth is calculated by the backend. Half-angle means half the included angle between the two belt sides. Pending or invalid calculations block saving.
- The CVT sheave half-angle is read-only with an explanation tooltip. The backend also enforces the match on save and validation. Geometry studies preserve selected belt dimensions; measured-section mode calculates its matching angle.
- Source/measurement entry fields are hidden. Existing provenance remains in stored data. Version history, comparison and restore remain available through secondary controls; revision numbers are removed from ordinary cards, pickers and saved-state labels. Component updates are expandable.
- Public tunes appear under their parent CVT, with a **View tunes for this CVT** section on both physical and public CVT pages. There is no standalone public Tunes tab. Tunes can be reused across vehicle setups using the same CVT version; incompatible versions are rejected. The original setup reference remains internal provenance and provides the starting vehicle when opening a public tune.
- Public run rows reserve a status column, independent of title length, and adapt at mobile widths.
- Inclines use degrees. Changing length preserves the angle. Distance is measured along the road surface, so elevation change is `length × sin(angle)`.
- Recorded, public and owned playback show elevation versus distance with a timeline-linked vehicle marker. The course is projected from the run's frozen CINDER road profile and frozen route extent. Editing a library load case cannot alter old playback. Signed distances and continuation beyond the route follow CINDER's grade convention.
- Playback has consistent horizontal gutters, including the standalone anonymous demo. Existing 3D rendering, plots and fixed playback controls remain shared.

## Default belt correction

The original update retained top width and derived bottom width. This was superseded by Kai's confirmed **11.5° half-angle** in [the common-case workflow update](COMMON_CASE_RUN_WORKFLOW.md): retain bottom width 16.8148 mm and height 15.5702 mm, and derive top width **23.150385985 mm**. The updated application default passes CINDER preflight and actual execution.

Imported catalog belts instead retain the supplied top width, bottom width and height and derive their half-angle. Original sheet values, including the separately listed angle, remain in the offline source snapshot/provenance. A catalog belt may require different CVT radii or actuator profiles; validation reports incompatibilities rather than silently resizing hardware.

The research preset, formulation and retained demo evidence are unchanged. The demo represents its original frozen input, not a newly seeded physical configuration.

## Setup

Use a fresh development database: the belt and incline JSON contracts changed deliberately without a compatibility migration. Stop the API and worker, then from the repository root:

```bash
cd backend
source venv/bin/activate
python -m app.scripts.init_database --reset
uvicorn app.main:app --reload
```

In a second backend terminal using the same database environment:

```bash
python -m app.scripts.run_worker
```

In a frontend terminal:

```bash
cd frontend
npm install
npm run dev
```

The reset command deletes the selected development SQLite database, including accounts and runs. Register a new account afterward. It respects `CVT_DATABASE_URL`; the API and worker must use the same value. No new dependencies are required. Frontend startup/build regenerates backend and CINDER types. The anonymous `/demo` needs only the API and frontend.

## Engineering and acceptance

Mechanics and section resolution stay in the backend; transport types are generated. Mantine controls, the shared library-option grouping, belt editor/picker, navigation frame, quantity validation and course chart are reused. Stored revisions, optimistic concurrency, ownership, CSRF protection and frozen runs remain intact.

Acceptance covers fresh seeding, all four belt closures, invalid-section rejection, server-enforced sheave matching, a real completed worker run, degree-preserving road edits, cross-vehicle compatible tunes, incompatible-CVT rejection, public CVT filtering and frozen course projection. Browser walkthroughs cover creating/selecting belts, compact CVT editing, navigation, library switching, load cases, status alignment, course scrubbing and responsive playback. Generated contracts, TypeScript, production build and targeted lint are checked.

No unit-test suite, committed E2E suite, CI, deployment or research changes are included. Broad automated E2E coverage and release-environment verification remain M5 work.
