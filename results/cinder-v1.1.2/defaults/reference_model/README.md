# CINDER v1.1.2 results reference model

This package defines the executable shared reference model used by general
v1.1.2 results studies.

## Secondary helix topology

The results reference CVT uses a **zero-clearance bilateral/slotted
torque-reactive secondary helix**.

The following CINDER 1.1.2 mechanics are preserved exactly:

- signed reacted belt torque;
- torsional spring/preload;
- movable-member rotational inertia;
- signed axial-force contribution;
- shaft reaction;
- helix kinematics;
- movable-member torque fraction.

The only topology choice is that the helix reaction may be carried by either slot
flank. No absolute value, clipping, or force-law modification is introduced.

## Why the loader exists

The public CINDER 1.1.2 JSON schema has no bilateral-topology selector. The
frozen public Baja document therefore remains under `../baja/`, and
`decode_reference_case()` applies the declared results topology immediately
after normal public decoding.

There is no runtime installation, `.pth` file, environment variable or
process-global monkey patch. A study inherits this topology only by using the
shared results reference-case loader.

## Scope

Shared Baja-reference studies use `decode_reference_case()`. Studies that build
their own independent assembly remain explicit by design; if such a study wants
the shared helix policy it should call `use_bilateral_secondary_helix()` on its
constructed plant rather than relying on hidden global state.
