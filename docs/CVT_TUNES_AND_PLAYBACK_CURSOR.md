# CVT tunes, component previews, and playback cursor

Incremental update after `7694adc` / `CINDER_Review_Playback_And_Profiles.patch`.
Apply this patch once, after that update. CINDER's displayed version remains
`1.1.5.dev0`.

## Apply and rebuild

Extract the ZIP, then run from the repository root:

```powershell
git apply --check CINDER_CVT_Tunes_And_Cursor.patch
git apply CINDER_CVT_Tunes_And_Cursor.patch
```

This update includes a database migration. Stop the API and worker, rebuild the
image, migrate the same database volume, then recreate both containers:

```powershell
docker stop cinder-local-api cinder-local-worker
docker rm cinder-local-api cinder-local-worker
docker build -f backend/Dockerfile -t cinder-local .
docker run --rm -v cinder-local-data:/data -e CVT_DATABASE_URL=sqlite:////data/cinder.db cinder-local alembic upgrade head
docker run --rm -v cinder-local-data:/data -e CVT_DATABASE_URL=sqlite:////data/cinder.db cinder-local python -m app.scripts.init_database
docker run -d --name cinder-local-api -p 8000:8000 -v cinder-local-data:/data -e CVT_DATABASE_URL=sqlite:////data/cinder.db cinder-local
docker run -d --name cinder-local-worker -v cinder-local-data:/data -e CVT_DATABASE_URL=sqlite:////data/cinder.db cinder-local python -m app.scripts.run_worker
```

Use your existing names and database URL if they differ. Migration
`20261005_0010` moves tune references from vehicle versions to their CVT versions
and initializes a default tune for every saved CVT version. Existing run snapshots
are retained. No database wipe is needed. Back up a database you want to retain
before migrating; downgrade requires restoring that backup because a CVT-owned
tune no longer identifies a unique vehicle.

For a native backend, activate its virtual environment and run from `backend/`:

```powershell
python -m pip install --force-reinstall --no-deps ../cvtModel
alembic upgrade head
python -m app.scripts.init_database
```

Restart the API and worker. On Windows, continue using the Docker worker.

From `frontend/`, run `npm run dev` or `npm run build`; either regenerates the API
types. If host Python is unavailable, export contracts from Docker first
(PowerShell, from the repository root):

```powershell
New-Item -ItemType Directory -Force backend/generated | Out-Null
docker run --rm --mount "type=bind,source=$($PWD.Path)/backend/generated,target=/contracts" cinder-local python -m app.scripts.export_contract_artifacts --output-dir /contracts
cd frontend
$env:CINDER_SKIP_BACKEND_EXPORT = "1"
npm run dev
```

## Behavior

- **CVT hardware:** belt, pulley geometry and mounting dimensions, inertias, and
  contact properties. The supported clamping mechanism arrangement stays fixed.
- **Tunes:** primary mass, springs/preloads and ramp profile; secondary springs,
  preloads and helix profile. Add tune is available below a saved CVT's hardware,
  including when viewing someone else's public CVT. The new tune belongs to its
  creator and points to that CVT; it does not create a vehicle or copy the CVT.
- Each saved CVT version has a designated default tune. Its owner can choose a
  different default from that CVT's tune list. Build a run selects it automatically.
  A submitted run retains the exact tune revision and effective values it used.
  Changing the default or editing that tune cannot change past runs.
- New CVT versions receive an initial default from their saved assembly. Tunes
  remain associated with the hardware version for which they were validated;
  saving a tune cannot silently move it to different hardware.
- Tune viewing is read-only until Edit tune is selected. Add, edit and duplicate
  share the same editor as Build a run. Version history can open an old version
  or restore it as a new version. A designated default cannot be archived until
  another default is chosen.
- Rotatable primary and secondary previews use the shared procedural renderer.
  They show only the selected pulley assembly, including ramp/flyweights or
  helix/rollers. The secondary view starts facing its clamping mechanism.
  Preview requests are debounced and stale responses are discarded. Full-travel
  validation remains part of saving and running.
- Secondary helix angles are displayed from the circumferential direction:
  `display angle = 90° − stored profile angle`. Edits use the inverse conversion.
  The existing 70° profile displays as 20° with unchanged physical geometry.
- Vehicle pages show vehicle/drivetrain values and linked engine/CVT summaries.
  A CVT links its belt. Links retain the selected version and carry a contextual
  Back destination through nested navigation.
- Library tabs share one component: Vehicle setups, Engines, CVTs, Belts, then a
  separator before Load cases. Public views add Runs and People afterward.
- New and reset passwords require 8–128 characters, including the operator
  password command. Existing-password verification is unchanged.
- The replay cursor is a persistent native chart layer. It is driven by replay
  progress and redraws independently of the tooltip. Hover tooltips still show
  values, but no longer introduce a competing crosshair. The cursor handles
  initial display, seek, resize, zoom, legend selection, and new streamed data.

## Implementation boundaries

Transport types come from the backend's generated OpenAPI contracts. Physical
references are response metadata, so adding links does not change saved physical
documents or create new revisions. CINDER owns profile evaluation and mechanical
geometry; the gateway projects it into the existing scene contract. Component
previews resolve an initial primary contact plus the secondary travel path without
compiling the full primary flyweight map. Numerical save/run validation is kept.

No CI changes or new unit-test suite are included.

## Verification

- Fresh database initialization and migration of a copy of the previous database.
- API acceptance checks: 8-character signup and rejection below the minimum;
  new tune on a public CVT without hardware copies; default ownership and stale
  update protection; default creation and run selection; incompatible tune
  rejection; exact run reuse after a default change; engine/CVT/belt links.
- Real ECharts rendering checks without hover: initial cursor, seek, resize,
  zoom clipping, legend visibility, data updates, and disposal.
- Server-rendered frontend checks: read-only and editable 20° helix display,
  linked summaries, tab order/separator, and contextual Back link. Three.js model
  checks include both isolated mechanisms and finite scene bounds.
- Production build and TypeScript generation/checking; frontend lint has only
  the two pre-existing hook warnings in the older design/validation pages.

Interactive browser verification was unavailable in this environment. The checks
above do not replace a visual pass in your browser. Suggested manual pass:

1. Open McMaster 2025 → Tunes → Add tune; adjust primary and secondary inputs,
   rotate each preview, save, and reopen it.
2. On a CVT you own, choose another default and confirm Build a run selects it.
   Try starting from an existing run afterward: its original tune stays selected.
3. Follow vehicle → CVT → belt and use the page's Back button at each level.
4. Open playback with the pointer outside the plots. Play, pause, seek, zoom,
   switch plot tabs and resize/fullscreen the view; the current-position marker
   should remain independent of hover.
