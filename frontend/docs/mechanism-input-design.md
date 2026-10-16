# Mechanism input design

Status: design proposal with a first implementation in the sliding-block demo,
using the published CINDER 1.2.0 geometry study. The demo now has selectable
section features, eight dimension inputs, linked ramp/block angles, live
preview requests, undo/redo, input revision guards, body mass derivation and
hardware interference feedback. General sketching, measured/CAD import,
physical-library saving and simulation use remain proposed follow-up work.

## Recommendation

Start with a **dimensioned axial section and a live assembly preview**, using
named mechanism templates. A user selects the cup, block, ramp or guide in the
section; the adjacent form shows dimensions for that selection. The section is
the editing surface; the 3D view explains the assembled result and motion.
Use numeric inputs as the precise controls, with drag handles as an optional
shortcut. Both update the same draft.

Grow this into a small constrained profile editor, then add measured-profile
and CAD import as alternative ways to populate the same definition. Do not
require a CAD file or a complete unconstrained sketch for the first useful
workflow. Do not advertise arbitrary contact shapes until CINDER can compile
their actual contact branches.

## Alternatives considered

| Approach | Strongest use | Main difficulty | Decision |
| --- | --- | --- | --- |
| Named templates with physical dimensions | Building a known cup/block or pivot/roller mechanism from measurements | Cannot describe every manufactured detail | First release; keep fields tied to visible dimensions |
| Constrained section sketch | Custom contact geometry, with parallel/tangent/radius relationships | Ambiguous sketches, excess constraints and contact-mode changes need useful diagnostics | Add supported primitives and a few explicit relationships next |
| Tables of measured points or a calibrated drawing | Reverse engineering without native CAD | Measurement noise and uncertain tangents/curvature can substantially change motion derivatives | Add fitting with residuals and uncertainty; never run raw point interpolation silently |
| DXF section import | Existing 2D engineering outlines | Units, origin, edge selection and unsupported curves still need interpretation | Good advanced entry route after the section editor exists |
| STEP solid import | Real block bodies with pockets, inserts and mass properties | Coordinate systems, selected contact faces, materials and reduction to a supported mechanism are still necessary | Later; preserve native geometry separately from its solver representation |
| Freehand outline or mesh upload alone | Quick visual context | An attractive solid does not identify contacts, mounting, mass distribution or a valid motion branch | Allow as reference material, not as an automatic mechanical definition |

This is a staged recommendation, not a claim that templates cover arbitrary
hardware. CAD import is valuable, but does not remove the need to tell the
application which surfaces contact and how the weight is guided.

## What the user would enter first

Use one mechanism selector for each pulley: fixed-pivot/roller or sliding
block. Show mechanism-specific measurements beneath a common preview shell.
Keep the two mechanisms' physical parameterizations distinct. A second copy of
the same distributed sliding-block group is not an option.

For the first sliding-block template:

| Selection | Primary controls | Important relationship |
| --- | --- | --- |
| Assembly | Shaft datum, open-state reference, available sheave stroke | Draw the positive local closure direction; secondary coordinates may be negative |
| Reaction cup | Contact arc radius, arc position, radial extent | Circular contact profile and visible backing meet at the same edge |
| Block | Radial extent, rounded cup-face radius/position, thickness at a named datum, tangential width | Positive thickness throughout; the drawn weight is the mass-bearing body |
| Movable ramp | Angle, position at the open datum, radial extent | Block face can be linked parallel to it; the link is stored explicitly |
| Mass | Uniform material/density or measured mass; distribution source | Count and per-block mass produce one total-set mass |
| Guide | Explicit fixed-orientation ideal guide assumption | Show calculated demands separately from any declared hardware capacity |
| Hardware appearance | Cup backing thickness, sleeve and sheave envelope | These belong to the CVT, not to the flyweight mass calculation |

Angle labels must include a small diagram and reference axis. For example,
measure the signed ramp angle from the radial direction in the r,z section;
convert to the solver's dimensionless dz/dr once. The belt-facing cone angle
is a separate property. It is not automatically the block/ramp angle.

The section has equal physical axis scales while editing so an angle is
visually meaningful. The editable demo section now uses equal scales, with
dimension guides for the focused field, including an explicit radial reference
for the ramp angle.

Use a shared angle when a user selects “block face parallel to ramp.” Do not
store two independently editable angle values and hope they stay equal. The
same principle applies to a tangency constraint. Provide an explicit unlink
action for genuinely independent geometry.

Changing a dimension highlights the affected edge and dimension annotation.
Keep the camera and selected stroke position stable during edits. On a small
screen, the selected feature's controls open below the section. Every handle
has an equivalent keyboard-accessible quantity input and undo operation.

## Representation and ownership

Store three related things, with different responsibilities:

1. **Authoring definition:** named features, dimensions, constraints, material
   regions, references, source units, provenance and authoring schema version.
   Preserve these so a saved mechanism reopens as an editable design.
2. **Resolved mechanical definition:** the existing CINDER component payload,
   in SI, including finite contact profiles, selected branch, mass, COM, full
   centroidal tensor and explicit guide. CINDER remains the authority for its
   admissibility, motion derivatives, four maps, reactions and impulses.
3. **Display description:** tessellated weight and CVT hardware with feature
   IDs and attachment frames. It is generated from the definition; it is not a
   second source of mechanical parameters. Imported reference meshes remain
   visibly distinguished from geometry used by the solver.

Keep authoring/display metadata in application-owned storage alongside the
CVT revision, outside the strict CINDER assembly JSON. Do not put arbitrary
editor fields into the simulation schema. Freeze the resolved mechanical
payload with a submitted run, preserving its CINDER version and source
revision. A later edit must not change the input of an existing run.

Cup backing is attached to the shaft frame; ramp and movable backing are
attached to the translating sheave frame; the weight follows the mechanism's
body datum. All views consume the same resolved profiles and preview frames.
Selecting an edge in either view selects its authoring feature.

The current `CvtEditor` renders numeric metadata fields. It does not provide a
complete editor for the sliding component's nested profile and tensor objects.
Add a dedicated mechanism editor there rather than exposing raw JSON or
flattening every profile coefficient into the ordinary hardware form. Reuse
`QuantityInput`, unit preferences, invalid draft handling, document-path
findings, revision history and the existing physical-library save flow.

## Weight shape and mass cannot drift apart

For a uniform extruded section, derive volume, COM and the full tensor from
the smooth section and tangential width, independently of mesh resolution.
Choose either material density or measured mass as the mass source. With a
measured mass and a uniform distribution assumption, rescale density; retain
the shape's COM and inertia per mass. Label that assumption.

For pockets, embedded inserts or variable width, require a supported
multi-region body model or imported/measured mass properties. A single
“weight” number cannot capture a relocated insert. Offer an advanced mass
properties input with the datum, axis order and units visibly specified.
Transform an imported tensor into the local radial/tangential/axial frame and
shift it to the COM before normalizing by mass. Check symmetry, nonnegative
principal moments and the inertia triangle inequalities.
Convert inertia units explicitly (for example, kg·cm² to kg·m²) and reconcile
the source's product-of-inertia sign convention. Do not confuse a CAD tensor
about world axes with a centroidal tensor already expressed in local axes.

For an identical distributed set, accept per-block mass and count in the UI
but resolve exactly one `total_mass`; count never multiplies an already-total
mass in the force calculation. If total mass is the selected source instead,
count changes the per-block readout, not total mass. Changing distribution
must update COM and tensor, not just mass. Nonidentical groups require a new
model, not duplicate copies of the same component.

Extra drawn cup/sheave material must never enlarge the weight's mass. It also
must not silently change the host's separately specified translating mass or
rotating inertia. A later CAD-driven hardware-mass workflow can update those
explicitly with clear accounting.

## The matching-flat-face case found in this demo

The requested rounded cup face has a unique interior tangency in this sample.
The opposite flat block face is exactly parallel and coincident with the flat
ramp throughout the selected stroke. The cup and ramp slopes are distinct,
so simultaneous contact still determines translation. At held closure with
the specified ideal guide, the two normal force resultants are also determined.

The pressure resultant's position along the flat face is not determined by
those constraints. Moving that resultant changes its moment arm and the
required guide couple. A flat contact does not imply zero block torque, nor
does it justify reporting a particular midpoint or endpoint pressure centre.

The CINDER 1.2 compiled sliding provider conservatively rejects conformal
contact. The editable, nonpersistent sample uses CINDER's existing finite-profile
geometry inspection, whose four-map held force is independent of the arbitrary
flat-face endpoint it chooses internally. The application discards that
endpoint and its contact-only moment. It draws the full contact span and a
normal-direction arrow, reports the held resultants, and labels simulation
support as unavailable. It does not expose a run-ready component or a numeric
guide couple for this case.

Before enabling this template for saved simulations, extend CINDER itself:

- Certify the flat conformal mode and its complete finite overlap over the
  selected branch, independently of endpoint-contact policy. Preserve the
  existing uniqueness, conditioning and derivative checks.
- Represent the contact set explicitly. Separate a display anchor from a
  physically determined pressure location.
- Keep the canonical four-map force law. With the stated ideal guide, return
  force resultants and guide-couple bounds/indeterminacy rather than choosing
  a pressure centre silently. An assumed pressure law must be an explicit
  additional physical model, not a UI convenience.
- Propagate this distinction through reaction/impulse diagnostics and public
  serialization. Test it in the coupled host and event paths; publish a new
  CINDER release before the application consumes it.

The core extension needs its derivation in the root flyweight formulation
folder. This software proposal does not introduce another force formulation
or weaken the published compiler's rejection policy.

## Limits and feedback

Do not put arbitrary universal min/max ranges on all dimensions. Derive hard
geometry limits from the chosen construction and assembly. Use manufacturer
limits or user-supplied envelopes for actual hardware capacities. Suggested
slider ranges are conveniences; a typed value can exceed them if the physical
definition and solver support it.

| Check | Where it belongs | User feedback |
| --- | --- | --- |
| Finite numbers, units, positive dimensions, ordered extents | Immediate form validation and backend | Specific field message; retain the draft |
| Closed body, positive thickness, no self-intersection | Geometry resolution | Highlight the offending edges/region |
| Circle domain strictly inside its open semicircle | Geometry resolution | Show the affected arc endpoint and permitted construction |
| Enough track footprint over the whole branch | CINDER compilation | Show the first unsupported region and track extension needed when determinable |
| Unique regular two-contact branch and consistent mode | CINDER compilation | Distinguish singularity, mode change and unsupported/ambiguous proof |
| Tangential COM offset, relative sheave helix, unsupported guide | CINDER compatibility | Explain the missing model; do not silently project it away |
| Conformal face contact | Current CINDER compatibility | Geometry study can remain visible; simulation stays unavailable |
| Positive mass and physically admissible centroidal tensor | Mass resolution and CINDER | Point to mass source, axes or tensor entry |
| Block/body interference | Full-stroke section check first; whole-solid check when implemented | Mark position and interfering bodies; state whether the check is sampled |
| Compressive normals and retained-contact event impulses | Solved operating state and event checks | Name the contact and state where it would lift off |
| Guide loads, pressure, wear and strength limits | Additional hardware/constitutive models | Unknown when no capacity/model is supplied; never infer “safe” from ideal contact |

The accepted CINDER 1.2 profile families are line, quadratic and unrotated
circular-arc graphs z=f(r), on finite intervals. They are not general splines,
overhangs or arbitrary 3D contact surfaces. Even a supported primitive can be
rejected if its curvature bounds do not certify the requested branch. This is
a solver support result, not automatically evidence that real hardware cannot
work. Do not suggest “split the interval” as a complete cure for conformal
contact; splitting cannot determine its pressure distribution.

Report at least three separate statuses: **geometry preview**, **CINDER
compilation**, and **operating-state checks**. A held-RPM check is not proof for
all accelerations or impacts. A successful compiler result does not certify
guide strength, full 3D clearance or contact pressure.

## Updating previews reliably

Keep immediate drawing feedback local, then request authoritative backend
resolution/compilation after a short debounce. Cheap local geometry may show
the draft immediately; force values and validated motion belong only to the
matching backend result. Never show old forces as if they describe a new shape.

Each request includes a monotonically increasing draft revision. Each response
echoes it and includes the resolved mechanical digest and CINDER version,
feature-linked findings, supported interval, compilation diagnostics and
preview frames. Ignore responses from older revisions. Abort superseded
browser requests, but do not assume that aborting HTTP cancels backend work.

Bound compile cost, request rate, queue depth and cancellation server-side;
the anonymous template preview now has bounded inputs and frame count, a
16-entry result cache, a two-slot per-worker concurrency limit and the existing
database-backed IP throttle (90 requests per minute). Cache compiled
motion by canonical geometry and CINDER version; mass-only changes can reuse
geometry compilation. Cache mass properties separately by body/material input.
Only visual hardware changes should leave the mechanical digest unchanged.

Keep the last valid preview available but visibly stale while a draft is
pending or invalid. Block “use in simulation” until the current draft passes
authoritative compilation and host compatibility. Saving an unsupported
authoring draft can be separate from publishing a usable CVT revision. Save
and run submission must revalidate independently, with the same exact resolved
definition and revision checks.

## Import and measurements

A later import flow should explicitly ask for units, shaft axis, section plane,
body datum, cup/block/ramp selection and material/mass source. Start with DXF
lines/arcs for contact sections, then STEP for bodies. Preserve the original
file and transform, selected feature identities and conversion tolerances.
Reimport must surface lost selections instead of attaching to a different face.

Fit unsupported measured curves only with visible residuals and a declared
supported model. Position fit alone is insufficient: contact normals and
motion derivatives also need error checks. For a sampled profile, separate
measurement uncertainty from a solver's arithmetic tolerance. A calibrated
photo can guide measurements but cannot supply an unmeasured tangential width,
density, hidden pockets or real pressure distribution.

Established CAD workflows support this direction: Onshape exposes explicit
parallel, tangent and equal constraints and visually reports constraint
status [1]. Its DXF workflow requires units and offers an explicit file-origin
choice [2]. Fusion exposes COM, density and inertia data, including distinct
world and principal-axis moments [3]. OCCT's STEP translator handles units,
topology and shape tolerances [4]. These are reference patterns, not selected
dependencies or a promise that importing a file creates a valid CINDER model.

## Delivery order and acceptance

1. Extend and release CINDER's conformal-contact support for this exact matched
   face template; keep existing point-contact mechanisms supported.
2. Add the dimensioned template editor and authoritative preview contract,
   including mass derivation, linked angles and explicit compatibility status.
3. Integrate authoring drafts and resolved revisions with the physical library
   and run builder. Then add supported constrained profile editing.
4. Add measured data/DXF import, then solid CAD and multi-material bodies when
   their mass/geometry conversion can be validated.

Before the editor is usable for runs, verify: reopening reproduces dimensions
and geometry; unit changes preserve SI; linked angles cannot drift; density or
mass changes preserve the declared distribution; moving inserts update COM and
tensor; mesh quality cannot change mechanics; all stroke positions remain
supported; stale responses never enable save/run; invalid typed values remain
editable; keyboard controls and mobile selection work; and frozen runs keep
their original resolved inputs after subsequent edits.

## References

- [CINDER sliding-block API and current limits](../../cvtModel/docs/SLIDING_BLOCK_FLYWEIGHT.md)
- [Canonical physical formulations](../../docs/flyweight_mechanisms/README.md)
- [1. Onshape sketch constraints](https://cad.onshape.com/help/Content/Sketch/working_with_constraints.htm)
- [2. Onshape DXF/DWG insertion](https://cad.onshape.com/help/Content/Sketch/insert_dwg_or_dxf.htm)
- [3. Fusion PhysicalProperties API](https://help.autodesk.com/cloudhelp/ENU/Fusion-360-API/files/fusion_PhysicalProperties.htm)
- [4. OCCT STEP translator](https://dev.opencascade.org/doc/overview/html/occt_user_guides__step.html)
