# Complete Baja GPS-to-simulator validation run

## Reproduced pipeline

1. Strict obstacle-definition validation.
2. GPS timestamp/coordinate/speed cleaning and lap segmentation.
3. Reference centreline construction and ordered single-`s` map matching.
4. Physical-feature projection and declared response grouping.
5. Per-pass approach, entry, minimum, end, traversal, kinetic-state-change, and recovery metrics.
6. Robust median/IQR/percentile event summaries and grouping identifiability audit.
7. Uniform-anchor slowdown signatures relative to the whole-track baseline.
8. Reset-at-entry event cases and continuous-lap templates for simulator validation.

## Run counts

- Clean GPS rows: 4462
- Complete laps detected: 13
- Laps retained: 11
- Physical definitions: 40
- Analysis groups: 37
- Aggregate-eligible event passes: 403 of 481
- Slowdown signatures: 21 strong, 11 moderate, 8 weak

## Interpretation boundary

These outputs measure repeatable vehicle speed states and provide validation targets. They do not identify absolute terrain-energy loss, braking causation, grade work, or tire slip from GPS alone. Use paired candidate comparisons and uncertainty sweeps.
