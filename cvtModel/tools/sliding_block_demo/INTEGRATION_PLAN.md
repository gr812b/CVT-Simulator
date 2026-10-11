# Sliding block physical review and integration plan

**Historical review and plan.** The core implementation and 1.2.0 version bump
are now included in this PR. See the [canonical formulation index](../../docs/flyweight_mechanisms/README.md)
for implemented scope and [release verification](../../docs/flyweight_mechanisms/VERIFICATION.md)
for current checks. The application editor remains a separate PR. Statements
below describing missing production features record the review baseline.

Review date: 2026-10-11. Demo baseline: PR #520, `5262dede609c86dce81938f13ce82a6bd8fbda0b`.
Boundary baseline: PR #519, `e80ade45ead41e5b8127f04b4a59f281939c6df7`.
Both PRs were open when checked. The package and application pin were 1.1.5.

The smooth-motion inertia reduction agrees with independent material-point
balances. It is suitable for a constrained-mechanism provider. Production use
also needs an explicit guide assumption, reliable branch limits, and checks of
the reactions required by motion and impacts. A positive normal-force result
alone does not establish those other conditions.

This document proposes the input model and two implementation stages. It does
not release a new CINDER version or implement the application editor. The
existing mechanics, total-mass convention, five examples, and sectional viewer
remain the reference. No measured CVTech hardware is claimed.

## Physical checks and findings

These are new physical oracles, not a second reviewer. The material-point check
reuses solved positions, but independently differentiates Cartesian particle
trajectories in an inertial frame. It does not reuse contact normals, motion
derivatives, inertia maps, or the force formula to construct its expected loads.
Eight equal material masses reproduce the specified COM and shaft-axis second
moment, with zero products of inertia. Their linear accelerations determine
generalized force through virtual work and shaft torque through moment balance.
Their velocities determine kinetic energy directly.

| Check | Result and interpretation |
| --- | --- |
| Three regular shapes at forward, reverse, and zero rotation, with nonzero shift speed and acceleration | Nine cases agree in force, torque and energy. Largest absolute differences were 9.95e-5 N, 5.95e-8 N m, and 4.09e-6 J with a five-point 1e-4 s stencil. This checks smooth dynamics, not global geometry certification. |
| Straight wedge hand free body | At x=7.5 mm and omega=350 rad/s, r=57 mm and total axial force=2094.75 N. Normal-force moments require a nonzero holding couple. |
| Same COM, mass and shaft inertia, opposite radial-axial mass correlation | The four inertia functions and rotational energy are identical, but required transverse inertial moments differ. A gyration radius cannot determine the complete guide wrench. |
| COM displaced 2 mm circumferentially from a radial guide plane | With M=0.75 kg and r'=0.4, unit shift speed carries -0.0006 kg m of shaft angular-momentum coefficient B. Fixed orientation alone does not imply B=0. The current centered model satisfies B=0. |
| Sudden stop of the straight example | At x=x_max, stop xdot from +0.1 m/s to zero without a shaft-speed jump. Retaining both contacts would require impulses (-0.0084853, +0.0432666) N s. The first contact would have to pull. The pre-stop operating point is admissible, but this imposed reset cannot retain its two-contact branch. |
| Non-finite data | Before this review, NaN mass, gyration radius or operating values could return PASS. Finite-value validation now rejects those inputs. Count must be a positive integer. |

`test_physical_checks.py` preserves these checks, including the counterexamples.
Passing a counterexample test means the limitation is reproducible, not that the
prototype has acquired the missing guide or impact model. Existing mass/count,
Messick-limit, derivative, energy, liftoff, singularity and drawing tests remain.

The complete demo suite passed **63 tests**, including all 28 previous checks.
A separate temporary adapter probe mounted each regular geometry on PR #519's
actual `CentrifugalInertiaForce`: all nine operating cases also agreed with the
Cartesian oracle, including a nontrivial bias and scale in the host's local
acceleration relation. This verifies the boundary handoff, not a full coupled
sliding-block CVT simulation. No adapter was installed in production.

## Why the block can need torque

Fixed orientation is a constraint relative to the rotating pulley. The block
still rotates in space at the shaft angular velocity. For one block, in a frame
fixed to its body, the required centroidal moment is

    sum((contact_position - COM) cross contact_force) + guide_moment
        = I_C alpha_vector + omega_vector cross (I_C omega_vector).

The second term can be nonzero even at constant shaft speed if the shaft is not
a principal inertia direction. In local (radial, tangential, axial) coordinates,
the tangential component includes I_rz * omega^2. Centroidal spin also needs
I_zz * alpha about the shaft. Neither is established by setting the relative
block angle to a constant.

The current demo reports the opposite of the two contact moments in its 2-D
(r,z) plane. That is the contact-only holding demand; it assumes zero inertial
rocking moment. Its sign is opposite the physical positive tangential-axis
convention. The following are magnitudes at x=7.5 mm, omega=350 rad/s
(3342.25 RPM), zero shift speed/acceleration, and total mass 0.75 kg:

| Example | Sum of like local moment demands | Demand per block for n=3 |
| --- | ---: | ---: |
| Straight ramps | 51.06 N m | 17.02 N m |
| Circular cup | 41.31 N m | 13.77 N m |
| Both curved | 63.88 N m | 21.29 N m |

The middle column is not a resultant shaft torque or a global vector sum. Even
if symmetrically distributed blocks have cancelling global transverse moments,
each pocket must carry its own local load. An ideal force couple resisting
17.02 N m across 20 mm requires opposite forces of about 851 N, before any other
loads. This is a scale illustration, not a guide design or capacity rating.

Circumferential sidewall normals can resist tangential force and moments about
other axes, but cannot alone resist a moment about the tangential axis. The
anti-rocking feature must actually constrain that rotation. Finite contact
patches may also shift their pressure resultants to carry a moment. The current
point-contact model does not recover that pressure distribution, particularly
for conformal contacts.

Two supported guide descriptions should be distinguished:

- **Ideal prescribed orientation:** an explicit unlimited, frictionless guide
  assumption. Compute the demanded wrench; report physical capacity as unknown.
- **Specified guide contacts:** positions, normals, clearances and optional
  independently supplied capacities. Solve the full force/moment feasibility
  problem with compressive contact reactions. Guide forces may also have radial
  and axial components, so the old two-normal solution is not automatically the
  answer once a real guide is introduced.

The guide need not introduce a new state if it can enforce the stated motion.
If it permits rocking or loses support, the one-coordinate map no longer
describes that motion. Contact loss then needs additional dynamics or a clear
termination; it must not be hidden by clipping a reaction to zero.

## Inputs for user supplied shapes

Use a body datum independent of the COM. Changing an insert can move the COM
without changing the contacting outline. The current prototype's faces are
COM-relative, so this separation is an intentional production-schema change.

| Object | Geometry and attachment | Mass or mechanical data |
| --- | --- | --- |
| Representative flyweight | Closed meridional outline; named active contact edges; extrusion width or declared 3-D reduction; fixed orientation and guide datum | Total set mass M, block count n, COM relative to datum, and full centroidal inertia tensor or equivalent mass model |
| Cup | Finite solid and named contact profile; axially fixed to the shaft frame | Clearances and optional guide/contact properties |
| Movable sheave | One rigid solid translated by x; belt cone and rear actuator ramp are separate named faces | Its own mass/inertia remain in the host sheave accounting |
| Guides | Attachment body, contact positions/normals, constrained directions and clearance, or an explicit ideal constraint | Optional force/pressure/couple limits with their source |
| Assembly | Relative placements, shaft axis, travel stops, selected initial branch | Springs remain separate force elements; belt geometry remains the CVT host's responsibility |

For identical weights, m_one=M/n. Count never multiplies an already-total force
or inertia. Count does matter for per-pocket capacity and circumferential
clearance. A UI may store a per-unit-mass centroidal tensor and multiply by M,
or derive per-block tensors from uniform/composite extrusions. Whichever schema
is chosen, units and whether a tensor is per-block or total must be explicit.
CAD mass properties can be supplied instead; an outline alone cannot specify
the mass distribution of a plastic body with metal inserts.

Start with editable lines, circular arcs and supported smooth curve segments,
plus JSON import/export. A later point-table or CAD-section importer should
produce the same documented geometry representation. Current profiles are
single-valued graphs z=f(r); they cannot represent arbitrary overhangs, closed
loops or saddle contacts. General parametric profiles require a contact solver
that can enumerate candidates, enforce outward normals and select a continuous
branch. Do not label the current 25-sample gap search as an arbitrary-shape
guarantee.

For a homogeneous extrusion, mass properties can be computed from its outline
and width. For an insert change, recompute the COM and tensor as well as mass.
A tangential COM offset can create B!=0 even without relative block rotation.
The first provider must reject such a case or require a demonstrated complete-
assembly cancellation; the four-quantity boundary cannot silently absorb B.

## Limits and preview behavior

The preview should use the same compiled geometry and contact solution as the
simulation. Fixed means axially fixed in the rotating shaft frame. The sheave
and its rear track move rigidly together; the cup does not translate.

| Layer | Checks | Result shown to the user |
| --- | --- | --- |
| Input | Finite values, units, valid outlines, positive thickness, ordered intervals, valid tensor and count | Field-specific error before compilation |
| Configuration branch | Both active contacts, whole-solid clearance, no extrapolation, scaled Jacobian conditioning, competing roots, and contact-mode changes | Supported interval(s), branch identity, and first failure location |
| Smoothness | Consistent derivatives; enough regularity for finite M, M', J, J'; explicit treatment of corner/edge switches | Separate branches or a rejected interval, not an invented blend |
| Instantaneous operation | Both normal reactions and the complete guide wrench at the solved acceleration | Contact loss, guide demand and verified/unknown capacity separately |
| Impacts | Required normal/guide impulses and compatibility with retained constraints | Accepted reset or a named unsupported topology change |
| Hardware envelope | Supplied speed, strength, pressure, clearance and spring-travel limits | Which stated limit is exceeded; unknown if no evidence exists |

Geometry can define a travel interval; it cannot by itself define a universal
safe RPM or acceleration limit. At one x, changing speed or acceleration can
change whether contacts remain closed. A nonsingular local Jacobian does not
prove global uniqueness. Adaptive subdivision/root isolation is needed around
suspected transitions; a fixed collection of green samples is insufficient.

Keep the existing section and one main closure slider. Add a component selector
and precise dimension/profile controls. Geometry edits request a new compiled
preview; mass-only edits can reuse contact kinematics when the shape is unchanged.
Use revision IDs so a slow older request cannot replace a newer preview. While
compilation is pending, identify the picture as stale; if it fails, highlight the
offending part and limit instead of displaying the old pose as a successful new
design. Sweep the chosen branch and mark its unsupported region on the slider.

Store the physical input and branch choice, not just an image or four fitted
force curves. Derive inertia and derivatives from one consistent motion
representation. Save optional compiled caches with a geometry/schema version
and content hash. The backend remains authoritative; JavaScript should not
maintain a second contact-physics implementation.

The prototype's automatically relieved supporting solids are useful synthetic
examples. A user-supplied solid must not be trimmed or moved automatically to
make it pass: return the collision and let the user change the design.

## Proposed CINDER change

First build on [PR #519](https://github.com/gr812b/CVT-Simulator/pull/519), which
already defines `CentrifugalInertiaSample`, `CentrifugalInertiaMap` and
`CentrifugalInertiaForce`. Do not duplicate that boundary in this demo. Its
common element supplies both the closing force and shaft reaction, and its
kinetic modes supply energy and event inertia.

The production PR should add the following within `cvtModel/`:

1. A validated sliding-block specification and deterministic branch compiler in
   `src/cinder/model/cvt/actuation/`, with an interval-aware inertia provider.
   Compile geometry outside RHS/closure iteration. Keep diagnostics available
   separately from the lightweight map sample. Derive all four quantities from
   the same motion, COM and mass properties.
2. A sliding-block element using `CentrifugalInertiaForce` for common dynamics,
   and its own contact/guide policy. Resolve reactions with the actual solved
   local acceleration and shaft acceleration. The existing single contact-
   margin hook can return min(N_fixed,N_moving), with both named values retained
   for inspection. Do not replace these by the sign of net closing force.
3. A reset-admissibility path for unilateral mechanism contacts. Event inertia
   alone is insufficient. If the imposed reset needs tensile impulse, terminate
   with that cause or implement the corresponding new topology. The first
   release need not invent flight, rocking or recontact dynamics.
4. Saved-document encode/decode, schema and catalog entries, public exports,
   preflight validation, inspectable fields, and round-trip fixtures. Preserve
   the current fixed-pivot and centrifugal-ramp documents. Additive schema
   support must not silently reinterpret existing records.
5. Mass ownership checks: weights appear once in M_f and J_f; sheave masses,
   bearings, cup and springs retain their separate ownership. Preserve the
   local-to-shared acceleration relation, including its curvature bias, when
   mounting the mechanism on either pulley.
6. Promote the physical oracles into core tests, add coupled smooth-transient
   and valid/invalid stop cases, and retain the existing baseline launch/event
   regression. A test of a rejected contact topology is part of acceptance,
   not a reason to force that scenario to complete.

Proposed release: **CINDER 1.2.0**, subject to checking the release head before
implementation. This is a new public mechanism feature after 1.1.5; it is not
the separate CINDER V2 continuum-belt project. Update package version and source
links together, run the package gates, then tag/publish through the established
release workflow. This review does not bump, tag or publish anything.

## Separate application PR

After the CINDER version is available, make a separate application PR that pins
that version in `backend/requirements.txt`, exposes the new specification and
preview/inspection service, and adds the frontend editor and selector. Extend
the existing `backend/app/api/v1/primary_design.py` and frontend primary-design
flow where practical. Both simulation and preview must call the released CINDER
implementation. Keep existing designs and existing editor defaults unchanged.

Acceptance includes all five research samples, edited shape/mass round trips,
invalid geometry, liftoff, ideal-versus-specified guide status, out-of-domain
travel, stale-request behavior, and a usable sectional preview on desktop and
narrow screens. A later CAD importer can target the same schema without changing
the transient boundary.

## Review record

| Requirement | Evidence | Remaining gap |
| --- | --- | --- |
| Total mass, arbitrary identical count | Existing scaling/count tests retained; count validated | Per-pocket capacity and placement require real count/guide geometry |
| Preserve five geometries and physical cross-section | No scenario or solid geometry edits in this review | Continuous and 3-D collision guarantees are outside current checks |
| Verify force and shaft coupling together | Cartesian particle force, torque and energy checks | Actual hardware measurements remain separate |
| Explain torque on the block | Hand moment balance and tensor counterexample | Full tensor and physical guide feasibility are planned |
| Keep integration mechanically honest | Explicit negative stop-impulse fixture | Production event hook and response policy still to implement |
| CINDER before frontend | Existing #519 reused; core and app changes separated | Version bump and both implementation stages remain future work |

References: the supplied CINDER formulation, Sections 3.2, 3.3 and 3.6; the
2026-10-09 general centrifugal-mechanism v4 note (assumptions, boundary and event
qualification); Messick (2018), Section 9.4.1, thesis page 109 / PDF page 118
(straight-ramp centrifugal-force limit). General Newton-Euler moment and ideal
constraint-work principles are also described in MIT OpenCourseWare's
[rigid-body dynamics notes](https://ocw.mit.edu/courses/8-09-classical-mechanics-iii-fall-2014/6fe39e8d5ce4ce746ca256dfea665eda_MIT8_09F14_Chapter_2.pdf)
and [Lagrange equations notes](https://www.ocw.mit.edu/courses/16-61-aerospace-dynamics-spring-2003/e16936ad266f184f38159855f69fc227_lecture9.pdf).
