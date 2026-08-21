# Numerical stability and step-scale comparison

## Why this figure is included

Ballew's 2015 thesis explicitly identifies numerical stiffness as a limitation of the discretized
belt formulation. Section 3.8 describes a fourth-order fixed-step Runge-Kutta integrator and reports
that unusually small time steps were required for numerical stability. The thesis states that the
steps used were on the order of `1e-5 s` (about `0.01 ms`) and recommends future variable/scaled
stepping partly to reduce simulation time.

That makes numerical behavior a legitimate point of comparison, but the comparison must be stated
carefully. Ballew's `~10 us` value is a **reported fixed integration-step scale**. CINDER uses adaptive
LSODA, so its `max_step` is only an upper bound on an internally selected step. The figure therefore
compares **numerical operating scales and convergence**, not identical solver steps and not
wall-clock speed.

## What the archived CINDER study shows

The same five-second closed-loop problem was solved with maximum CINDER steps of `0.25`, `0.50`,
and `1.00 ms`, plus a tighter-tolerance `0.50 ms` reference. Relative to that tightest case, the
largest changes in the headline errors are:

- primary-speed RMSE: `0.000226%`;
- secondary-speed RMSE: `0.000059%`;
- speed-ratio RMSE: `0.000011%`;
- clamp-force RMSE: `0.000076%`.

Thus CINDER's tested `max_step` range is 25--100 times Ballew's reported fixed-step scale while the
macroscopic closed-loop result remains effectively unchanged. This is useful evidence that the
reduced CINDER formulation is substantially less restrictive numerically for this benchmark.

## What this does *not* establish

Do not report a direct `X times faster than Ballew` wall-clock speedup from this figure. The original
Ballew implementation was not benchmarked on the same hardware, language/runtime, or exact
problem instance. A fair runtime statement requires a reproducible wall-clock benchmark.

`run_numerical_performance_sweep.py` is included beside the benchmark runner for that purpose. It
re-runs the closed-loop case over a wider step/tolerance grid, records wall-clock time, and measures
trajectory drift against a tight reference. Run it on the same machine/environment used for the
paper's final simulations before publishing any absolute runtime or real-time-factor claim.

## Canonical figure

`numerical_stability_envelope.png` plots the archived convergence data and marks Ballew's reported
`~0.01 ms` fixed-step scale. `stability_plot_data.csv` contains every plotted CINDER value and the
25--100x scale multiples.
