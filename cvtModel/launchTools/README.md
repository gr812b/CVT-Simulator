# CINDER launchTools — circular-primary / traction-first update

These launch tools are written against the composed CINDER architecture. They build a CVT assembly, attach primary/secondary shaft boundaries, and run the resulting `ComposedCVTHybridSystem`.

## What changed

- The primary ramp can now be either `linear` or `circular_hard_to_soft`.
  The circular option uses a single quadrant-2 circular segment, so the
  flyweight radial slope stays positive but decreases continuously with shift.
- The default manual run is a traction-first circular reference:
  `m=0.80 kg`, `helix=20°`, `twist=300°`, `secondary preload=110 mm`,
  circular ramp `38° → 30°`.
- Primary preload is still solved from the 2000 rpm lower-stop-release target.
  It is not a free sweep variable.
- The full-run metrics now report `primary_restuck_time_s`,
  `primary_restuck_primary_rpm`, `primary_restuck_shift_mm`, and
  `primary_slip_duration_s`. The dynamic preflight ranks earlier re-stick
  rather than only shift onset and shift duration.
- Transition labels are compact: `low stop`, `engage`, `low seat`,
  `shift start`, `re-stick`, and `high stop`. Labels on the dotted event lines
  use a smaller font.
- Each detailed run writes `primary_ramp_profile.png`, showing radial
  displacement, local slope, and centrifugal axial-force curves.
- The prior linear slow-shift result is preserved under
  `saved_runs/linear_slow_reference/`, including its original PNG, CSV, and
  JSON. It can be reproduced with the command below.

## Current circular reference

With the supplied updated reorganized CINDER source and LSODA, the 10 s reference run
completed with:

- main low-ratio-seat release: **3071 rpm**;
- primary re-stick: **2.20 s** after launch (about **2.09 s** in primary slip);
- main 10–90% shift: **3.97 s**;
- peak main-shift speed: **52.4 mm/s**;
- high-stop impact: **6.06 s**;
- one engagement and no re-disengagement.

For comparison, the archived linear reference remained in primary slip until
about 6.29 s. The new reference is deliberately not presented as a final
physical tune: the `300°` secondary pretension and `110 mm` secondary preload
are an exploratory traction-first setting that should be checked against your
actual spring travel and hardware limits.

## Run the circular reference

```powershell
python launchTools/run_tuned_launch.py --duration-s 10 --no-show `
  --output-dir artifacts/circular_traction_first
```

The defaults already select the circular reference and LSODA settings.

## Re-run the saved linear reference

```powershell
python launchTools/run_tuned_launch.py --manual `
  --flyweight-mass-kg 0.55 --helix-angle-deg 20 `
  --secondary-twist-deg 140 --secondary-preload-mm 70 `
  --primary-ramp-kind linear --primary-ramp-angle-deg 30 `
  --duration-s 10 --max-step-ms 10 --relative-tolerance 3e-5 `
  --no-show --output-dir artifacts/linear_slow_reference_rerun
```

## Search workflow

```powershell
python launchTools/screen_launch_tuning.py --no-show `
  --output-dir artifacts/circular_screen

python launchTools/preflight_launch_sweep.py `
  --ranked-csv artifacts/circular_screen/ranked_tunes.csv `
  --top-n 6 --duration-s 10 --no-show `
  --output-dir artifacts/circular_preflight

python launchTools/run_tuned_launch.py `
  --ranked-csv artifacts/circular_preflight/full_launch_ranked.csv --rank 1 `
  --duration-s 10 --no-show --output-dir artifacts/circular_selected
```

The default static screen studies 20° helix, 0.75–0.85 kg flyweights,
260–300° secondary twist, 100–110 mm secondary preload, and 38–40° →
28–30° circular profiles. Narrow or widen those command-line ranges rather
than editing the tool code.

## Composed simulation architecture

The launch tools build the same physical Baja baseline through the current public path:

1. construct a `CVTAssemblySpec`;
2. create `MechanicalCVTPlant.from_assembly(assembly)`;
3. connect `FullThrottleEngineBoundary` on the primary shaft;
4. connect `LockedFinalDriveShaftBoundary` on the secondary shaft;
5. carry secondary shaft angle in `SecondaryShaftAngleHost`;
6. run the resulting `ComposedCVTHybridSystem`.

The CVT core receives only primary/secondary shaft-port values. Vehicle speed, distance, road load, and reflected road torque are reported from secondary-boundary metadata. A dyno, brake, motor, tire-coupled vehicle, or custom host can be connected by replacing the shaft boundary and host without changing the CVT plant.

## Uniform exported traces

The normal diagnostic tools use the composed hybrid runner directly and export a uniform report grid sampled from SciPy's per-segment dense solution. The adaptive solver trace is still kept internally for audits and exact event timing. Every hybrid transition is added as its own exact pre/post pair even if it falls between report-grid points, so a CSV may contain repeated timestamps at a real reset or impact.

`--plot-samples` / `--diagnostic-samples` are optional display/export caps.
When omitted, the full 10 ms report grid is written. Wrapper scripts forward to the canonical composed route-grade runner unless they add their own study-specific post-processing.


The route-grade default report step is 50 ms. Use `--report-step-s` for denser exported CSV/plots when needed.
