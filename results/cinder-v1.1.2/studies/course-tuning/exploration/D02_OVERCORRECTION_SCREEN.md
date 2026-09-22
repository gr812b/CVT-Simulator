# D02 flyweight over-correction screen

This overlay adds one exploratory competitor file only. It does not modify the selected/final course fleet, its selection lock, or any CINDER model source.

## Question

Starting from `D02_M` (reference tip mass with D02's 115% primary preload), how far can primary centrifugal actuation be increased before the severe 38-degree hill response changes from a useful traction repair into insufficient backshift?

The screen keeps D02's primary preload at 115% and changes only replaceable flyweight tip mass. The existing Results tuning resolver updates the corresponding flyweight total mass, first moment, and second moment consistently.

Cases:

- `D02`: 65% tip, 115% primary preload — original adverse anchor
- `D02_P`: 65% tip, 100% preload — preload-repair anchor
- `D02_M`: 100% tip, 115% preload — mass-repair anchor
- `D02_M110`: 110% tip, 115% preload
- `D02_M120`: 120% tip, 115% preload
- `D02_M130`: 130% tip, 115% preload
- `D02_M140`: 140% tip, 115% preload
- `D02_M150`: 150% tip, 115% preload

## Run

From `results/cinder-v1.1.2` in the frozen Results environment:

```bash
python studies/course-tuning/exploration/run.py \
  --course studies/course-tuning/inputs/course.json \
  --competitors studies/course-tuning/exploration/inputs/d02_overcorrection.json \
  --preset tight \
  --cars D02 D02_P D02_M D02_M110 D02_M120 D02_M130 D02_M140 D02_M150 \
  --jobs 4 \
  --resume \
  --focus D02 D02_P D02_M D02_M110 D02_M120 D02_M130 D02_M140 D02_M150
```

The campaign remains under `studies/course-tuning/exploration/artifacts/` and does not change the final-study fingerprint.

## What to return/check

Return the generated campaign folder or ZIP it. The most useful first-pass quantities over the main hill (120-224 m, especially the 132-212 m 38-degree hold) are:

1. minimum shift coordinate / maximum backshift drawdown,
2. whether and when the low-ratio seat is reached,
3. primary RPM through the hill,
4. vehicle speed and whether progress is maintained,
5. primary static traction utilization and slip intervals,
6. primary flyweight/spring/belt axial-force balance.

For manuscript use, do not automatically select the heaviest or fastest case. Prefer the least-extreme mass increase that gives a clear qualitative over-correction: primary traction remains adequate, but the CVT backshifts materially less than `D02_M`, leaving the engine/vehicle response worse for a ratio-related reason rather than renewed traction failure.
