# CINDER 1.2.0 mechanism verification

This PR incorporates the four-quantity boundary from PR #519 into PR #520 and
adds a constrained sliding-block provider. Verification used Python 3.12.14,
NumPy 2.3.5 and SciPy 1.17.0. The package bump is prepared in the PR; no release
tag or package publication is performed by this work.

## Mechanical and contract checks

The complete smoke and research-demo run passed **229 tests**: 166 core smoke
checks, including 37 new sliding-block checks, plus the 63 existing demo
checks. After the final change to immutable specification access and explicit
upper-stop acceptance checks, all 37 sliding-block checks were rerun and passed.

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
fixed-pivot mechanism (20 pages), and sliding blocks (8 pages). Rendered-page
review checked the full layouts, diagrams, equations and tables. The final
logs contain no unresolved-reference or overfull-box warnings. PDF text and
cross-document targets were also checked. The fixed-pivot historical reference
record is preserved with its own provenance, not relabelled as a new run.

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
| Separate complete formulations with clean sources | Three document folders in root `docs/flyweight_mechanisms/`, each with its PDF beside its `.tex` | Measured CVTech hardware is not supplied |
| Core/version first; application later | Core contracts, catalog and 1.2.0 metadata; demo consumes core | Backend pin, live editor and authoritative preview API are a later PR |

The prose review preserved the accepted general Revision 4 derivation, updated
obsolete implementation/future-work claims, distinguished fixed-pivot and
sliding-block attachments, and kept historical measurements and numerical
comparisons identified as such.
