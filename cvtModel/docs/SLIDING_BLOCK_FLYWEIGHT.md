# Sliding-block flyweight API — CINDER 1.2.1

The common boundary is defined once by `CentrifugalInertiaSample`,
`CentrifugalInertiaMap`, and `CentrifugalInertiaForce`. Mechanisms supply
`M_f, M_f_prime, J_f, J_f_prime` from one compatible motion and mass distribution;
the common element owns force, shaft reaction, energy and event inertia.

The physical derivations live in the repository-root
[formulation folder](../../docs/flyweight_mechanisms/README.md). Each PDF and
LaTeX source is in the same mechanism subfolder. This file documents software,
not measured CVTech dimensions or hardware validation.

## Define contact shapes

A cup is not required to be circular. `SlidingBlockProfile` accepts finite
lines, quadratics, circular graphs, and user-defined **C2 piecewise polynomial
graphs** `z=f(r)`. Supply points in metres for an interpolating cubic:

```python
from cinder.model.cvt.actuation import SlidingBlockProfile

cup = SlidingBlockProfile.from_points([
    (0.020, -0.010), (0.035, -0.006), (0.050, 0.002),
    (0.065, 0.014), (0.080, 0.030),
])
```

`from_points(points, degree=5)` instead constructs a C4 quintic. Too few points
produce a single lower-degree polynomial. Both interpolate the supplied points;
neither silently smooths measured noise. Interpolants can overshoot between
points. Inspect the resulting curve or fit measurements explicitly first.

For exact editor/CAD curve coefficients, construct `kind="spline"`, supplying
`knots` and one `coefficients` row per knot interval. Row `i` contains ascending
powers of **normalized** coordinate `t=(r-knots[i])/(knots[i+1]-knots[i])`.
Values are axial metres; `offset` adds an axial translation. `left` and `right`
must equal the outer knots in Python construction. Seams are checked through
the second derivative. Polynomial degree and physical dimensions have no
sample-template caps. Exact circles remain available without approximating
them as point data.

All four contacts use this same representation: fixed cup (`lower_track`),
translating sheave (`upper_track`), and the two faces in the block's body datum
(`lower_face`, `upper_face`). The faces share a finite radial domain and retain
positive thickness. The complete block footprint must fit the supplied tracks.
Supporting CVT solids and the belt cone are separate geometry; changing their
illustrative backing does not change this contact model or the flyweight mass.

This provider represents meridional graphs and translation with an explicit
`ideal_fixed_orientation` guide. It does not infer the guide from the outline.
Overhangs, independent rocking, friction, compliance and relative sheave-helix
rotation need additional contact/kinematic models. The common force boundary
is broader than this particular provider.

## Contact and branch construction

The minimum gap is searched over the **whole finite face**, including every
polynomial stationary point, seam, endpoint and constant-gap interval. Curvature
may change sign and multiple local minima are allowed. Circular/polynomial
stationarity is reduced to a polynomial, with candidates checked in the original
unsquared equation. No coarse contact grid selects the minimum.

Declare a positive radial branch window and a signed local axial interval.
Bounds on track slopes establish monotone closure and nonsingular translation.
Where track-wide bounds overlap, active-contact enclosures eliminate face
regions which cannot minimize the gap, and the radial interval is subdivided.
Separate reachable-path checks establish isolated regular nonlinear contacts
or retained endpoints; affine tracks also admit fixed multiple minima and flat
contact spans. The compiler does not smooth across an unestablished envelope
transition. Conservative floating-point enclosures can fail to establish a
valid branch; such a failure is reported as numerical, not proof of impossible
hardware.

The compiled C2 body motion supplies both inertia functions and their actual
derivatives. Contact paths use the same cached representation. Position errors
include contact coordinates; derivative errors concern body motion. The report's
three interior checks per final cell are sampled interpolation diagnostics,
not rigorous continuum error bounds. Runtime force, reactions and impulses
perform no contact root solves and never extrapolate beyond declared travel.
Identical geometry reuses compilation when mass changes.

## Flat faces and pressure location

Matching flat faces are supported when the two constraints determine regular
translation. Multiple separated contacts against one affine track are also
supported. They can determine net normals and clamping without determining
where pressure acts.

`pose.lower.u_intervals` and `pose.upper.u_intervals` return the local contact
sets. A pair `(u,u)` is an isolated point; `(a,b)` is an entire contact interval.
`Contact.u` is a geometric representative, **not a predicted pressure centroid**.

For a single contact point per face, `reactions.guide_moment` remains the unique
three-component ideal-guide holding couple. When pressure location leaves a nonzero moment range it is
`None`; `guide_moment_bounds` gives each component's lower/upper demand over all
admissible pressure centroids. `per_block_guide_moment_bounds` divides by count.
The same convention applies to impulses, in N m s. Bounds include the full
centroidal spin demand, including products of inertia. Real guide capacity and
the pressure distribution remain unknown; neither is needed to invent a unique
moment just to return clamping.

## Mass properties belong to the weight

`SlidingBlockMass` accepts total group mass, count, COM offset and full centroidal
inertia **per mass** in local `(radial, tangential, axial)` axes. SI units are kg,
m and m². Count only divides loads for reporting; it never multiplies total mass.
A nonzero tangential COM offset is rejected because it introduces the mixed
kinetic term absent from the four-map boundary. Update COM and tensor when an
insert changes distribution.

Two optional constructors keep uniform-body reduction in CINDER:

```python
from cinder.model.cvt.actuation import SlidingBlockMass

mass = SlidingBlockMass.from_section(
    [(0, 0), (0.030, 0), (0.030, 0.010),
     (0.010, 0.010), (0.010, 0.040), (0, 0.040)],
    width=0.020, total_mass=0.600, count=3,
)
# Alternatively, integrate two smooth mass-body profiles without a display mesh:
# mass = SlidingBlockMass.from_profiles(lower, upper, width=0.020,
#                                      total_mass=0.600, count=3)
```

`from_section` integrates a simple polygon exactly using its area moments,
accepts either winding, and rejects self intersections. `from_profiles` integrates
the smooth material between two profiles with normalized adaptive quadrature.
Both assume uniform extrusion through tangential width; supplied total mass
sets its effective uniform density. These mass outlines need not be identical
to the selected contact faces. For holes, inserts, nonuniform density or a
nonprismatic solid, supply the appropriate measured/computed COM and tensor.
Cup, sheave and spring material remains in the host's separate accounting.

Only one distributed sliding-block group is allowed per pulley. Increase its
total mass rather than appending duplicate groups.

## Construct and inspect

```python
from cinder.model.cvt.actuation import (
    SlidingBlockGeometry, SlidingBlockSpec, SlidingBlockFlyweightForce,
)

geometry = SlidingBlockGeometry(
    cup, ramp, block_lower, block_upper,
    radial_min=branch_left, radial_max=branch_right,
    axial_position_min=open_position, axial_position_max=closed_position,
)
force = SlidingBlockFlyweightForce(SlidingBlockSpec(
    geometry=geometry, mass=mass, guide="ideal_fixed_orientation",
))
sample = force.inertia_map.evaluate(x)
pose = force.inertia_map.pose(x)
loads = force.inertia_map.reactions(
    x, omega=280.0, alpha=130.0, xdot=0.11, xddot=-8.0,
)
print(loads.lower_normal, loads.upper_normal, loads.guide_moment_bounds)
```

The returned closing force is the mechanism's contribution to the movable-sheave
balance. Spring force, belt load and the host's translating inertia remain
separate. The local interval is signed: mounted secondary coordinates may be negative.
Both normal forces are checked at the solved coupled accelerations. At events,
normal impulses required by the candidate reset must also be compressive.
`CVTOperatingHybridSystem` checks selected resets automatically; direct projection
callers must call `require_admissible_mechanism_impulses()`.

Raw normals remain available. Only unresolved near-zero margins are snapped,
using local contact-work residuals and arithmetic roundoff resolution. Resolved
tension is rejected. Flight, rocking and recontact require additional dynamics.

`SlidingBlockGeometryError` provides `code`, `category`, optional
`axial_position`, `radial_interval` and `contact`. For example,
`branch_domain` means no double contact in the declared window at the named
closure; `branch_enclosure`/`contact_regularity` are numerical enclosure failures;
`contact_topology_transition` identifies an unimplemented change in contact-set
cardinality. An application must keep these distinct from invalid dimensions,
actual loss of contact and clearance of separately supplied solids.

## Saved records and compatibility

The component kind remains `sliding_block_flyweight` in assembly schema 1.
Legacy primitive records keep their exact fields and meanings. A new spline
record contains `kind`, `knots`, `coefficients`, and optional `offset`. The public
encoder emits normalized coefficients, not independent fitted force maps.
The schema, decoder, catalog and production force provider all admit the new
representation. [Examples](../examples/sliding_block/) include a noncircular
cup with a matching flat ramp and a nonconvex two-point contact case.

CINDER 1.2.1 changes the core and its canonical documentation. The editable web
demo remains a separate application PR; this release does not update its old
sample-specific controls or claim a general CAD/contact-dynamics engine.
