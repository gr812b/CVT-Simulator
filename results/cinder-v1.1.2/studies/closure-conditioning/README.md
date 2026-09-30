# Current publication revision

Use the common-solve/sticking contour figures and commands in
[the 25 September provenance note](provenance/CONTOUR_REVISION_2026_09_25.md).
`run.py --plot-only` requires both the recovered `reviewed/` evidence and its
new `contour_audit/` record, all included in the delivery. `--audit-contours`
repeats only the new focused contact check; it never reruns a trajectory.
The earlier study protocol and original import instructions follow.

# Closure conditioning — Results 4.2.4

## Final publication reproduction

Use the release-local environment with **installed `cinder-cvt==1.1.2`**, source
tag commit `7637a38b4fb9ec21dfb953c1c80a27ec5f389654`. The newer live simulator
must not enter this study. Commands below run from `results/cinder-v1.1.2`:

```bash
.venv/bin/python verify_environment.py
.venv/bin/python studies/closure-conditioning/verify_study.py
.venv/bin/python studies/closure-conditioning/run.py --plot-only \
  --artifacts-dir studies/closure-conditioning/artifacts/reviewed \
  --figure-dir studies/closure-conditioning/artifacts/reviewed/publication
.venv/bin/python studies/closure-conditioning/tests/test_publication.py
```

Place the delivered `reviewed/` directory at the indicated artifact path first.
`--plot-only` verifies registered input/output hashes, all retained map masks,
both censuses, root derivatives and selected fresh checks before plotting. It
performs no simulation. It emits two vector PDFs, two 300 dpi PNGs, checked
values and a figure provenance record. The manuscript uses the two PDFs at
6.5-inch width. The code is `analysis/publication_plots.py`, connected to this
canonical runner; no exploration script is required.

To recover the evidence from the exact original archives and repeat only the
selected frozen calculations:

```bash
.venv/bin/python studies/closure-conditioning/run.py --import-retained \
  '/path/artifacts(20260912-044618).zip' \
  '/path/best-visual-multiroot-story(1).zip' \
  '/path/one-contact-multiroot-fold-search.zip' \
  --artifacts-dir studies/closure-conditioning/artifacts/reviewed \
  --figure-dir studies/closure-conditioning/artifacts/reviewed/publication
```

Archive identities are registered in `provenance/retained_archives.json`.
The first archive supplies the **735-start full census and 241/321/501 maps**.
The older `artifacts(10).zip` supplies only the superseded recap (375 starts,
81/101/121 maps); it must not be substituted. The import retains original
member bytes, uses the embedded historical case library, and records exact
executed input snapshots. It re-evaluates selected roots, finite differences,
an open local curve and a focused residual grid. It does **not** repeat the
launch, full maps, broad search or multistart sweeps.

The original maps' one-sided helix contact masks are preserved and identified
as historical. The publication's matrix maxima are unmasked. Selected two- and
one-contact roots also pass the current bilateral reference, with identical
mechanical responses. Read `provenance/SECTION_4_2_4.md` for exact values,
case/hash reconciliation, limits and the distinction between a numerical
acceptance flag and complete contact admissibility.

The default runner and `--quick` remain available for new full/quick core
experiments. They now write to `artifacts/full_recomputed` and `artifacts/quick`
and refuse to erase existing output directories. These are new executions with
the current release-scoped defaults; they are not substitutions for the
registered historical evidence and do not automatically reconstruct the
targeted fold archives.

## Core study and retained diagnostics

This study asks two distinct questions:

1. for a specified traction pair \((\lambda_p,\lambda_s)\), is the production **8×8 mechanical closure** full-rank and well conditioned?
2. in stick–stick, is the **2×2 traction-root map** locally identifiable and effectively unique?

The study now separates **mechanical-state coverage** from **lambda-plane depth**.

## Mechanical-state coverage

The frozen Baja launch still contributes physically encountered low-ratio-seat, mid-shift, late-shift, and upper-stop states. It is no longer the whole scenario set.

Additional engaged stick states are searched from the shared release library:

`../../defaults/verification/operating_cases.json`

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

- the static box, for a finite physical-root census;
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

## Optional singular-vector ridge diagnostic

After a normal closure-conditioning run has produced the expanded `.npz` maps,
`analysis/singular_vector_diagnostics.py` can interrogate the weak direction of the
8×8 closure without repeating any lambda-plane sweep:

```powershell
python .\studies\closure-conditioning\analysis/singular_vector_diagnostics.py
```

By default it analyzes `upper_stop` and `mid_shift`.  For each state it compares
the actual root with the expanded-domain maximum of scaled `kappa(A)`, the
worst topology-admissible expanded point, and the nearest point on the top
0.5% high-conditioning ridge.  It writes the weakest right singular vector,
the matching left singular vector, and a focused `(tau_s,N_s)` row-alignment
diagnostic under `artifacts/full_recomputed/singular_vector_diagnostics/`.

The singular vectors are taken from the same row/column-equilibrated matrix
used by the study's scaled closure condition number.  Therefore the vector
components show the weak *equilibrated* direction rather than being dominated
by the incompatible physical units of angular acceleration, torque, and force.
The back-scaled physical direction is saved for sign/response interpretation,
but its raw component magnitudes must not be compared across different units.
