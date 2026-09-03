# Launch then hill climb

This is the first example of the results-layer convention.

## Question

How does the frozen Baja CINDER 1.0.0 reference respond to a full-throttle
launch followed by a sustained uphill load?

## Baseline

The study loads:

```text
../../defaults/baja_reference_simulation_case.json
```

No CINDER hardware, tune, engine, vehicle, friction, initial-state, solver, or
reporting value is duplicated in `study.json`.

## Intentional changes

`study.json` changes only:

- simulation end time from 5 s to 10 s;
- road profile from flat everywhere to:
  - 0° from 0 m;
  - 15° from 15 m onward.

The road profile is encoded as CINDER's public
`piecewise_constant_grade` document, whose segments are distance-based.

## Run

With the release environment activated:

```bash
python results/cinder-v1.0.0/studies/launch-hill-climb/run.py
```

## Generated artifacts

The script recreates `artifacts/` and writes:

- `resolved_simulation_case.json` — complete exact executed input;
- `result.json` — complete public projected CINDER result;
- `summary.json` — compact study/provenance/termination summary;
- `report.csv` — flattened report table;
- `primary_speed_rpm.png`;
- `vehicle_speed_kmh.png`;
- `cvt_ratio.png`;
- `shift_position_mm.png`;
- `clamp_forces_N.png`;
- `road_grade_deg.png`.

The CVT ratio plotted is the instantaneous effective-radius reduction ratio

```text
secondary effective radius / primary effective radius
```

which is the kinematic `omega_primary / omega_secondary` ratio in ideal belt
contact.
