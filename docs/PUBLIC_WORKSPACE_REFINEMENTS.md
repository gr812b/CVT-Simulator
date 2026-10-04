# Public workspace and manual-review refinements

This scope supersedes M1–M4's private-by-default and explicit publication policies. Development uses a fresh database; no historical-data migration or compatibility layer is required.

- Accounts use the free tier. Saved physical configurations, tunes, load cases and run inputs/results are public. Authentication and ownership still control edits, submissions, cancellation and account information. Email, password data and session data are never public content.
- School is optional at signup and editable in account settings.
- Engines, belts, CVTs and vehicle setups appear in the public catalog automatically when saved. Public snapshots retain immutable revisions and source attribution; copies belong to their new owner.
- Seed all belts from the supplied Design Space Explorer's Belts tab. Retain unrounded sheet values, manufacturer/series/part labels, source statuses and assumptions. Density is an explicit application-baseline assumption, not a manufacturer specification.
- Load cases are reusable, named, versioned objects with their own library/editor and a run-page picker. Seed flat roads, positive/negative road angles and the existing hill/whoops examples. Secondary loading stays vehicle/road only.
- Run setup proceeds through Vehicle, CVT and belt, Primary boundary, Load case, and Review. Keep a persistent summary and reuse the physical and road editors. Primary choices use CINDER's existing engine, torque/inertia and speed-tracking boundaries; no new solver mechanics.
- Geometry study defaults to matching belt/sheave angles: derive bottom width from top width, height and half angle. Full active travel defaults to bottom width; total shift includes deadzone. Preserve measured sections as an explicit alternative and allow a shorter mechanical limit under Advanced.
- Use one CINDER home link across page headers. Hide Primary Design and Dyno Validation from workspace navigation.
- Playback controls stay visible at the viewport bottom. Adjust page layout and spacing using Mantine without changing chart, replay or 3D mechanics.
- Explain disabled actions, including the one-active-run limit. Opening a run acknowledges its completion notice.

Continue generated backend-to-frontend contracts, one gateway to CINDER, server-side geometry resolution, centralized theme/units and shared components. Use targeted backend and browser acceptance walkthroughs for this work. Formal E2E tests and CI remain M5 work.

## Local setup for this update

Apply this update after the demo/worker follow-up (`3aca8c6`). No new dependencies are added. Stop the API and worker before resetting the database. From the repository root:

```bash
cd backend
source venv/bin/activate
python -m app.scripts.init_database --reset
uvicorn app.main:app --reload
```

`--reset` deletes the selected file-backed SQLite development database, including accounts and runs, then recreates and seeds it. It respects `CVT_DATABASE_URL` or `--database-url`. It refuses production mode, PostgreSQL and in-memory databases. Create a new account after resetting; there is no default password.

Start a second backend terminal using the same database environment:

```bash
cd backend
source venv/bin/activate
python -m app.scripts.run_worker
```

Start the frontend in a third terminal:

```bash
cd frontend
npm run dev
```

Open `http://localhost:5173`. The development/build scripts regenerate backend and CINDER contracts. `/demo` remains available without an account or worker. Normal runs need the separate worker. A fresh PostgreSQL database uses `alembic upgrade head` followed by `python -m app.scripts.init_database`; preserving an existing database is outside this update's scope.

## Included defaults and behavior

- The offline seed snapshot contains all 32 belt rows from the linked sheet's **Belts** tab, plus the three existing belt examples: 35 belts total. Manufacturer, series and part are combined in the display name. Source statuses, notes, the exact source URL and unrounded values are retained in `backend/app/database/catalog_belts.json`. Normal startup does not access Google Sheets.
- Nine load cases include flat road, climb, repeated whoops, and ±5°, ±10°, ±15° constant roads. Grades are resolved using distance along the road, matching the existing backend road contract.
- Saving a physical item publishes its revision automatically. Discovery shows the latest active revision; earlier snapshot URLs stay fixed. Other users can copy public items, while editing and archiving remain owner operations. Account details are not public simulation content.
- Load cases have their own library, editor, revision history, road preview and run-builder dropdown. Choosing or creating one is a full builder step. Run-specific numerical/initial-condition adjustments do not silently change the saved load case.
- The secondary boundary remains vehicle/road. Primary choices are an engine, applied torque with inertia, or an advanced speed-reference tracking boundary. The latter uses CINDER's existing tracking controller and may apply corrective torque; it is not a new motor model.
- The default geometry study derives bottom width from top width, height and half-angle. Selecting a catalog belt preserves its measured bottom width through the explicit measured-section mode. Full active travel defaults to that bottom width, with deadzone and shorter mechanical travel under Advanced.
- One queued or running simulation per account remains enforced on the server. Disabled run controls explain the limit. Viewing a completed run clears its unread completion notice. Playback controls remain fixed at the viewport bottom.

## Manual acceptance checkpoints

1. Browse engines, belts and load cases without signing in; inspect a belt's source notes and open the recorded demo.
2. Register with School, edit it in Account, and confirm CINDER returns home from each page.
3. Build a run through all five steps. Select a default grade, then create and reuse a named road with repeated whoops. Confirm the summary follows each selection.
4. Submit a short run. Confirm another submission is blocked with an explanation, then open the finished run from its notice and verify the notice clears.
5. Open playback at desktop and mobile widths; scroll through plots while using the visible player. Confirm CSV export and public result links work.
6. Run the geometry study using derived and measured widths; review the resolved travel and feasibility.

Disposable backend/browser walkthroughs are used for this implementation, alongside generated contracts, production build and lint. No unit-test suite, committed E2E suite or testing-CI changes are part of this update.

Verified on this update: fresh SQLite reset and Alembic setup; all catalog kinds and source belt values; automatic publication and independent copying; immutable revision URLs; ownership and CSRF enforcement; all nine default load cases; both primary overrides and editable run copies; a real worker run and concurrent-submission rejection; geometry derivation and measured widths; signup/profile School; desktop/mobile builder, geometry and playback; completion-notice acknowledgement; and anonymous result access. Production build and generated contracts pass. Frontend lint has zero errors and the two existing hook warnings in the deferred Primary Design/Validation pages.
