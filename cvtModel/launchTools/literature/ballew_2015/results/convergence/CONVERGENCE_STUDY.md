# Ballew 2015 closed-loop numerical convergence study

Physical inputs and controller reconstruction were frozen. Only numerical controls changed.

## Cases

- 1.00 ms max step, rtol=1e-7, atol=1e-9
- 0.50 ms max step, rtol=1e-7, atol=1e-9
- 0.25 ms max step, rtol=1e-7, atol=1e-9
- 0.50 ms max step, tighter rtol=3e-8, atol=3e-10

## Main result

The macroscopic solution is strongly converged. Primary RPM, secondary RPM, speed-ratio,
primary-force error, shift envelope, and compact hybrid-mode occupancy are effectively invariant
to step refinement and tighter tolerances.

The exact raw transition count is not converged. The entire difference comes from
`kinetic_slip_direction_updated_at_zero_crossing` events. After excluding those pure kinetic
direction updates, every case contains exactly 1411 substantive contact/constraint transitions.

The compact regime occupancy is identical to the displayed precision in every case.

This means the Ballew comparison's ~4.4% primary-speed error, ~2.7% secondary-speed error,
~5.24% speed-ratio error, and ~46% primary-force RMSE are not numerical-step artifacts.
However, the exact number of kinetic slip-direction reversals should not be interpreted as a
physical observable without further event-level regularization/analysis.
