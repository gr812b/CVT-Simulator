# CINDER 1.2.0 mechanism verification

This PR incorporates the four-quantity boundary from PR #519 into PR #520 and
adds a constrained sliding-block provider. Verification used Python 3.12.14,
NumPy 2.3.5 and SciPy 1.17.0. The package bump is prepared in the PR; no release
tag or package publication is performed by this work.

## Mechanical and contract checks

The latest complete smoke and research-demo run passed **262 tests**: 199 core
smoke checks, including 70 sliding-block checks, plus the 63 existing demo
checks. This includes 33 regression cases added in the October 16 readiness
pass, following the original 229-test integration run.

- Material-point force, shaft torque and kinetic energy: three regular
  geometries, three operating cases, both owning shaft channels (18 boundary
  cases). The Cartesian oracle uses direct positions and differentiated
  inertial trajectories, independently of the inertia-map derivatives and
  force law. Its tolerances account for finite-difference error.
- One consistent motion interpolant: finite-difference derivatives, contact
  gaps at interior positions, no runtime contact-root solve, and no domain
  extrapolation.
- Mass/COM/tensor: total-mass scaling, count invariance, COM changes without
  moving contacts, the product-inertia contribution to the full guide wrench,
  and rejection of mixed kinetic coupling or unphysical tensors.
- Branch policy: insufficient support, ambiguous/conformal branches, mode
  switches, conditioning and explicit endpoint-contact admission.
- Assembly records: all three examples round-trip through public assembly
  encode/decode, validate against the JSON Schema, and report the ideal guide
  assumption in preflight. Existing records retain their meaning.
- Signed travel: changing the axial origin leaves the mechanism's inertia,
  reactions and guide wrench unchanged across all three profile examples,
  including intervals wholly below zero. An actual secondary-mounted group
  round-trips through the schema, passes preflight, and evaluates the coupled
  engaged runtime at three shift positions using the negative local coordinate,
  velocity and acceleration gain. The relative-helix exclusion still applies.
- Zero-load resolution: both contacts' zero-load boundaries are checked with
  positive and negative perturbations. Moving-track tests span three geometries,
  three mass scales, moving/stationary states and interior positions. Three
  positive-mass coupled sheave/spring fixtures admit zero load and reject
  resolved tension. Raw reactions remain available; admissibility combines
  the existing arithmetic roundoff convention with the measured tangency/work
  residual, as derived in the sliding-block formulation.
- One distributed group per pulley: Python construction, public document
  validation and JSON Schema reject duplicate sliding-block groups. Increasing
  the group's total mass retains working inspection/reporting. Profile sign
  validation also matches the saved schema for inactive circle fields.
- Coupled smooth motion: a short free-deadzone transient moves the block while
  conserving primary angular momentum with the mechanism's variable inertia.
- Hybrid events: the actual upper-stop transition accepts the feasible wedge
  fixture and rejects the tensile-impulse counterexample. The latter requires
  `P_fixed = -0.00848528137 N s` when arresting `xdot = +0.1 m/s`. A separate
  transition-hook test ensures the selected reset cannot bypass the guard.
- Existing fixed-pivot behavior: the ten-second launch equivalence test checks
  all states, reports, event times and reset states against the earlier q/I
  laws, through launch, belt engagement and the upper stop.

These are numerical and analytical checks of the stated ideal model, not
experimental validation of CVTech hardware. The contact-branch inequalities
are distinct from the sampled interpolation-error report. Whole-solid
clearance, real guide capacity, pressure, friction and recontact remain outside
the production mechanism represented here.

The regenerated offline demo also passed 780 JavaScript coefficient-response
comparisons against core evaluations, including total-mass scaling; the largest
absolute difference was 1.14e-12. A fresh Chromium screenshot run could not be
completed because the browser download returned a truncated archive. The
existing section tests passed, but this is not a claim of a new browser-layout
review.

## Documents and packaging

The canonical documents compile with `latexmk`: common boundary (19 pages),
fixed-pivot mechanism (20 pages), and sliding blocks (9 pages). Rendered-page
review checked the full layouts, diagrams, equations and tables. The final
logs contain no unresolved-reference or overfull-box warnings. PDF text and
cross-document targets were also checked. The fixed-pivot historical reference
record is preserved with its own provenance, not relabelled as a new run.

The October 16 sliding-block update adds signed-coordinate and single-group
rules plus the numerical-resolution derivation. It was rebuilt
beside its LaTeX source and all nine rendered pages were checked. The final
build has no unresolved-reference or overfull-box warnings. The common and
fixed-pivot PDFs were not changed by this readiness pass.

Black and flake8 pass on `src` and `test/smoke`; `git diff --check` passes.
The 1.2.0 wheel and source distribution build successfully. After the layout
correction, physical formulations and historical reference sources live in
root `docs/flyweight_mechanisms/`, outside the package. The source bundle retains
software/API docs and example records. Production dependencies remain NumPy and SciPy;
`jsonschema` is added only to the development extras for contract tests.

## Brief review record

| Requirement | Evidence in this PR | Remaining gap |
| --- | --- | --- |
| One canonical mechanical boundary | Both providers use `CentrifugalInertiaForce` for force, torque and kinetic modes | Mixed kinetic terms need a richer boundary |
| Arbitrary mass distribution within the admitted motion | Datum/COM separation and full centroidal tensor; total-set convention | Imported mass properties must match real parts |
| Block torque and contact feasibility | Full guide wrench; two solved force margins; retained-contact impulse checks | Ideal guide capacity and post-release dynamics are unknown |
| Signed host coordinates and zero contact load | Actual mounted-secondary runtime checks; cancellation/tangency residual policy with tensile counterexamples | Numerical checks do not establish hardware limits |
| Separate complete formulations with clean sources | Three document folders in root `docs/flyweight_mechanisms/`, each with its PDF beside its `.tex` | Measured CVTech hardware is not supplied |
| Core/version first; application later | Core contracts, catalog and 1.2.0 metadata; demo consumes core | Backend pin, live editor and authoritative preview API are a later PR |

The prose review preserved the accepted general Revision 4 derivation, updated
obsolete implementation/future-work claims, distinguished fixed-pivot and
sliding-block attachments, and kept historical measurements and numerical
comparisons identified as such.
