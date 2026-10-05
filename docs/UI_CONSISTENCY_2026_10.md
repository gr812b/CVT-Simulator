# Shared library and result pages — October 2026

## Delivered behavior

- Physical and public libraries use one browser, source selector, search, card,
  loading treatment and pagination. Load cases use these same components.
  The physical library keeps its source selection when switching categories.
- Public and owned runs share their detail and playback pages. Ownership only
  changes available actions. Initial loading covers the navigation too.
- Runs show their author and link saved vehicle, CVT, belt, engine, tune and
  load-case versions. Temporary overrides remain identified as modified values.
  Public runs can start a new experiment using their original references.
- Hardware opens in display mode. Owners choose Edit configuration; public
  visitors see readable values and registered users can explicitly copy an item.
  Existing publication links open the same page at their published version.
- CVT and vehicle reads use stored validation results instead of rerunning the
  solver validation. Writes, explicit input checks and run submission still
  validate. Component catalogs load when entering edit mode. Torque charts load
  their chart library only when needed.
- Public Library has a searchable People tab and school filter. Registration
  and account settings share the searchable school dropdown. The directory
  exposes display name and school, never email.
- The offline school catalog contains 142 normalized names from official 2024
  Michigan, 2025 Arizona and 2026 Oregon Baja SAE results. Source URLs and the
  update date are recorded in `backend/app/data/baja_schools.json`. This is a
  starting list from those three events, not every competition worldwide.
  Refresh that file to add further schools; blank school remains permitted.
- There is one default vehicle: McMaster 2025, 500 lb. Normal reseeding archives
  former sample vehicle variants without removing saved-run references. The
  default CVT and engine remain McMaster 2025 and Kohler CH440 (Baja Restricted).
- The regenerated demo accelerates on a flat, climbs at 35 degrees, crosses a
  short flat, descends at 35 degrees and finishes on a flat. It is a real completed
  CINDER simulation and needs no account or worker at playback time.
- Course previews and playback use equal horizontal/vertical metres per pixel.
  Solver distance is road arc length; the plot projects it onto horizontal
  distance so displayed slopes preserve their physical angles.
- Run status colors come from the shared theme. Running checkpoints are labelled
  live progress; final partial trajectories retain their termination reason.
- Tooltips have explicit high-contrast text/background colors. The home header
  follows authentication state; the footer includes PyPI alongside GitHub.

## Apply this update

This patch contains this entire UI consistency update, including the regenerated
demo. It is based on the tree at `a5346ab` on `front-end-redo-setup` (identical to
the local baseline `adaca15`). Apply this patch once; it is not a second layer on
another patch from this update.

Extract the download, then run these commands in PowerShell, adjusting the patch
path to where you extracted it:

```powershell
cd F:\Code\Projects\CVT-Simulator
git apply --check "$HOME\Downloads\CINDER_UI_Consistency\CINDER_UI_Consistency.patch"
git apply "$HOME\Downloads\CINDER_UI_Consistency\CINDER_UI_Consistency.patch"
```

Rebuild both backend processes from the repository root. The commands below use
the existing `cinder-local-data` Docker volume and `cinder-local-*` container names.
Keep your existing volume/mount and environment settings if yours differ.

```powershell
docker stop cinder-local-api cinder-local-worker
docker rm cinder-local-api cinder-local-worker
docker build -f backend/Dockerfile -t cinder-local .
docker run --rm -v cinder-local-data:/data -e CVT_DATABASE_URL=sqlite:////data/cinder.db cinder-local python -m app.scripts.init_database
docker run -d --name cinder-local-api -p 8000:8000 -v cinder-local-data:/data -e CVT_DATABASE_URL=sqlite:////data/cinder.db cinder-local
docker run -d --name cinder-local-worker -v cinder-local-data:/data -e CVT_DATABASE_URL=sqlite:////data/cinder.db cinder-local python -m app.scripts.run_worker
cd frontend
npm run dev
```

No database reset or new schema migration is needed for this update. Normal
`init_database` reseeding updates the default catalog. `npm run dev` regenerates
API contracts using the existing backend virtual environment. No new dependencies
are introduced.

## Verification completed

- Production frontend build, generated API contracts and TypeScript compilation.
- Frontend lint: zero errors; two pre-existing hook dependency warnings remain
  in the primary-design and dyno-validation pages.
- Changed backend files pass Ruff import/undefined-name checks and formatting.
- API acceptance using disposable accounts and a local database: school options
  and validation, directory privacy/filtering, one default vehicle/CVT/engine,
  public item reads, exact-version run links and owner-only mutation enforcement.
- Reopening another user's public run retains the selected setup/CVT and creates
  zero vehicle, CVT, belt, engine or experiment objects.
- A real queued simulation ran through the production worker and its result
  loaded anonymously. The real demo completed its entire hill course.
- Editing acceptance: unchanged save retains its version; a changed save creates
  v2; public historical reads retain v1; anonymous writes are denied.
- Local warm API requests measured roughly 9–12 ms for the default CVT and
  18–23 ms for its vehicle. These timings exclude network and browser rendering.

Interactive browser verification could not be completed: the available browser
blocked the local preview address. Build/API acceptance is not a substitute for
visual inspection. No unit tests or CI changes were added.

## Frontend walkthrough still to verify locally

1. Signed out, open the home page, demo, public hardware, People and a public run.
   Follow an author and the run's configuration links. Check home auth actions.
2. Sign in, select CINDER defaults in the physical library, then change categories
   including Load cases. Confirm the source remains selected and layout stays put.
3. Open your hardware in display mode. Edit, cancel and save it; compare a previous
   version. Open another author's item and confirm there are no disabled forms.
4. Open the same run through both owned/public links and playback. Confirm matching
   loading, owner/configuration links and player behavior at desktop/mobile widths.
5. Create an experiment from someone else's run. Check selected references and
   available CVT tunes; opening it alone must not add items to your library.
6. Watch queued/running/completed/failed statuses and a running checkpoint. Confirm
   the checkpoint says Live progress and tooltips remain readable.
7. Play the hill-course demo. Inspect equal plot scales, the vehicle-position
   marker, and the full flat/climb/crest/descent course.
