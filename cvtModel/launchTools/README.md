# CINDER launchTools — circular-primary / traction-first update

Replace the contents of your existing `tools2/` launch-tools folder with this
folder. No production CINDER source file is modified. The tools use CINDER's
existing `CircularSegment` profile and select it only while constructing the
Baja diagnostic baseline.

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

With the supplied updated CINDER source and LSODA, the 10 s reference run
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
python tools2/run_tuned_launch.py --duration-s 10 --no-show `
  --output-dir artifacts/circular_traction_first
```

The defaults already select the circular reference and LSODA settings.

## Re-run the saved linear reference

```powershell
python tools2/run_tuned_launch.py --manual `
  --flyweight-mass-kg 0.55 --helix-angle-deg 20 `
  --secondary-twist-deg 140 --secondary-preload-mm 70 `
  --primary-ramp-kind linear --primary-ramp-angle-deg 30 `
  --duration-s 10 --max-step-ms 10 --relative-tolerance 3e-5 `
  --no-show --output-dir artifacts/linear_slow_reference_rerun
```

## Search workflow

```powershell
python tools2/screen_launch_tuning.py --no-show `
  --output-dir artifacts/circular_screen

python tools2/preflight_launch_sweep.py `
  --ranked-csv artifacts/circular_screen/ranked_tunes.csv `
  --top-n 6 --duration-s 10 --no-show `
  --output-dir artifacts/circular_preflight

python tools2/run_tuned_launch.py `
  --ranked-csv artifacts/circular_preflight/full_launch_ranked.csv --rank 1 `
  --duration-s 10 --no-show --output-dir artifacts/circular_selected
```

The default static screen studies 20° helix, 0.75–0.85 kg flyweights,
260–300° secondary twist, 100–110 mm secondary preload, and 38–40° →
28–30° circular profiles. Narrow or widen those command-line ranges rather
than editing the tool code.

## Secondary attachment refactor

The launch tools now assemble the same locked final-drive vehicle through
CINDER's explicit `LockedFinalDriveVehicle` attachment.  CLI inputs, figures,
CSV columns, route behavior, and current default results are unchanged.  This
is an internal ownership cleanup: CINDER's CVT core now receives a secondary
boundary condition rather than directly assuming that every secondary load is
a rigid vehicle.

The standard route scripts still use a locked vehicle attachment, so they keep
reporting vehicle speed, distance, road force, and reflected road torque as
before.  Future secondary-dyno and one-way-bearing experiments can instead
supply another secondary attachment without modifying the belt/contact
closure or these normal vehicle workflows.
