# Generated comparison results

The Ballew study keeps two complementary protocols.

- `run_comparison.py`: corrected **force replay**, with Figure 45 imposed as primary clamp and
  Figure 41 as the response reference.
- `run_closed_loop_comparison.py`: reconstructed **PI + feed-forward controller**, with Figure 41
  and Figure 45 both treated as outputs for comparison.
- `controller_reconstruction.py`: source-consistency audit for the published controller gains and
  inferred sign/units.

## Important v9 provenance note

The first runs after the A10 friction-convention correction terminated very early with an exact
singular closure. That was subsequently traced to deadzone-side geometry derivatives being used at
an **engaged** low-ratio boundary during ODE event localization. It is a resolved hybrid-boundary
implementation defect, not a physical CINDER-vs-Ballew result. See `../SINGULARITY_DIAGNOSIS.md`.

The old v9 partial traces are preserved under `legacy_boundary_derivative_bug/`. Canonical
`force_replay/` and `closed_loop/` now contain the successful five-second v11 runs generated after
both hybrid-boundary/admissibility corrections.

## Output contract

When a full run completes, the force-replay runner writes `comparison_overview.png`,
`cinder_diagnostics.png`, `cinder_trace.csv`, native-time RPM/ratio comparisons,
`transitions.csv`, `metrics.json`, and `summary.md`.

The closed-loop runner writes primary/secondary RPM, ratio, Figure-45 controller-force comparisons,
a uniform CINDER trace, transition history, internal diagnostic plot, `metrics.json`, and `summary.md`.
Both runners still preserve any future genuine failure as `termination.json` plus a reproducible partial
trace rather than tuning the model to continue.

`legacy_raw_mu_replay/` remains historical only because it used Ballew's raw `0.55/0.40` directly as
CINDER lambda limits before A10 corrected the convention translation.

## Final numerical-convergence audit

`convergence/` contains the frozen-physics four-case closed-loop refinement study. The macroscopic speed, ratio, force-error, shift envelope, and mode occupancy are converged. Raw transition-count variation is isolated to tolerance-sensitive kinetic slip-direction zero-crossing bookkeeping; all runs contain 1411 substantive contact/constraint transitions. See `../FINAL_STUDY.md` for the combined interpretation.


## Numerical-stability figure

`numerical_stability/` recasts the archived convergence sweep against the integration scale reported by Ballew (2015). The figure marks Ballew's roughly `0.01 ms` fixed-step scale and shows that CINDER's headline errors remain effectively invariant across tested `max_step` values of `0.25--1.00 ms`. Because CINDER uses adaptive LSODA, this is a convergence/operating-scale comparison rather than a direct fixed-step or wall-clock speedup. See `numerical_stability/NUMERICAL_STABILITY_NOTE.md`.


## Broad numerical-stability stress test

`numerical_stability/stress_test/` contains the 72-case solver-control stress test used to map the numerical operating envelope beyond the original four-point convergence audit. The canonical interpretation is `../NUMERICAL_STABILITY_RESULTS.md`.

For paper use, emphasize numerical accuracy, actual adaptive timestep scale, accepted integration-step count, and the separation between substantive topology transitions and kinetic slip-direction zero-crossing bookkeeping. Wall-clock/Pareto timing is intentionally not part of the headline comparison because the original Ballew implementation was not benchmarked on the same hardware.
