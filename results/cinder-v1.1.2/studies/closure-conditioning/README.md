# Closure conditioning — operating-domain upgrade

This study asks two distinct questions:

1. for a specified traction pair \((\lambda_p,\lambda_s)\), is the production **8×8 mechanical closure** full-rank and well conditioned?
2. in stick–stick, is the **2×2 traction-root map** locally identifiable and effectively unique?

The study now separates **mechanical-state coverage** from **lambda-plane depth**.

## Mechanical-state coverage

The frozen Baja launch still contributes physically encountered low-ratio-seat, mid-shift, late-shift, and upper-stop states. It is no longer the whole scenario set.

Additional engaged stick states are searched from the shared release library:

`../../defaults/verification_operating_cases.json`

That library was extracted from the latest mechanical-invariants case design on PR #487. The closure study uses forward/reverse stick states, positive free-shift velocity, negative free-shift velocity/backshift, low/high interior ratio, and a stressed fixed-boundary state when those states are accepted by CINDER's production classifier and mechanical admissibility checks.

Deadzone cases are intentionally excluded: the engaged 2×2 stick-root map does not exist there.

## Lambda domains

Three map scales are retained:

- **physical / static Coulomb-capacity box** — 241×241 by default;
- **expanded mathematical continuation** — normally \([-2.6,2.6]^2\), 321×321;
- **broad structural diagnostic** — \([-10,10]^2\), 501×501, generated only for the configured showcase state.

The old label “physical domain” was too strong. Being inside \(|\lambda_j|\le\mu_s\) does not guarantee the trial mechanics are physically admissible.

## Admissibility overlays

Every trial point is still solved and retained in the NPZ. The study independently classifies whether that trial also satisfies the retained topology:

- \(N_p,N_s\ge0\);
- complete reduced belt tension remains nonnegative;
- distributed wrap normal loading remains nonnegative;
- mounted unilateral mechanism contacts remain compressive;
- an active low-ratio/upper support does not need to pull.

For every mapped state the study emits:

- an **unmasked** 8-panel conditioning map;
- a **topology-masked** version of the same map;
- a separate **inadmissibility map** showing the reason a point was rejected;
- raw NPZ arrays containing both visible and hidden points.

Expanded/broad maps also draw the true static Coulomb-capacity box as a dotted rectangle.

## Why the finite-lambda “walls” matter

The wrap trial factors use the regular functions

\[
\Phi_-(z)=\frac{1-e^{-z}}{z},\qquad
\Psi_-(z)=\frac{z-1+e^{-z}}{z^2},
\]

with continuous limits at \(z=0\). For finite real \(z\), \(\Phi_-(z)\) does not cross zero. Therefore a sharp wall around a finite value such as \(\lambda_p\approx -1\) is **not automatically a pole in the individual wrap law**.

Only the final three rows of the production 8×8 system change with lambda: the primary traction row, secondary traction row, and closed tension-loop row. Sharp finite-lambda residual walls occur when those lambda-dependent rows combine with the five frozen mechanical rows so that the assembled 8×8 matrix approaches singularity. The study now stores the smallest singular value and determinant of the **same equilibrated 8×8 matrix CINDER solves**, allowing these walls to be identified directly rather than inferred from the residual colors alone.

The primary and secondary lambda dependences enter separately before being coupled by the tension-loop equation. Consequently near-singular loci often look nearly vertical or horizontal over part of the map, then bend as the two pulley contributions become strongly coupled.

## Zero contours and root choice

A zero of \(R_p\) alone is only a one-dimensional family of traction pairs compatible with primary sticking. Likewise \(R_s=0\) is the secondary family. A stick–stick candidate must satisfy both simultaneously:

\[
R_p=0,\qquad R_s=0.
\]

The baseline physical root is the simultaneous intersection that is also statically admissible and mechanically/topologically admissible. Expanded maps may contain additional mathematical branches or apparent intersections outside that region. The study therefore performs two different multi-start tests:

- the physical static box, for the production physical-root uniqueness claim;
- the expanded mathematical box, to catalogue additional mathematical root clusters without confusing them with physical solutions.


## Definition of the stick-root Jacobian

The conditioning quantity reported as `J_R` is the derivative of the **frozen physical residual map**

`[R_p, R_s]` with respect to `[lambda_p, lambda_s]`

at the reported root. The study reconstructs it directly with a symmetric central difference and verifies the result over a decade-spanning step sweep (`root_jacobian_step_sweep.csv`, summarized by `root_jacobian_convergence_summary.csv`).

Do not use `EngagedContactSolveResult.jacobian` as the canonical conditioning metric. In CINDER 1.1.2 that field is solver working state: a fresh least-squares solve stores the optimizer's terminal finite-difference Jacobian, while an accepted continuation step can store a Broyden-updated Jacobian carried from the preceding state. It is intentionally useful for continuation, but can depend on solver history and therefore is not a unique property of one frozen CVT state.

## Outputs worth inspecting

- `actual_root_state_scan.csv` — conditioning at every mechanically distinct accepted state;
- `mapped_state_selection.csv` — which states received expensive 2-D maps;
- `states/<case>/physical_conditioning_map.png`;
- `states/<case>/expanded_conditioning_map.png`;
- corresponding `_topology_masked` maps;
- `states/<case>/expanded_inadmissibility_map.png`;
- `states/<case>/expanded_feature_overlay.png` — 8×8 conditioning ridge + both zero contours + admissibility;
- `states/mid_shift/broad_conditioning_map.png` — the one high-resolution \([-10,10]^2\) showcase;
- `closure_singularity_ridge_candidates.csv`;
- `expanded_multistart_summary.csv`.

Run from `results/cinder-v1.1.2`:

```powershell
python .\studies\closure-conditioning\verify_study.py
python .\studies\closure-conditioning\run.py
```

A much cheaper structural preview is available with `--quick`.


## Shared-case ownership

Mechanical invariants consumes that same defaults file directly; closure conditioning
does not maintain a private duplicate of the fixed-boundary case/search ranges. The
shared file owns the scenario vocabulary, while this study owns lambda-domain
resolution, conditioning diagnostics, root-census logic, and map selection.
