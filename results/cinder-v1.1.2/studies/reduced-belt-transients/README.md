# Reduced-belt transient mechanics — final closure study

## Scientific question

Within CINDER's dynamically closed reduced whole-belt model, **which terms that survive in the final solved belt equations can become mechanically important, what physical variables make them grow, and does a reasonable Baja operating envelope actually reach those conditions?**

The reference trajectory studies remain discovery-first and leave the production CINDER model untouched. The final closure stage adds two **explicit experimental continuations** for the belt-inertia question: one temporarily scales only the whole-belt transport inertia row as an isolation test, and one scales belt density coherently so global and local belt inertia vanish together. These are study-local experiments, not production model switches.

The study now deliberately uses two independent lenses:

1. **equation sensitivity** — derive and map how each surviving term grows with its physical driver, ratio geometry, and traction utilization;
2. **Baja operating-envelope simulation** — sample realistic signed road loads, disturbance timescales, naturally reached ratios/speeds, and a small documented preload-robustness range.

A later reduction is justified only where these two views agree.

## Physical terms being studied

Whole-belt transport is

\[
m_b\dot v_b+\tau_p/r_{p,\mathrm{eff}}+\tau_s/r_{s,\mathrm{eff}}=0.
\]

The independent tension-loop compatibility contains four transient mechanisms plus the contact-load contribution:

\[
F_{\mathrm{shift\ accel}}
+F_{\mathrm{path\ curvature}}
+F_{\mathrm{belt\ accel}}
+F_{\mathrm{moving\ radius}}
+F_{\mathrm{contact}}=0.
\]

The transient terms are exactly

\[
F_{\mathrm{shift\ accel}}
=K_{\mathrm{shift\ accel}}(s)\,\ddot s,
\]

\[
F_{\mathrm{path\ curvature}}
=K_{\mathrm{path\ curvature}}(s)\,\dot s^2,
\]

\[
F_{\mathrm{belt\ accel}}
=K_{\mathrm{belt\ accel}}(s,\lambda_p,\lambda_s)\,\dot v_b,
\]

\[
F_{\mathrm{moving\ radius}}
=K_{\mathrm{moving\ radius}}(s,\lambda_p,\lambda_s)\,\dot s\,v_b.
\]

This split is central to the study. A contribution may be small because its response coefficient is weak, because the Baja trajectory never supplies a large driver, or both.

## Equation-level sensitivity

`equation_sensitivity.py` evaluates the final-equation coefficients without integrating a trajectory.

The radial coefficients are mapped over the full engaged shift range. The traction-sensitive coefficients are mapped over static-contact utilization using the exact regular wrap functions. Three representative active shift fractions (0.1, 0.5, 0.9) are evaluated, and an independent primary/secondary traction-demand grid prevents a symmetric-contact path from hiding asymmetric behavior.

The analysis also verifies the exact traction-reversal structure numerically:

- the tangential wrap coefficient \(H\) is odd in signed \(\lambda\);
- the normal/contact coefficient \(G\) is even in signed \(\lambda\).

Therefore an idealized simultaneous drive-to-overrun traction reversal flips the sign of the tangential transient coefficients at fixed utilization magnitudes while preserving the corresponding \(G\) coefficients. Dynamic overrun trajectories can still change \(N_j\), \(|\lambda_j|\), and the operating state, so this symmetry is an equation property rather than a substitute for an overrun simulation.

### Equation-derived importance thresholds

Two different notions of "small" are now kept separate.

The **gross-force threshold** compares a transient term with

\[
F_C=|G_pN_p|+|G_sN_s|,
\]

which answers whether the term is large compared with the underlying contact-force inventory. This is useful context, but it is not the equation-importance verdict because the two contact contributions can nearly cancel.

The primary **final-equation activity threshold** instead freezes the other surviving terms. If term \(i\) is to contribute fraction \(\alpha\) of total absolute equation activity,

\[
\frac{|F_i|}{|F_i|+\sum_{k\ne i}|F_k|}=\alpha,
\]

then

\[
|F_i|_\alpha=\frac{\alpha}{1-\alpha}\sum_{k\ne i}|F_k|.
\]

Since \(F_i=K_iD_i\), the required driver is obtained directly from this force target. The study reports 1%, 5%, 10%, and 25% activity thresholds and the dimensionless ratio

\[
\chi_i=\frac{|D_i|}{|D_i|_{10\%,\mathrm{activity}}}.
\]

Thus \(\chi_i=1\) now means exactly that the mechanism would be 10% of the **final solved equation activity** at that operating state if the other surviving contributions were locally frozen. The old gross-contact thresholds remain in the CSVs under explicit `gross_threshold` names.

## Existing broad and controlled cases

The previous study stages are retained because they provide interpretable anchors:

- flat launch and natural upshift;
- 8°, 18°, and 28° spatial uphill load steps;
- a controlled 18° road-load application over 0, 50, 200, and 800 ms;
- controlled 8°, 18°, and 28° applications at a fixed 200 ms rise.

The zero-rise case is now described as an **instantaneous road-load application**, not an "ideal CVT step": only the road grade/load is discontinuous; the CVT states respond dynamically.

## Smart Baja operating envelope

`envelope_design.py` adds a deterministic low-discrepancy design instead of a Cartesian sweep.

The default design uses 18 Halton samples plus six mechanistic anchors and four preload-robustness anchors. Reference-tune samples span:

- signed grade/load: approximately \(-20^\circ\) downhill/unloading to \(+30^\circ\) uphill/loading;
- load application time: 50–800 ms on a logarithmic scale;
- disturbance start time: 1.05–3.35 s during the natural full-throttle acceleration, so the actual pre-disturbance ratio and belt speed vary naturally.

Near-zero grade changes are intentionally excluded from the space-filling set because the flat baseline already covers weak forcing.

The negative-grade cases probe **downhill/unloading under the normal full-throttle engine boundary**. They are not labelled closed-throttle overrun or engine braking. Equation sensitivity separately exposes the traction-reversal symmetry; a dedicated measured/defined engine-braking boundary can be added later if the paper needs a true overrun trajectory.

### Tune robustness anchors

The repository's existing fixed-pivot tuning helper searches secondary compression preload from 105–115 mm and torsional pretension from 280–320°. The envelope therefore adds only two documented edge variants around the 110 mm / 300° reference:

- 105 mm + 280°;
- 115 mm + 320°.

These are called lower/higher **secondary preload** variants, not assumed clamp-force multipliers. The resulting normal loads and \(|\lambda|/\mu_s\) are measured directly. This lets the study ask whether the baseline conclusions survive plausible contact-demand changes without changing the friction coefficient simply to manufacture a larger utilization fraction.

## What the synthesis asks

For every free-stick case, `sensitivity_synthesis.py` compares the actual kinematic driver with its equation-derived 10% threshold. The principal output is therefore not merely the largest force term but:

- which mechanisms ever cross their 10% threshold;
- how often they do so;
- which Baja case and physical state produces the strongest crossing;
- the ratio, grade, belt speed, shift speed/acceleration, and contact utilization at that point;
- whether increasing contact demand strengthens the traction-sensitive coefficients as the equations predict.

This provides the desired connection:

\[
\text{equation growth law}
\rightarrow
\text{predicted threshold}
\rightarrow
\text{Baja state that does or does not reach it}.
\]

## Final closure stage

The final stage resolves the remaining questions identified by the Baja-envelope and equation-sensitivity work.

### High-contact and mixed-slip search

Friction coefficients are held fixed. Contact demand is increased physically by weakening one clamp mechanism at a time while applying a +30° / 100 ms road-load event during active shifting. Five primary-actuation scales, five secondary-reaction scales, and three combined cases are used. CINDER's existing hybrid contact logic decides whether each trajectory remains stick-stick, enters primary-slip/secondary-stick, enters primary-stick/secondary-slip, or reaches both-slip.

The primary stress family scales the fixed-pivot flyweight mass and all of its mass moments together. The secondary family scales the axial-spring and torsional-reaction stiffnesses together. These are stress-study variants, not proposed competition tunes.

Principal outputs are `contact_closure_summary.csv`, `mixed_slip_examples.csv`, `contact_asymmetry_vs_moving_radius.png`, and `moving_radius_by_slip_mode.png`.

### Controlled overrun

Two cases retain the normal drive boundaries until 2.0 s, then smoothly ramp the road to -20° while ramping the primary boundary torque to either -5 or -12 N·m. The synthesis explicitly checks whether the resulting samples satisfy

\[
P_p<0,\qquad P_s>0,
\]

so the study reports whether true secondary-to-primary power flow was actually achieved rather than assuming that a downhill road is automatically overrun. This is a controlled boundary experiment, not a calibrated closed-throttle engine map.

### Belt-inertia continuation

Three representative scenarios are tested: flat acceleration, a fast +30° backshift load, and a fast -20° unloading event.

For each scenario the full model is compared with two asymptotic continuations at 0.10x and 0.03x inertia:

1. `global_transport` scales only the \(m_b\dot v_b\) coefficient in the whole-belt transport row. This isolates structural sensitivity to that small row term, but is not by itself a physical reduced belt.
2. `coherent_density` scales belt density, so both whole-belt mass and local wrap linear-density inertia vanish together. This is the physically coherent massless-belt limit.

Trajectory comparisons report RMSE/max errors in \(\omega_p,\omega_s,v_b,s,\dot s\), plus hybrid transition-count changes.

## Running

Run the complete study, including the smart envelope:

```powershell
python studies/reduced-belt-transients/run.py
```

Equation sensitivity only:

```powershell
python studies/reduced-belt-transients/run.py --stage sensitivity
```

Smart Baja envelope only (equation sensitivity is generated too):

```powershell
python studies/reduced-belt-transients/run.py --stage envelope
```

Final unresolved closure studies only:

```powershell
python studies/reduced-belt-transients/run.py --stage closure
```

Change the number of low-discrepancy samples while retaining the fixed anchors:

```powershell
python studies/reduced-belt-transients/run.py --stage envelope --envelope-points 30
```

Previous natural/controlled stages remain available:

```powershell
python studies/reduced-belt-transients/run.py --stage broad
python studies/reduced-belt-transients/run.py --stage controlled
```

Pure tests only:

```powershell
python studies/reduced-belt-transients/run.py --tests-only
```

## Principal new outputs

Direct equation analysis under `artifacts/equation_sensitivity/`:

- `geometry_sensitivity.csv`;
- `contact_sensitivity.csv`;
- `contact_pair_sensitivity.csv`;
- `radial_coefficients_vs_shift.png`;
- `belt_acceleration_coefficient_vs_contact_demand.png`;
- `moving_radius_coefficient_vs_contact_demand.png`;
- `summary.json`.

Baja-envelope design and observed coverage:

- `baja_envelope_design.csv`;
- `baja_envelope_observed_coverage.csv`;
- one normal per-case atlas for every envelope case.

Equation-to-simulation connection:

- `equation_threshold_coverage.csv` — per case and mechanism;
- `equation_connection_examples.csv` — strongest observed Baja example for each mechanism;
- `baja_envelope_equation_coverage.csv` — envelope-level threshold coverage;
- `baja_envelope_vs_equation_thresholds.png`;
- `contact_demand_vs_belt_acceleration_coupling.png`;
- `equation_to_simulation_synthesis.json`.

All earlier phase-aware outputs remain.

Final closure outputs:

- `contact_closure_summary.csv`;
- `contact_stick_targets.csv`;
- `mixed_slip_examples.csv`;
- `overrun_summary.csv`;
- `inertia_continuation_comparison.csv`;
- `closure_failures.csv`;
- `closure_synthesis.json`;
- `contact_asymmetry_vs_moving_radius.png`;
- `moving_radius_by_slip_mode.png`;
- `inertia_continuation_<scenario>.png`.

## Decision gate

Do not reduce a term solely because it was small in the canonical launch. A reduction becomes a serious candidate only after the study has established both:

1. the equation-level combination of geometry, contact demand, and kinematic driver that could make it grow; and
2. whether reasonable Baja conditions or documented tune variations actually approach that region.

Only then should a coherent reduced formulation be implemented and compared against complete trajectories plus the energy/invariant checks.
