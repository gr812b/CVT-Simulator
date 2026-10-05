# Playback, roads and force visualization — October 2026

This update builds on the UI consistency patch (base commit `4c6d76f`).
It adds no dependencies, database migration, unit tests or CI changes.

## User-facing changes

- Playback analysis has Overview, Primary, Secondary, Engine and Belt & slip
  tabs. Each starts with two plots; users can select up to four and expand one.
  Inactive plots unmount. Timeline/camera state stays in the shared playback;
  independent X/Y zoom and legend selections survive plot/tab changes.
- Clicking a plot selects a retained report frame. Speed-based plots select the
  nearest point on their trajectory. Very short partial results show an inline
  notice instead of blocking browser alerts.
- A Forces control selects the primary or secondary movable assembly, individual
  contacts and torques, axial/radial/tangential components, labels, arrow scale
  and transparent hardware. Resultants and components use a common force scale;
  shaft torques use curved arrows and a separate torque scale.
- Active queued/validating/running jobs have a disabled playback action with an
  explanation. Direct playback URLs also check status before loading results.
  Stopped partial results remain accessible. Configuration links retain exact
  pinned revisions without showing a version suffix in their labels.
- The road editor fits the available width and keeps equal physical axis scales.
  Zoom, background panning, Fit course and Fit section replace forced horizontal
  scrolling. Sections can be selected, reordered, duplicated and removed; point
  dragging and exact coordinates remain available under advanced editing.
  The load-case modal is wider and keeps save actions at its bottom edge.
- The retained demo and a new CINDER default load case share one 160 m course:
  30 m flat, 30 m at +35°, 10 m flat, 30 m at −35°, 10 m flat, 20 m at +20°,
  then 30 m flat. The simulation stops at its finish. Lengths are along the road.
- Landing and demo use the same sign-in/create-account or workspace/sign-out
  header. The demo's public-library link and the workspace's Explore/demo entry
  are removed.
- `backend/README.md` includes Windows drive switching, Docker first setup,
  rebuild/recreate, reseeding, frontend type generation and log commands.

## Force conventions and implementation boundary

`cinder_gateway` remains the only backend module importing CINDER. It supplies
the resolved mechanism contact geometry and analytical belt tension field to
`application/force_projection.py`. The latter projects retained report values;
it never reruns a simulation or solves a new closure. New HTTP contracts live
in `schemas/scene.py`; frontend API shapes come from generated OpenAPI types.

- Forces act on the selected movable assembly. Positive axial closes that
  pulley, radial points outwards, and tangential follows positive shaft rotation.
  Torque signs follow the shaft convention, independently of the axial axis.
- The reported belt normal resultant covers both faces. The movable face's axial
  load is `−N cos(beta)/2`. Six integrated wrap sectors display the normal and
  traction loads using CINDER's tension field and eight quadrature points per
  sector. Torque sharing follows the configured helical element; rigidly guided
  pulleys use symmetric face sharing. The torque arrow reports the corresponding
  share of the retained belt torque.
- Primary roller forces share the retained dynamic flyweight reaction across
  the modeled contacts and use CINDER's selected ramp normal. Secondary rollers
  use the retained dynamic helix reaction and local `dtheta/dx`; the three contact
  vectors satisfy the ideal helix's virtual-work relation.
- Springs show assembly resultants. Shaft/bearing, primary torque-guide and
  travel-stop reactions are not reported. The UI identifies this as a contact
  view, rather than claiming a complete equilibrium diagram.
- Unsupported or missing channels stay absent. Report indices accompany force
  samples so two event states at the same timestamp remain distinguishable.
  Larger trajectories use fewer display samples while retaining event pairs,
  contact-validity boundaries and endpoints; raw plots and CSV retain all rows.
- Force data loads only when requested. Geometry is prebuilt for the fixed demo.
  The overlay shares the scene's frame loop, runs after the mechanism pose update,
  skips unchanged paused frames, and releases its geometry/material resources
  when disabled or unmounted. Theme colors remain centralized.

Road input and course playback share the arc-length-to-horizontal projection.
Dragging uses its inverse, so physical angles and distances remain consistent.
The demo builder and additive seed use `roads.demo_scenario()` as their single
course definition. Regenerate retained examples deliberately with
`python -m app.scripts.build_demo`; this is never part of an HTTP request.

## Application

Apply this patch after `CINDER_UI_Consistency.patch`. From the repository root
(adjust only the download folder if needed):

```powershell
git apply --check "$HOME\Downloads\CINDER_Playback_Roads_Forces\CINDER_Playback_Roads_Forces.patch"
git apply "$HOME\Downloads\CINDER_Playback_Roads_Forces\CINDER_Playback_Roads_Forces.patch"
```

Rebuild/recreate the API and worker using the commands in `backend/README.md`,
run normal `init_database` seeding to add the demo load case, and restart
`npm run dev` to regenerate API contracts. A database wipe is unnecessary.
The regenerated demo and both lightweight scene projections are included.

## Verification

- Frontend production build, generated contracts and TypeScript compilation.
- Frontend lint: zero errors; the two existing hook dependency warnings remain
  in the primary-design and validation pages.
- Changed backend files pass import/undefined-name checks. The force projection
  also passes the complete configured Ruff rules.
- The real demo completes its 160 m course, and its retained road definition
  matches the seeded load case. Repeated seeding creates no duplicate course.
- Demo projection: 23 force/torque tracks across 1,441 retained frames. Belt
  axial totals match the movable-face normal projection to about `1.4e-12 N`;
  ramp/helix totals, torque signs, finite values and helix virtual work checked.
  Cold projection from prebuilt demo geometry took about 0.65 s here, excluding
  network transfer and browser rendering.
- Anonymous demo/force endpoints, active-run rejection, and result-bearing
  completed/failed/timed-out/cancelled access checked against a disposable API.
- Frontend data checks confirm all default tab plots exist in the real demo,
  35° road geometry and point-drag coordinate round trips, exact force frames
  including duplicate timestamps, missing-contact gaps, and paused replay state
  for newly mounted charts. A dense projection check preserves event pairs and
  original report-row mapping when display samples are reduced.
- The documented Alembic upgrade path was exercised against a disposable copy
  of the existing local database. Docker itself is unavailable in this workspace.

Interactive visual verification remains outstanding: the provided browser
rejects the running local preview with `ERR_BLOCKED_BY_CLIENT`. Build, data and
API checks are not a substitute for browser inspection.

## Local walkthrough

1. Open `/demo` signed out and signed in; check the shared header and pinned
   playbar. Switch analysis tabs while paused and playing, hide a series, change
   both axis zooms, expand/close a plot and return to the original tab.
2. Enable Forces, pause on the climb, switch between movable assemblies and
   toggle each component, contacts, torque arrows, labels and transparency.
   Scrub through engagement and toggle the overlay off/on.
3. Open the new default demo load case. Fit the full course and a section, zoom
   and pan, change an incline angle/length, reorder sections, drag a custom point,
   undo and save a named copy. Repeat at a narrow viewport width.
4. Queue a run and inspect its disabled playback explanation. Try its playback
   URL while active; after it stops, confirm retained results open normally and
   configuration links show names without version suffixes.
