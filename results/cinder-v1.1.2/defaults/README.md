# Frozen Baja reference defaults

The authoritative public solver input is:

```text
baja_reference_simulation_case.json
```

It is a complete `cinder_composed_simulation_case` copied semantically from the
released `cinder-v1.1.2` example. `provenance.json` records the source tag,
commit, path, blob SHA, and PyPI package version.

The document contains every runtime input category required for the reference
simulation, including belt/pulley geometry, friction law, inertias, flyweight and
spring hardware, the torque-reactive secondary helix, engine/vehicle boundaries,
initial state, solver settings and reporting settings.

## Results reference-model policy

`results_reference_model.json` declares the one deliberate results-side topology
override used by the general v1.1.2 results programme: the secondary
 torque-reactive helix is treated as a zero-clearance **bilateral/slotted**
reaction rather than a selected unilateral flank.

The override does **not** change the helix's signed torque or axial-force law,
torsional preload, movable-sheave inertia, or shaft reaction. It removes only the
selected-flank compression inequality. The public simulation document remains
unchanged and therefore remains valid CINDER 1.1.2 input; the results support
layer records the additional topology choice separately.

This makes unusual belt/contact stress tests answer questions about the belt and
closure formulation instead of terminating on a particular helix hardware
flank. A dedicated future study should compare unilateral and slotted designs
explicitly.

## Shared verification operating cases

`verification_operating_cases.json` is a second kind of release default: it is
not one executable simulation, but the canonical vocabulary of controlled
verification cases used by multiple studies. It owns common fixed-boundary
inertias, torque/speed/shift search ranges, tangential contact branch requests,
free-shift directions, static-rest and structural-boundary recipes.

After the dedicated missing-coverage exploration, it also owns two deterministic
**rare-contact reproduction anchors** (`secondary_slip_plus` and
`both_slip_mp`). Those states are not pre-approved solutions: a consuming study
must still let the production classifier select the requested topology and must
re-run its complete physical/invariant checks and hybrid continuation. They are
kept so later studies can reproduce the same difficult operating classes instead
of rediscovering them through thousands of search attempts.

Two additional states that previously failed only on unilateral helix flank
lift-off are kept as capability probes for the slotted reference topology.

Mechanical invariants and closure conditioning consume the shared case library;
other studies may reuse the same operating vocabulary while keeping their own
metrics and pass/fail policy.

## Human tuning manifest

`baja_reference_tuning.json` is deliberately secondary to the executable JSON.
It records physical knobs obscured by the runtime representation, including
flyweight masses/ramp, primary spring, secondary spring/torsional preload, helix
angle, final drive and engine equivalent inertia.

A study must execute the public simulation document and explicitly record any
results-side topology/configuration policy applied after decode.

## Release provenance

The source release is `cinder-v1.1.2` at commit
`7637a38b4fb9ec21dfb953c1c80a27ec5f389654`; exact source identifiers are
recorded in `provenance.json`.
