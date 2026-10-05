# Review, playback and public profiles

Incremental update after `1568d5b` / `CINDER_Website_And_Playback_Preferences.patch`.
Apply this patch once, after that update. It does not replace the earlier patches.
CINDER remains `1.1.5.dev0`; its version display is unchanged.

## Apply and restart

Extract the ZIP, then run from the repository root (use the actual patch path):

```powershell
git apply --check CINDER_Review_Playback_And_Profiles.patch
git apply CINDER_Review_Playback_And_Profiles.patch
```

Rebuild and recreate both Docker containers. These commands use the existing
local container and volume names from `backend/README.md`:

```powershell
docker stop cinder-local-api cinder-local-worker
docker rm cinder-local-api cinder-local-worker
docker build -f backend/Dockerfile -t cinder-local .
docker run -d --name cinder-local-api -p 8000:8000 -v cinder-local-data:/data -e CVT_DATABASE_URL=sqlite:////data/cinder.db cinder-local
docker run -d --name cinder-local-worker -v cinder-local-data:/data -e CVT_DATABASE_URL=sqlite:////data/cinder.db cinder-local python -m app.scripts.run_worker
```

No database migration, reset, or reseeding is needed. Keep your own database and
volume settings if they differ. For a native backend, reinstall the bundled
package with the backend virtual environment active, then restart the API and
worker:

```powershell
cd backend
python -m pip install --force-reinstall --no-deps ../cvtModel
```

Run `npm run dev` from `frontend/`, or `npm run build` for production. Both
regenerate API types. If using Docker without host Python, first export the new
API contracts (PowerShell, from the repository root):

```powershell
New-Item -ItemType Directory -Force backend/generated | Out-Null
docker run --rm --mount "type=bind,source=$($PWD.Path)/backend/generated,target=/contracts" cinder-local python -m app.scripts.export_contract_artifacts --output-dir /contracts
cd frontend
$env:CINDER_SKIP_BACKEND_EXPORT = "1"
npm run dev
```

## Changes

- Review opens before simulation validation finishes. Input checks update after
  edits, ignore obsolete responses, support retry, and retain the current check
  when returning without changes. Run stays disabled until the current inputs
  pass. Submission still performs authoritative backend validation.
- JSON-defined flyweight geometry is compiled once per backend process and
  cached in a bounded 32-entry cache. The complete geometry, ramp, tolerances,
  and compilation settings form the key. Mass moments remain separate. Every
  decoded assembly receives its own copy; concurrent identical cold requests
  share one compilation. New geometry still undergoes the original full audit.
- Page dropdowns stay below the fixed header. Shared modal controls retain
  portalled dropdowns above their dialog. Mantine's detached-target hiding
  remains enabled. Overlay layers and modal behavior are centralized.
- Space toggles playback even when a button, slider, checkbox, or link has
  focus. Actual text editing retains normal spaces; Enter still activates
  buttons. Fullscreen selects its active player without double toggles.
- Plot cursors subscribe directly to the ready chart and update on initial
  rendering, size changes, zoom, and legend changes, without requiring hover.
- Collapsed playback navigation remains a fixed sidebar rail with an expand
  button and labelled icon links. The player follows the shell's sidebar
  offset. Mobile navigation remains full-width when opened.
- Author links, directory names, and the signed-in header name lead to
  `/people/:userId`. Profiles show name, school, and public vehicle setups,
  CVTs, engines, belts, load cases, and runs. Tunes remain under CVTs.
  Profiles and the public catalog use the same tabs, library cards, filters,
  and run list. Server-side author filters apply before run pagination/counts;
  existing readability and ownership checks remain in place. Profiles expose
  no email or account credentials. API types are generated from OpenAPI.

## Verification

- Production frontend build, TypeScript and contract generation pass. ESLint
  has zero errors and the same two existing warnings in the primary-design
  and validation pages. Changed Python files pass syntax/import checks.
- Geometry audit and runtime outputs matched the pre-patch implementation
  exactly at 501 travel positions. Changed mass remains independent; changed
  compilation settings recompile; invalid dimensions and impossible contact
  branches fail; cached data cannot be mutated through a decoded map.
- Four concurrent requests produced one geometry compilation and independent
  runtime maps. Local validation measured 7.247 s cold and 0.0021 s for changed
  road/initial-speed inputs sharing that geometry. This is validation timing,
  not end-to-end browser or simulation timing; cold geometry remains costly.
- API acceptance checks passed for anonymous/owner profiles, missing/system
  users, author filtering across physical categories and load cases, excluded
  private/archived physical items, and filtered run totals/pagination.
- Existing direct frontend checks passed for chart sizing at 280/420/760 px,
  zoom preservation as data grows, replay notifications, stored preferences,
  and scene shaft direction.
- Browser preview access was blocked by the execution environment. Interactive
  browser checks below remain manual. No new unit/E2E suite or CI changes.

## Manual browser pass

1. Open Review, change duration, and navigate back/forward. The summary should
   remain usable, obsolete checks should not enable Run, and unchanged inputs
   should not need another request. Check both validation errors and retries.
2. Open a CVT picker and scroll past it: the header stays above it. Repeat
   inside a create/edit modal; its picker should stay visible above the modal.
3. Open demo/playback without hovering plots. Check the cursor immediately,
   after switching tabs, resizing, zooming, and expanding a chart.
4. Focus a scene button or player slider, press Space, and repeat in fullscreen.
   There should be one toggle. Spaces in text/search fields should still work.
5. Collapse navigation and scroll to the bottom. The rail and expand control
   remain visible; the player aligns with the remaining content width. Check
   full mobile navigation after opening its header button.
6. Open two different authors from People and from run/library attribution.
   Browse each profile's categories, follow a CVT to its tunes, and check a
   logged-out view, an empty category, and a missing profile.
