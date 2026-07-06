# CINDER tuned-launch visual refinement

This overlay fixes the functional regressions in the visual-preserving Phase 4 frontend while keeping its original input page, dashboard/table, demo entry, graph-card layout, playback bar, and GLB scene.

## What changed

- The sole default is now **Baja Tuned Launch**, generated directly from `launchTools/run_tuned_launch.py`.
- Its CINDER document uses the exact 10.00 s launch configuration: 10 ms reporting grid, LSODA, 20 ms maximum step, 0.80 kg flyweights, 20° helix, 300° secondary twist, 110 mm secondary preload, and a 38°→30° circular input ramp. The primary preload is the lower-stop release value resolved at 2000 rpm: **104.614547969 mm**.
- The original **Load Simulation** page and **View Demo** route work again using the CINDER preset API. No static legacy demo data or old saved-parameter format returns.
- Frontend persistence keys advance to `v2`, so stale 1.5 s documents/runs cannot be restored after deployment.
- The original charts stay in place but now read only CINDER result-table signals. CINDER reporting now supplies the small set of channels the visual cards require: vehicle acceleration, three road-load components, ratio/radius rates, and engine power.
- Playback validates and uses the canonical report time axis. Event-boundary duplicate timestamps remain valid; a non-monotone or malformed axis is rejected instead of being silently coerced.

## Verified tuned-launch run

Using the supplied CINDER source with the included backend overlay, the exact stored document completed with:

- report axis: **0.00 s → 10.00 s**
- rows: **1013**
- hybrid segments: **7**
- transitions: **6**
- final vehicle distance: **93.0132 m**
- final vehicle speed: **13.3541 m/s**
- warnings: **none**

That confirms the report supplied to the replay controller contains the full 10 s timeline and a changing `vehicle.distance` column.

## Apply

1. Start from the previous visual-preserving Phase 4 frontend, or from the provided `src.zip` frontend after applying that visual refinement.
2. Copy this bundle's `src/` directory over the frontend's `src/` directory. No dependency changes are required.
3. In the backend repository root, copy:
   - `backend/presets/baja-launch-baseline.json` to `presets/baja-launch-baseline.json`.
   - `backend/src/cinder/results/reporting.py` to `src/cinder/results/reporting.py`.
   - `backend/src/cinder/contracts/conventions.py` to `src/cinder/contracts/conventions.py`.
4. Restart the backend, then run `npm ci`, `npm run lint`, and `npm run build` in the frontend.

`APPLY_TUNED_LAUNCH_REFINEMENT.ps1` performs those copy operations when pointed at the frontend root and backend repository root.

## Deliberate non-changes

- The editable UI remains limited to the old visible tuning surface. Other CINDER document fields stay at the tuned-launch baseline values.
- Browser imports create a session-only CINDER document draft. Backend presets remain immutable.
- No streamed percent progress is restored.
