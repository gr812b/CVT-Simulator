# Numerical robustness methodology

The Ballew case is useful not only as a model-to-model comparison but also as a
numerically demanding hybrid trajectory. The scripts in this study retain two
separate numerical checks so the paper-facing comparison can be distinguished
from solver sensitivity.

No numerical results are stored in this clean source bundle. Both checks write
fresh outputs beneath `artifacts/`.

## Four-case refinement check

`run_convergence.py` evaluates the reconstructed closed-loop case at:

| label | rtol | atol | max step |
|---|---:|---:|---:|
| nominal_1p00ms | 1e-7 | 1e-9 | 1.00 ms |
| nominal_0p50ms | 1e-7 | 1e-9 | 0.50 ms |
| nominal_0p25ms | 1e-7 | 1e-9 | 0.25 ms |
| tight_0p50ms | 3e-8 | 3e-10 | 0.50 ms |

The comparison metrics are evaluated against the Ballew digitizations exactly
as in the canonical closed-loop run. The purpose is to check whether the
reported model-to-model errors materially move under straightforward numerical
refinement.

## Broad stability sweep

`run_stability_sweep.py` asks a different question: over what solver-control
region does CINDER reproduce its own tightly resolved closed-loop trajectory?

The tight **CINDER-only** reference is:

- LSODA;
- `max_step = 0.1 ms`;
- `rtol = 1e-10`;
- `atol = 1e-12`.

It is not physical truth and it is not a fitted Ballew reference. It exists only
to quantify numerical drift as the integrator controls are relaxed.

For each sweep point, the runner compares primary RPM, secondary RPM, speed
ratio, and shift coordinate. The composite score is the maximum relative RMS
error across those four signals, reported in parts per million. Dimensional
errors are also retained.

The runner records accepted internal time-step statistics from CINDER's raw
hybrid segments. This distinction matters because `max_step` is only an upper
bound for an adaptive method; statements about the time scale the solver
actually used should be based on accepted steps, not the configured ceiling.

## Ballew's reported numerical scale

Ballew reports fixed-step fourth-order Runge-Kutta integration with a time step
**on the order of** `1e-5 s` (0.01 ms). Over five seconds this corresponds to an
order-of-magnitude scale of about 500,000 fixed integration intervals. A
straightforward RK4 implementation would evaluate four stages per interval,
roughly two million RHS stages.

That literature value is useful as a **step/work scale only**. It is not an
apples-to-apples wall-clock benchmark because Ballew's distributed-belt model
and CINDER's reduced model have very different state equations and per-step
costs. Do not report a measured CINDER-vs-Ballew speedup unless Ballew's
executable is actually timed under controlled conditions.

## Interpretation boundary

Numerical convergence is not physical validation. These studies establish only
that conclusions drawn from the Ballew comparison are not artifacts of a
fragile CINDER integrator setting.
