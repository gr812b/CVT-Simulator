# Playback balances and scene cleanup

Incremental update after `b14fd19` / `CINDER_Playback_Roads_Forces.patch`.

## Behavior

- Fixed assemblies use silver-blue; movable assemblies use gold, including
  ramps, hubs and secondary roller carriers. Springs use a separate color
  because they connect both assemblies. Both assemblies still rotate.
- Transparent mode covers every physical mesh: belt, shafts, springs,
  flyweights, rollers, tracks and sheaves. Force arrows and grids stay readable.
  Turning it off restores each material's original settings.
- Plain shafts extend in the same world direction toward the external shaft
  boundaries; the secondary shaft passes through its actuator carrier. Dimensions outside the resolved contact geometry are illustrative.
- The large floating plot values box and both axis sliders are removed. Hover
  values, compact series keys, the replay cursor, scroll zoom, rectangular
  X/Y selection, reset and image export remain.
- Overview opens with speed, acceleration, ratio and shift curve. Primary and
  secondary open with axial balance, actuator breakdown and torque balance.
  Radius rates remain an optional plot rather than the primary default.
- Replay navigation collapses on desktop; its preference survives reloads.
  Course axes retain equal metres per pixel without the redundant captions.
- Run time histories automatically fetch new checkpoints, retain the displayed
  curve during refresh/error, and fetch the full report after the run stops.
  Signal selection and zoom survive data updates. Preview-only retained runs
  still work. Changing signals resets the vertical range.
- The default demo finishes a 160 m course with segments:
  30 m flat, 30 m at +45°, 10 m flat, 30 m at −35°, 10 m flat,
  20 m at +30°, 30 m flat. The McMaster setup and tune are unchanged.
  Re-seeding advances the default load case by appending an immutable revision;
  existing runs keep their original course. Other setups can stall normally.

## Reporting

The bundled CINDER source is version `1.1.5.dev0`. Only reporting changes;
no integration equations or numerical settings change. The backend installs
`../cvtModel` through its requirements, and Docker installs the same source.
This does not require a PyPI release. Run provenance distinguishes this version
from previous output.

Balance channels come from the solver inspections already used by reporting,
without additional closure solves or differentiation of stored trajectories.
New `balance.primary.*` and `balance.secondary.*` columns include:

- Belt axial force, axial spring, remaining actuator force, signed travel-stop
  reaction and translating-mass inertial demand.
- Belt torque, mechanism coupling torque, effective shaft inertial demand and
  solved angular acceleration.

Axial forces use local groove-closing sign. Thus belt opening forces and engaged
stop reactions are negative. The primary deadzone lower stop acts positive.
The force balance is spring + mechanism + belt + stop = mass × axial acceleration.
Secondary axial loads stay unavailable during deadzone, whose reduced belt lock
has no solved normal resultant. Its rotational balance includes the exact belt
transport-inertia torque, without counting that inertia twice.

The shaft balance is boundary torque + belt torque + mechanism coupling torque
= effective inertia × angular acceleration. The effective inertia includes
mounted mechanisms' acceleration coefficients; the coupling channel retains
other terms in the same solver equation. The charts do not present a residual
estimate as a measured support load. Existing flyweight and helix contribution
channels supply the detailed breakdowns. Primary deadzone actuator reporting
now resolves dynamic terms using its actual solved accelerations instead of zero.

Older retained runs do not acquire missing solver channels retroactively.
Their available plots remain usable; new runs and the regenerated demo contain
all balance plots. The frontend continues to use generated API contracts.

## Apply and run

From the repository root, after the preceding playback/roads/forces patch:

```powershell
git apply --check CINDER_Playback_Balances_And_Scene.patch
git apply CINDER_Playback_Balances_And_Scene.patch
docker build -f backend/Dockerfile -t cinder-local .
```

Recreate **both** API and worker containers with the commands in `backend/README.md`.
Run the normal seed command to update the default course. No database wipe or
migration is required. The new demo is already included; do not regenerate it
as part of startup. Restart the frontend; a production deployment needs a build.

For a native backend environment, reinstall from `backend/`:

```powershell
python -m pip install -r requirements-dev.txt
```

This installs the local CINDER reporting update as well. The worker still
requires Linux/POSIX and should run in Docker on Windows.

## Verification

- Frontend production build, generated contracts and TypeScript compile pass.
  Lint has no errors; the same two existing hook warnings remain in the legacy
  primary designer and validation page.
- The real default demo completes at 160 m in 15.035 s. Both grades are present.
  Across all 1,571 report rows, maximum force-balance residual is below
  1.4e-11 N and maximum torque-balance residual is below 2.9e-14 N m.
- API checks verify the demo, force projections, stopped/active guards, shared
  default course and repeat-seed behavior in a disposable database copy.
- Code-level frontend checks verify requested plot data, contact gaps and exact
  transition frames, equal-axis road geometry, all assembly colors, recursive
  transparency/restoration of 32 materials in 13 models, camera bounds and
  slider-free X/Y zoom configuration.
- Interactive browser verification is blocked in this environment:
  `ERR_BLOCKED_BY_CLIENT` opening the local preview. Before merging, manually
  check live refresh/zoom, sidebar collapse, plot interactions and transparent
  WebGL rendering. Docker itself is unavailable here; its source installation
  path is checked separately.

No unit tests or CI changes were added.
