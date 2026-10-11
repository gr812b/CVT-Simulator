# Flyweight and clamping mechanisms — CINDER 1.2.0

The common boundary is defined once by `CentrifugalInertiaSample`,
`CentrifugalInertiaMap`, and `CentrifugalInertiaForce` in
`src/cinder/model/cvt/actuation/`. Mechanism providers construct the same
`M_f, M_f_prime, J_f, J_f_prime` payload. The common element owns closing force,
shaft reaction, inspected force terms, and kinetic modes for energy and events.

| Document | Final PDF | Editable source |
| --- | --- | --- |
| General boundary, based on the accepted Revision 4 derivation | [Common boundary](common_boundary/formulation.pdf) | [LaTeX](common_boundary/latex/formulation.tex) |
| Fixed-pivot roller flyweight / weight-and-ramp mechanism | [Fixed-pivot mechanism](fixed_pivot/formulation.pdf) | [LaTeX](fixed_pivot/latex/formulation.tex) |
| Fixed-orientation sliding blocks / CVTech-style mechanism | [Sliding-block mechanism](sliding_block/formulation.pdf) | [LaTeX](sliding_block/latex/formulation.tex) |

The fixed-pivot `reference/` folder preserves the independent reconstruction
and historical v1.1.5 comparison record cited in that document. Its optional
`--repo` comparison deliberately requires the old source. Current behavior is
covered by the package smoke tests, including the ten-second fixed-pivot
launch regression. The sliding-block examples are synthetic, not measured
CVTech dimensions or a validated CVTech product model.

Build all three PDFs with `make` in this folder (TeX Live and `latexmk`). Each
subfolder keeps its final PDF beside its own `latex/` source. Intermediate
files stay in the ignored `.build/` folder. `make clean` removes only those
intermediates. Equations and contents are linked; Previous view uses the PDF
reader's navigation history. Cross-document links expect this folder layout.

## Sliding-block input and use

The public construction types in `cinder.model.cvt.actuation` are
`SlidingBlockProfile`, `SlidingBlockGeometry`, `SlidingBlockMass`,
`SlidingBlockSpec`, `SlidingBlockInertiaMap`, and `SlidingBlockFlyweightForce`.
The corresponding saved component kind is `sliding_block_flyweight`.
[Three complete component records](../../examples/sliding_block/) live in
`cvtModel/examples/sliding_block/`. These component objects can be inserted
in an assembly's `pulleys.primary.components` or `pulleys.secondary.components`.
The host's local travel must be covered, and that pulley must not have a
relative sheave helix.

All input fields use SI: metres, kilograms, dimensionless slopes, curvature
in inverse metres, and centroidal inertia **per mass** in square metres.
Profiles belong to the body datum; the COM offset is separate. The mass is
for the complete identical set. Count only divides loads for per-block
reporting. Cup, rigid-sheave and spring properties stay with the host.

```python
from cinder.model.cvt.actuation import SlidingBlockFlyweightForce

force = SlidingBlockFlyweightForce(spec)  # validated SlidingBlockSpec
maps = force.inertia_map.evaluate(x)
pose = force.inertia_map.pose(x)
reactions = force.inertia_map.reactions(
    x, omega=280.0, alpha=130.0, xdot=0.11, xddot=-8.0
)
print(reactions.lower_normal, reactions.upper_normal)
print(reactions.per_block_guide_moment, reactions.capacity_status)
```

The first guide model must be explicitly `ideal_fixed_orientation`. It
returns full tangential force and centroidal holding-couple demands, including
products of inertia; it does not establish real guide capacity. A nonzero
tangential COM offset is rejected because it introduces mixed kinetic energy.
Changing inserts should update the COM and full tensor as well as mass.

The compiler requires a declared radial branch window and axial interval.
Exact curvature/slope bounds certify the supported gap minimizer and a unique,
regular root within that window. It rejects ambiguous curvature, conformal
contact, mode switches and insufficient finite-track support. End contact is
an explicit idealization. No supporting-solid or 3-D collision guarantee is
implied by this meridional contact check.

A cached C2 motion representation supplies positions, derivatives, contact
locations, and all four inertia quantities. Its reported interpolation errors
are sampled numerical diagnostics, not rigorous continuum error bounds.
There are no geometry root solves in the RHS and no extrapolation outside the
compiled interval. Identical geometry reuses its compilation when mass changes.

Both normal forces are checked at the solved coupled accelerations. At events,
`CVTImpactProjection.mechanism_impulse_margins` reports the required normal
impulses. Direct projection callers must call
`require_admissible_mechanism_impulses()` before accepting a candidate;
`CVTOperatingHybridSystem.transition()` checks the selected reset automatically.
A tensile impulse stops the calculation with its contact named. Flight,
rocking, loss of orientation, and recontact require another model.

## Scope of this release

This PR includes the shared boundary, both mechanism implementations, saved
input/schema/catalog support, the canonical formulation documents, and the
CINDER 1.2.0 package version. The research demo imports core mechanics, and
its JavaScript evaluates exported response coefficients rather than a second
contact law. The existing five example geometries remain available.

The application change is a separate PR: update the backend pin after release,
expose authoritative compile/preview/reaction endpoints, then add the live
geometry editor. Preserve input revision IDs so a stale preview cannot replace
a newer design. Arbitrary CAD import, specified real guides, pressure/strength
limits, friction, and post-liftoff dynamics remain separate extensions.

[Verification and scope record](VERIFICATION.md) lists the checks performed for this PR.
