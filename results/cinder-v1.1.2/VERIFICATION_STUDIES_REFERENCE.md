# CINDER v1.1.2 Verification / Invariant Studies Reference

**Purpose:** Preserve the agreed verification plan in one place before implementation work continues.  
**Scope:** This document captures the four verification studies that together establish numerical/mechanical correctness of the CINDER `v1.1.2` results release. One is already complete; three remain to be built.

---

# 1. Overall verification structure

The verification package is intentionally split into four distinct studies:

1. **Energy consistency** — already completed.
2. **Mechanical invariants** — local equation/constraint/admissibility consistency.
3. **Closure conditioning** — numerical/mathematical well-posedness of the instantaneous algebraic solves.
4. **Solver convergence** — trajectory independence from LSODA settings.

These answer different questions and should remain separate even if they ultimately appear near one another in the manuscript.

The clean conceptual split is:

\[
\boxed{\text{Energy consistency}}
\]

asks whether power input/output, stored energy, slip dissipation, and event/capture losses close globally.

\[
\boxed{\text{Mechanical invariants}}
\]

asks whether the computed trajectory satisfies the equations, constraints, and inequality/admissibility conditions locally.

\[
\boxed{\text{Closure conditioning}}
\]

asks whether the instantaneous algebraic closure is well posed and numerically stable over the physical operating region.

\[
\boxed{\text{Solver convergence}}
\]

asks whether the time trajectory is a property of the model equations rather than the chosen numerical tolerances / maximum step.

Together, these form the internal-verification package. They do **not** constitute direct physical validation against experiment.

---

# 2. Reproducibility / implementation note for the final Results chapter

Near the beginning of the Results chapter, include a short section on code, release inputs, and reproducibility.

It should:

- identify the exact CINDER release/tag used for all results;
- link to the public repository / release-scoped results tree;
- record frozen baseline inputs and study-specific overrides;
- record solver settings and artifact provenance;
- distinguish the derivation-level presentation from the implementation-level numerical organization.

A specific implementation note should explain that the manuscript may present a reduced mechanical response system for clarity, while the actual production implementation solves a complete **8×8 affine mechanical closure** over

\[
[
\dot\omega_p,\,
\dot\omega_s,\,
\dot v_b,\,
\ddot s,\,
\tau_p,\,
\tau_s,\,
N_p,\,
N_s
].
\]

The implementation uses that organization for numerical robustness and direct auditability of the coupled mechanics; it does not alter the underlying physical equations.

Keep this distinct from the nonlinear stick-root problem:

- **8×8 mechanical closure conditioning**
- **2×2 stick-root conditioning** in \((\lambda_p,\lambda_s)\)

The code-verification results should audit the system that the implementation actually solves.

---

# 3. Study 1 — Mechanical energy consistency

**Status:** DONE / PASS

## 3.1 Scientific question

**Does modeled external work equal retained stored-energy change plus explicitly modeled irreversible losses, up to numerical error?**

The accounting is conceptually:

\[
W_{\rm ext}
=
\Delta E_{\rm stored}
+
E_{\rm slip}
+
E_{\rm event}
+
R_E
\]

where \(R_E\) is the residual that should converge toward numerical-error scale.

Important interpretation:

- **External work** is energy crossing the modeled system boundary through applied boundary torques.
- **Stored energy** is energy currently retained in model states / energy stores.
- **Slip loss** and **impact/capture loss** are modeled irreversible losses.

## 3.2 What was audited

- global energy closure;
- continuous-segment energy defects;
- exact hybrid-event energy defects;
- event momentum / constraint consistency;
- quadrature refinement;
- ODE solver refinement;
- stick-pair numerical work used only as a numerical drift diagnostic.

## 3.3 Current conclusion

The large structural energy inconsistency found during development was corrected before `v1.1.2`.

Current evidence supports:

- exact event/capture energy accounting closes to machine-scale numerical precision;
- the old large active-shift energy defect disappeared from raw production mechanics after the representative secondary contact-speed correction;
- remaining global continuous energy residual is sub-ppm relative to energy throughput at tight integration;
- the residual changes with numerical refinement rather than behaving like a stable missing physical sink/source;
- no evidence remains for another material omitted storage/dissipation channel within the retained model.

## 3.4 Interpretation boundary

This verifies the **implemented retained mechanics**.

It does **not** prove that physical effects omitted from the model are negligible in reality.

---

# 4. Study 2 — Mechanical invariants

**Status:** PLANNED  
**Directory concept:** `studies/mechanical-invariants/`

## 4.1 Scientific question

**Does the integrated trajectory remain on the mechanical and admissibility manifolds required by the formulation?**

Energy closure is global bookkeeping. This study checks the local equations and physical inequalities directly.

## 4.2 Required invariants / checks

At minimum, audit the following over the complete reference trajectory.

### A. Belt geometry / loop closure

\[
L_{\rm belt}\text{ closure}
\]

Record the belt-length residual through time and report the worst absolute violation.

Useful outputs:

- maximum absolute belt-length residual;
- RMS residual;
- residual at event-adjacent samples;
- optional time trace if structure is visible.

### B. Instantaneous mechanical closure residual

For the implemented 8×8 system,

\[
A\mathbf{x}=\mathbf b
\]

record

\[
\mathbf r_A=A\mathbf{x}-\mathbf b.
\]

Report:

- maximum absolute equation residual;
- scaled / normalized residual;
- per-equation maxima if useful;
- matrix rank at each solved point.

This should audit the **actual implementation closure**, not only the reduced manuscript algebra.

### C. Stick velocity compatibility

When a contact is declared sticking,

\[
v_{\rm rel,j}\approx0.
\]

Audit separately for primary and secondary:

\[
|v_{\rm rel,p}|,
\qquad
|v_{\rm rel,s}|.
\]

For the secondary, use the current representative contact speed with the helix torque-share correction.

### D. Stick acceleration compatibility

Where acceleration-level stick compatibility is active / meaningful,

\[
a_{\rm rel,j}\approx0.
\]

Audit:

\[
|a_{\rm rel,p}|,
\qquad
|a_{\rm rel,s}|.
\]

This catches cases where velocity compatibility may look good while acceleration closure is drifting.

### E. Static-friction admissibility

For declared stick states,

\[
|\lambda_j|\le\mu_s.
\]

Useful reported quantity:

\[
\Delta_{\lambda,j}
=
\max(0,|\lambda_j|-\mu_s)
\]

so the headline maximum should ideally be zero up to tolerance.

### F. Kinetic-slip sign consistency

For declared sliding contact, the Coulomb sign must oppose relative motion.

Check that the implemented convention satisfies the intended dissipative sign:

\[
\lambda_j\,v_{\rm rel,j}\le0
\]

under the chosen sign convention, equivalently that

\[
P_{{\rm contact},j}
=
\lambda_jN_jv_{\rm rel,j}
\le0.
\]

Report:

- number of sign violations;
- worst positive contact power, if any;
- minimum / maximum slip relative speed around transitions.

### G. Contact normal-force admissibility

\[
N_p\ge0,
\qquad
N_s\ge0.
\]

Report:

- minimum \(N_p\);
- minimum \(N_s\);
- count/duration of any negative values.

Any true negative resultant in an active unilateral contact requires interpretation rather than being hidden by clipping.

### H. Unilateral stop admissibility

When at the low-ratio seat or upper stop, verify the unilateral reaction has the physically admissible sign.

When the stop is inactive/free, verify no impossible reaction is being retained.

Audit separately:

- low-ratio seat reaction;
- upper-stop reaction;
- transition/release logic around zero reaction.

### I. Active kinematic constraints

Record residuals for any active belt-lock / stop / engagement constraints, especially around hybrid transitions.

This complements the event-energy audit.

### J. Post-transition constraint consistency

The energy study already audited exact event energy and momentum. The invariant study should include a compact check that post-event states satisfy the newly active constraints to numerical precision.

## 4.3 Preferred headline artifact

A compact table such as:

| Requirement | Worst observed value | Status |
|---|---:|---|
| Belt-length residual | ... m | PASS |
| 8×8 closure residual | ... | PASS |
| Stick \(v_{\rm rel,p}\) | ... m/s | PASS |
| Stick \(v_{\rm rel,s}\) | ... m/s | PASS |
| Stick \(a_{\rm rel,p}\) | ... m/s² | PASS |
| Stick \(a_{\rm rel,s}\) | ... m/s² | PASS |
| Static-friction excess | ... | PASS |
| Positive kinetic-slip power | ... W | PASS |
| Minimum \(N_p\) | ... N | PASS |
| Minimum \(N_s\) | ... N | PASS |
| Invalid low-seat reaction | ... N | PASS |
| Invalid upper-stop reaction | ... N | PASS |

Time histories should be added only where they reveal useful structure.

## 4.4 Suggested reference trajectory

Use one release-scoped reference trajectory that exercises:

- engagement/capture;
- low-ratio seat;
- active continuous shift;
- upper-stop arrival if present;
- at least one stick/slip transition if naturally present.

The study should be reusable on additional trajectories later, but one canonical trajectory is enough for the release-level invariant table.

## 4.5 Desired conclusion

Something like:

> Across the reference trajectory, the integrated solution remains within numerical tolerance of the belt geometry, algebraic closure, active contact compatibility conditions, Coulomb admissibility bounds, unilateral normal-force conditions, and stop constraints.

---

# 5. Study 3 — Closure conditioning

**Status:** PLANNED  
**Directory concept:** `studies/closure-conditioning/`

## 5.1 Scientific question

**Is the instantaneous algebraic closure well posed and numerically well conditioned over the physical states and traction-utilization regions CINDER actually encounters?**

This study has two distinct layers.

---

## 5.2 Part A — 8×8 mechanical closure conditioning

At every sampled trial \((\lambda_p,\lambda_s)\) pair and every actual solved trajectory point, record:

\[
\operatorname{rank}(A),
\]

\[
\kappa(A),
\]

and preferably the existing scaled condition number

\[
\kappa_{\rm scaled}(A).
\]

Also retain the post-solve equation residual.

The scaled condition number is important because the 8×8 matrix mixes equations/unknowns with very different physical units and magnitudes.

### Questions to answer

- Does \(A\) ever lose rank?
- Where does \(\kappa(A)\) become large?
- Does scaling substantially improve the numerical picture?
- Are poorly conditioned regions inside or outside the physically admissible contact region?
- Does conditioning systematically vary with:
  - shift position;
  - primary / secondary shaft speed;
  - torque/load;
  - contact state;
  - proximity to stops;
  - engagement boundary?

---

## 5.3 Part B — 2×2 nonlinear stick-root conditioning

For stick-stick closure,

\[
\mathbf R(\lambda_p,\lambda_s)
=
\begin{bmatrix}
R_p\\
R_s
\end{bmatrix}
\]

with Jacobian

\[
J_R
=
\frac{\partial(R_p,R_s)}
{\partial(\lambda_p,\lambda_s)}.
\]

The old residual-map work already sampled this surface and generated:

- \(R_p\) map;
- \(R_s\) map;
- residual norm;
- explicit zero contours;
- signed \(\det J_R\).

That was useful, but the formal conditioning analysis should be upgraded.

### Required Jacobian metrics

Keep the signed determinant for geometric interpretation, but add singular values:

\[
\sigma_{\min}(J_R),
\qquad
\sigma_{\max}(J_R),
\]

and condition number

\[
\kappa(J_R)
=
\frac{\sigma_{\max}}{\sigma_{\min}}.
\]

Reason:

- determinant alone is not a reliable condition metric;
- a large determinant can simply mean both singular values are large;
- a moderate determinant can hide a very weak direction;
- \(\sigma_{\min}\rightarrow0\) directly reveals a locally degenerate root direction.

---

## 5.4 Lambda-domain hierarchy

Use three distinct map domains.

### A. Baseline physical Coulomb box

Use the actual `v1.1.2` friction coefficients.

This answers:

**Is the physically admissible traction region of the frozen Baja model well behaved?**

### B. Expanded physically plausible range

Use a wider \((\lambda_p,\lambda_s)\) range than the baseline static-friction box.

Purpose:

- avoid making the conclusion depend on one chosen \(\mu_s\);
- understand how residual geometry evolves for other plausible friction levels;
- inspect features just outside the Baja admissible domain.

This should be clearly labeled as a **parametric/mathematical diagnostic**, not a baseline admissible domain.

### C. Broad signed diagnostic range

Retain a large map similar to the old \([-10,10]^2\) example.

Purpose:

- expose asymptotes;
- expose steep residual walls / valleys;
- expose determinant sign changes;
- identify algebraic structures that are invisible in the small physical box.

Again: not physically admissible operation, just a structural diagnostic.

---

# 5.5 Representative frozen states

Do not perform the map at only one quasi-static state.

At minimum, use several physically encountered states:

1. low ratio / near engagement or low-ratio seat;
2. active mid-shift;
3. late shift / near upper range;
4. backshift / load-disturbed state if naturally available;
5. optionally a deliberately stressed state approaching the worst observed conditioning.

For each state, record the actual solved \((\lambda_p,\lambda_s)\) point on top of the map.

---

# 5.6 Root uniqueness / multi-start test

At each representative state:

- seed the stick-root solver from a grid of initial guesses across the admissible lambda region;
- record which guesses converge;
- record the converged roots;
- determine whether all successful solves converge to the same physical root.

Useful outputs:

- convergence-basin map;
- number of distinct roots found;
- residual at each root;
- distance of actual trajectory root from poorly conditioned regions.

This supports a stronger claim than a contour plot alone.

---

# 5.7 Explain the shape, not just the condition number

One of the most interesting goals is to recover and explain the apparent spikes/asymptotes previously seen around certain \(\lambda\) values.

For every major feature:

- identify where it occurs in lambda space;
- trace it back into the assembled equations;
- determine whether it is associated with:
  - a normal-force denominator becoming small;
  - wrap/tension exponential amplification;
  - near-degenerate pulley/contact leverage;
  - geometry-dependent radius or motion ratio;
  - actuator gain;
  - a solved normal resultant approaching zero/infinity;
  - two stick residuals becoming locally nearly redundant.

Possible useful conclusions include structures such as

\[
\lambda\rightarrow\lambda^\star
\Longrightarrow
N_j\rightarrow\infty
\]

or

\[
\sigma_{\min}(J_R)\rightarrow0.
\]

If such a structure exists, the strongest verification figure would show both:

1. **why** the feature occurs mechanically/algebraically;
2. the actual CINDER trajectory remains comfortably away from it.

---

# 5.8 Preferred figures

Potential paper-quality figure set:

1. \(R_p(\lambda_p,\lambda_s)\) with \(R_p=0\) contour.
2. \(R_s(\lambda_p,\lambda_s)\) with \(R_s=0\) contour.
3. residual norm with both zero contours and actual solved root.
4. \(\log_{10}\kappa(J_R)\) or \(\log_{10}\sigma_{\min}^{-1}\).
5. optional signed \(\det J_R\) diagnostic.
6. 8×8 \(\kappa_{\rm scaled}(A)\) map over the same region.
7. multi-start convergence basin.

Not every plot needs to enter the final paper; the study should generate the full diagnostic set.

---

# 5.9 Desired conclusion

Something stronger than merely “the Jacobian is nonzero”:

> Over the physically admissible traction region and representative states encountered by the reference trajectory, the 8×8 mechanical closure remains full-rank and well conditioned after scaling, while the 2×2 stick-root map has a unique, locally well-conditioned physical solution. Poorly conditioned / asymptotic structures exist only in identifiable regions outside or well separated from the operating trajectory.

If the data says something more nuanced, report that instead.

---

# 6. Study 4 — Solver convergence

**Status:** PLANNED  
**Directory concept:** `studies/solver-convergence/`

## 6.1 Scientific question

**Are the reported trajectories properties of the model equations rather than artifacts of LSODA tolerances or maximum step size?**

The result should be more systematic than a simple “tight vs loose” comparison.

---

# 6.2 Tight reference trajectory

Construct one very tight reference trajectory using the same frozen machine/scenario.

This reference is not assumed exact; it is the best available numerical approximation against which the sweep is compared.

Record:

- exact solver settings;
- wall time;
- RHS evaluations / solver work metrics if exposed;
- transition sequence;
- transition times.

---

# 6.3 Main tolerance × max-step sweep

The main grid should vary:

\[
r_{\rm tol}
\]

and

\[
\Delta t_{\max}.
\]

Suggested range:

\[
r_{\rm tol}
=
10^{-2},\,
3\times10^{-3},\,
10^{-3},\,
3\times10^{-4},\,
10^{-4},\,
3\times10^{-5},\,
10^{-5},\,
3\times10^{-6}
\]

and

\[
\Delta t_{\max}
=
100,\,
50,\,
20,\,
10,\,
5\ {\rm ms}.
\]

This is about 40 runs, which is dense enough to make a useful 2D convergence map without becoming absurdly expensive.

Initially tie

\[
a_{\rm tol}
=
10^{-3}r_{\rm tol}
\]

or the same ratio used by the current canonical studies.

---

# 6.4 Independent absolute-tolerance sweep

Because the state vector mixes very different dimensional scales — hundreds of rad/s, belt speed in m/s, and shift position on the order of \(10^{-2}\) m — a scalar `atol` may matter differently across states.

After the main grid, perform a smaller independent `atol` sweep at one or two representative `rtol` values.

Goal:

- determine whether small shift-position/shift-speed states are being limited by absolute tolerance;
- justify the canonical `atol` used in later results.

---

# 6.5 Trajectory error metrics

Do **not** judge convergence only by the final state.

For each state/output \(x_k\), compare candidate run to the tight reference using a normalized RMS error:

\[
E_k
=
\sqrt{
\frac{1}{T}
\int_0^T
\left(
\frac{x_k(t)-x_{k,\rm ref}(t)}
{S_k}
\right)^2dt
}.
\]

Choose physical normalization scales \(S_k\) explicitly.

Also record:

- maximum normalized trajectory error;
- final-state error;
- RMS error per state;
- selected output errors such as ratio / clamp / normal force if useful.

---

# 6.6 Hybrid-sequence convergence metrics

Because CINDER is hybrid, trajectory closeness alone is not enough.

Record:

- transition count;
- exact transition sequence;
- whether the candidate sequence matches the reference;
- corresponding event-time errors;
- maximum event-time error;
- fraction of total time spent in a different contact/regime state;
- whether any event exists in one run but not the other.

This can produce a very useful **hybrid-stability map** over solver settings.

---

# 6.7 Computational-cost metrics

If accessible, record:

- wall-clock runtime;
- RHS/function evaluations;
- accepted/internal steps;
- event-function evaluations.

Then create an accuracy-vs-cost result.

The desirable result is a plateau:

> beyond a certain tolerance / max-step region, numerical error becomes negligible while cost continues increasing.

That justifies the solver settings used by the rest of the results program.

---

# 6.8 Preferred figures

### Figure A — Accuracy heatmap

Axes:

\[
r_{\rm tol}
\quad\text{vs}\quad
\Delta t_{\max}
\]

Color:

\[
\log_{10}(\text{normalized trajectory error}).
\]

### Figure B — Hybrid sequence map

Same axes, cells indicating:

- exact sequence match;
- event-time mismatch only;
- regime mismatch;
- different transition count.

### Figure C — Accuracy vs cost

Computational cost on one axis, trajectory error on the other.

This should make the diminishing-returns region visually obvious.

### Figure D — Absolute-tolerance sensitivity

A compact plot or heatmap showing whether `atol` materially affects the small-dimensional states.

### Optional Figure E — Representative overlaid trajectories

A loose, canonical, and very-tight trajectory overlaid for one or two outputs so the heatmap has an intuitive visual counterpart.

---

# 6.9 Desired conclusion

Something like:

> Below the selected canonical tolerance / maximum-step settings, further tightening produces negligible changes in the continuous states, transition sequence, and event times, while computational cost rises materially. The release-level results therefore operate within the numerically converged region.

The exact threshold should be determined from the sweep rather than prescribed in advance.

---

# 7. How the remaining three studies relate

The remaining verification work should proceed in this order:

1. **Mechanical invariants**
2. **Closure conditioning**
3. **Solver convergence**

Reason:

- Mechanical invariants tell us whether the trajectory obeys the formulation locally.
- Closure conditioning explains whether the algebraic solve itself is numerically healthy and where it becomes difficult.
- Solver convergence then tests the integrated hybrid trajectory across numerical controls.

There is some implementation overlap, so shared utilities may be worthwhile, but the scientific outputs should remain separate.

---

# 8. Things explicitly NOT to conflate

## 8.1 Verification vs validation

Energy closure, invariants, conditioning, and convergence establish internal consistency of the implemented model.

They do **not** establish real-world predictive accuracy.

## 8.2 8×8 vs 2×2 conditioning

The 8×8 mechanical closure and the 2×2 stick-root Jacobian are different mathematical objects and need different diagnostics.

## 8.3 Determinant vs conditioning

\[
\det J_R
\]

is useful for visual/geometric interpretation but is not sufficient as a condition metric.

Use singular values and

\[
\kappa(J_R)
\]

for formal conditioning.

## 8.4 Broad lambda maps vs physical admissibility

A broad \([-10,10]^2\)-style map is useful to reveal algebraic structure.

It is **not** a physical operating region.

## 8.5 Final-state convergence vs trajectory convergence

Matching the final state is insufficient for a hybrid model.

The transition sequence and event timing must also converge.

---

# 9. Expected final verification narrative

Once all four studies are complete, the beginning of the Results chapter should be able to establish, in a compact causal sequence:

1. **Reproducibility:** exact release, inputs, code path, implementation organization.
2. **Local mechanical correctness:** equations, constraints, friction bounds, unilateral contacts all remain satisfied.
3. **Algebraic well-posedness:** the instantaneous 8×8 solve and 2×2 stick-root solve remain well behaved in the physical operating region.
4. **Global energetic correctness:** external work, storage, and modeled dissipation close to numerical precision.
5. **Time-integration convergence:** the trajectory and hybrid events are insensitive to further solver tightening in the selected operating region.
6. **Independent model comparison:** Ballew comparison provides an external model-to-model reference, while retaining the correct interpretation boundary.

That should leave the later Results sections free to focus on physics rather than repeatedly defending the implementation.

---

# 10. Immediate next work

The actuator-dynamics family can be set aside provisionally.

The next coding tasks are:

1. build `mechanical-invariants/`;
2. build `closure-conditioning/`;
3. build `solver-convergence/`;
4. inspect their outputs before drafting manuscript claims;
5. then move into the genuinely new reduced-belt transient-term studies and later targeted hybrid-regime studies.

This file should be treated as the working reference for those three remaining verification implementations.
