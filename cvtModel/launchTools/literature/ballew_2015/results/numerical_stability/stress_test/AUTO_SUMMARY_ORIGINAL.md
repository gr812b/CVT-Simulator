# CINDER numerical stability stress test

## What this experiment answers

This sweep separates four different questions that should not be conflated:

1. **Accuracy:** how far does a run move from a tight CINDER numerical reference?
2. **Hybrid robustness:** does it complete, and does the transition topology remain the same?
3. **Numerical work:** how many accepted adaptive steps / RHS evaluations / LU factorizations are required?
4. **Wall-clock usefulness:** how quickly does the five-second physical trajectory run on this machine?

`max_step` is an upper bound, not the actual CINDER time step. The actual accepted step statistics are therefore reported separately.

## Literature reference scale

Ballew reports fixed RK4 time steps on the order of **1e-05 s = 0.01 ms** for numerical stability.
Across a 5 s run, that corresponds to an order-of-magnitude fixed-step count of **500,000 steps**.
A straightforward four-stage RK4 implementation is therefore on the order of **2,000,000 RK stage evaluations**, before considering Ballew's per-step belt geometry/search work. This is a work-scale reference, not a measured runtime comparison.

## Sweep result

- Completed cases: **72 / 72**
- Failed/incomplete cases: **0**
- Fastest <=100 ppm case: max_step=0.3 ms, rtol=1e-06, error=51.79 ppm, wall=88.59 s, real-time factor=0.0564×, nfev=58,282, accepted steps=27,980.
- Fastest <=1000 ppm case: max_step=300 ms, rtol=1e-05, error=244.9 ppm, wall=68.76 s, real-time factor=0.0727×, nfev=43,684, accepted steps=19,263.
- Largest allowed max_step still <=100 ppm: max_step=300 ms, rtol=1e-10, error=0.007975 ppm, wall=147.8 s, real-time factor=0.0338×, nfev=119,453, accepted steps=56,482.
- Current benchmark nominal point: max_step=1 ms, rtol=1e-07, error=21.46 ppm, wall=97.18 s, real-time factor=0.0514×, nfev=69,942, accepted steps=31,954.

## Step-scale comparison

The largest **allowed** CINDER max_step that remains within 100 ppm in this sweep is 300 ms, or **30,000× (4.48 decades)** above Ballew's reported ~0.01 ms fixed-step scale.
More importantly, that case's 95th-percentile **actual accepted adaptive step** is 0.2843 ms, **28×** the Ballew fixed-step scale. This is the cleaner numerical-efficiency comparison because it does not confuse max_step with the steps LSODA actually accepted.

## Runtime comparison within CINDER

On this machine, the fastest <=100 ppm case is **1.10×** faster than the current benchmark nominal setting. This is an apples-to-apples CINDER-vs-CINDER timing comparison.
Its accepted-step count is about **18× smaller** than the ~500,000-step fixed-step scale implied by Ballew's reported 10 µs step over five seconds. This is a step-count comparison, not a wall-clock speedup claim.

## Claims this supports

- CINDER's macroscopic closed-loop trajectory can be mapped over several decades of solver controls instead of being demonstrated at only four already-converged points.
- The plot can show where numerical error actually begins to grow and where hybrid integration eventually fails, if that boundary is reached by the chosen preset.
- Actual adaptive step sizes, accepted-step counts, nfev/njev/nlu, and wall time can be reported directly.
- Ballew's ~10 µs fixed-step requirement can be used as a published numerical-work scale.

## Claims this does **not** support by itself

- A direct wall-clock speedup of CINDER over Ballew. That requires running both implementations on controlled hardware.
- That a larger CINDER `max_step` is itself an actual larger integration step. Use the recorded internal dt distribution for that statement.
- Physical validation of CINDER merely because the numerical solution is converged.

## Generated figures

- `00_numerical_stability_story.png` — four-panel hero figure.
- `01_stability_envelope_heatmap.png` — filled accuracy/failure map.
- `02_speed_accuracy_pareto.png` — wall-time vs trajectory-error frontier.
- `03_solver_work_vs_max_step.png` — accepted steps, nfev, and real-time factor.
- `04_trajectory_stress_overlay.png` — where coarsening becomes visible in the physical trajectory.
- `05_actual_internal_step_scale.png` — actual adaptive step sizes versus Ballew's fixed-step scale.
- `06_method_comparison.png` — optional solver-method comparison.
