# v15 drop-in manifest

Extract this archive at the repository root. It is rooted at `cvtModel/` and may be overlaid directly onto the `ballew-comparison` branch.

## New canonical numerical-stability material

- `NUMERICAL_STABILITY_RESULTS.md` — paper-facing interpretation of the full solver stress test.
- `results/numerical_stability/stress_test/README.md` — same interpretation colocated with the raw results.
- `results/numerical_stability/stress_test/01_stability_envelope_heatmap.png`
- `results/numerical_stability/stress_test/04_trajectory_stress_overlay.png`
- `results/numerical_stability/stress_test/05_actual_internal_step_scale.png`
- `results/numerical_stability/stress_test/06_adaptive_step_count_vs_tolerance.png`
- `results/numerical_stability/stress_test/07_transition_decomposition_vs_tolerance.png`
- `results/numerical_stability/stress_test/stress_sweep.csv`
- `results/numerical_stability/stress_test/raw_results.jsonl`
- `results/numerical_stability/stress_test/reference_and_literature_scales.json`
- exact CSV data underlying the two added derived plots.

## Updated navigation / interpretation

- `FINAL_STUDY.md` now includes the broad 72-case stress-test result.
- `README.md` points readers to the final study and numerical-stability result note.
- `results/README.md` explains which numerical outputs are canonical.
- `PACKAGE_PROVENANCE.md` records the source of the stress-test artifacts and makes clear that solver controls only were changed.
- `NUMERICAL_STABILITY_STRESS_TEST_GUIDE.md` now notes that wall-clock/Pareto timing is exploratory rather than a headline comparison.

## Claim boundary

The canonical result is numerical convergence and adaptive integration efficiency in terms of accepted step scale/count. This drop-in does **not** claim a measured wall-clock speedup over Ballew.
