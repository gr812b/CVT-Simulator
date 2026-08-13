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
