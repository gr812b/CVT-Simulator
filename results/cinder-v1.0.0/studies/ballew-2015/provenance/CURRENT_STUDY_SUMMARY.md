# Canonical Ballew comparison summary carried into the results tree

## Purpose

The migrated study preserves the final interpretation of the pre-port Ballew
work while separating it from newly generated artifacts. This is a
**model-to-model benchmark** against Ballew's 2015 discretized rubber-belt
simulation, not experimental validation.

Two protocols must be interpreted together:

1. **Force replay** — impose Ballew Figure 45 primary clamp history on CINDER.
2. **Closed loop** — reconstruct Ballew's published PI + feed-forward controller
   around unchanged CINDER and compare both shaft response and clamp demand.

A solver-convergence/stability audit then asks whether the differences are
numerical or model-form driven.

## Historical headline results

| Protocol | Primary RPM RMSE | Secondary RPM RMSE | Speed-ratio RMSE | Primary-force RMSE |
|---|---:|---:|---:|---:|
| Force replay | 1796.1 rpm (71.88%) | 38.3 rpm (3.19%) | 1.4513 (69.61%) | imposed input |
| Closed loop | 109.7 rpm (4.39%) | 32.9 rpm (2.74%) | 0.1093 (5.24%) | 1180.2 N (46.04%) |

In the historical closed-loop result, mean CINDER primary clamp demand was about
`1517.29 N`, versus about `2563.68 N` for the visible digitized Ballew Figure 45
trace.

## Physical interpretation

### Force replay

The poor primary-speed and ratio agreement under an identical clamp-force
history demonstrates that Ballew's distributed belt/contact model and CINDER's
reduced global-shift model do **not** map clamp force into radial migration / ratio
change in the same way. This is a plant-model difference, not a failed attempt to
reproduce an identical set of governing equations.

Secondary speed remains relatively close because the vehicle/load boundary and
system inertia strongly constrain that macroscopic channel even while the
primary/ratio trajectories diverge.

### Closed loop

With Ballew's reconstructed controller, unchanged CINDER follows the published
shaft-speed and ratio trajectory much more closely: approximately 3–5% error in
the macroscopic speed quantities. It does so with a substantially different
primary clamp-force history.

That combination is important. Feedback can drive two different plants onto
similar controlled operating trajectories even if the internal force-to-shift
mapping differs strongly. Therefore the speed agreement is encouraging evidence
for macroscopic closed-loop behavior, but it does **not** validate CINDER's clamp
force, local belt deformation, radial migration field, or contact distribution
against Ballew.

## Historical convergence result

The legacy four-case closed-loop refinement held all physical/controller inputs
fixed while refining maximum integration step and LSODA tolerances. The headline
errors changed by only microscopic amounts:

| Case | Primary RMSE (rpm) | Secondary RMSE (rpm) | Ratio RMSE | Force RMSE (N) |
|---|---:|---:|---:|---:|
| 1.00 ms | 109.6651 | 32.92155 | 0.1092994 | 1180.2276 |
| 0.50 ms | 109.6651 | 32.92155 | 0.1092994 | 1180.2274 |
| 0.25 ms | 109.6650 | 32.92155 | 0.1092994 | 1180.2271 |
| 0.50 ms, tighter tolerance | 109.6649 | 32.92154 | 0.1092994 | 1180.2267 |

The tightest comparison against the original 1 ms run gave approximately:

- RMS primary-speed difference: `0.005 rpm`;
- maximum primary-speed difference: `0.011 rpm`;
- maximum speed-ratio difference: `9.52e-06`;
- maximum shift-coordinate difference: `1.226 µm`.

The macroscopic closed-loop result is therefore numerically converged at the
scales relevant to the Ballew comparison.

## Raw transition-count caveat

The historical raw transition count changed with tolerances because
`kinetic_slip_direction_updated_at_zero_crossing` is event-bookkeeping around
`v_rel=0`. The substantive contact/constraint topology was stable across the
converged cases. Exact raw transition count should not be presented as a physical
observable.

## Broad numerical-stability result

The later stress sweep explored a much larger LSODA control envelope. All 72
archived five-second cases completed. At nominal `rtol=1e-7`, once `max_step`
stopped actively limiting the adaptive solver, the composite trajectory error
versus the tight CINDER reference was only about `0.00215%`. Error remained very
small at `rtol=1e-5`, rose progressively around `1e-4`, and became model-scale at
`1e-3`.

Ballew reports a fixed fourth-order Runge-Kutta integration scale around
`1e-5 s` for stability. The archived CINDER stress analysis compared **accepted
adaptive step/work scale**, not wall-clock speedup. At nominal tolerance its
reported median accepted step was about `0.0914 ms` and the 95th percentile about
`0.4656 ms`; the five-second Ballew scale implies roughly 500,000 fixed steps,
while the converged CINDER benchmark used about 31,815 accepted adaptive steps.
Those figures should not be converted into a claim that CINDER is "X times
faster" because stage cost and implementation differ.

The exact raw stress-test dataset, plots and interpretation are materialized into
`artifacts/historical-v1.0.0/numerical_stability/`.

## Defensible paper-level conclusion

> The macroscopic closed-loop response is numerically converged. CINDER can
> reproduce Ballew's controlled shaft-speed and speed-ratio evolution to roughly
> 3–5% under the source-constrained controller reconstruction, despite predicting
> substantially different clamp-force requirements and internal shift dynamics.
> Force replay confirms that the two formulations have materially different
> force-to-shift mechanics. The remaining comparison discrepancy is therefore
> dominated by model form rather than integration resolution.

This conclusion is intentionally narrower than "validation" and should stay that
way in the paper.
