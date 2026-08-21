# Package provenance

This final drop-in was assembled from:

- `CINDER_Ballew_2015_dropin_v11.zip` — canonical five-second force-replay and closed-loop benchmark implementation/results.
- `Ballew_closed_loop_convergence_study.zip` — frozen-physics numerical-convergence audit.

No CINDER physics, benchmark constants, digitized reference data, or controller gains were changed while assembling this package. Added/updated study-level files are `FINAL_STUDY.md`, `results/convergence/`, `results/numerical_stability/`, `results/headline_metrics.csv`, `plot_numerical_stability.py`, `run_numerical_performance_sweep.py`, and navigation notes. The numerical-stability addition does not modify the benchmark physics or controller; it visualizes the already-archived convergence data and adds an optional reproducible timing sweep.


## v15 numerical-stability result addition

The package additionally incorporates `numerical_stability_stress_test.zip`, generated from `run_numerical_stability_stress_test.py` against the unchanged Ballew closed-loop benchmark. The stress study changes solver controls only. No CINDER physics, reconstruction constants, controller gains, or initial conditions were changed.

The canonical interpretation is `NUMERICAL_STABILITY_RESULTS.md`. Wall-clock-focused plots from the exploratory stress harness are deliberately excluded from the canonical figure set; raw timing fields remain in the archived CSV/JSONL for provenance. Two derived figures were added from the same archived sweep: accepted adaptive-step count versus tolerance and substantive-transition/zero-crossing decomposition.
