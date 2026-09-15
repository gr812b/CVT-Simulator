# Mechanical invariants — operating-domain audit

This study is frozen as the CINDER 1.1.2 operating-domain mechanical-invariant
verification.

Run:

```bash
python verify_study.py
python run_reference.py
python build_capability_map.py
```

`run.py` is the core audit implementation and now decodes the shared Baja input
through `defaults.reference_model.decode_reference_case`, so the bilateral
secondary helix is part of the study's starting reference model rather than a
study-local overlay. `run_reference.py` adds the deterministic rare-contact
reproduction anchors and writes reference-model provenance beside the artifacts.

## Reference topology

The secondary torque-reactive helix is a zero-clearance **bilateral/slotted**
contact. Signed helix torque, axial force, torsional spring, movable-member
inertia, torque sharing and helix kinematics are unchanged.

The hard physical topology limits challenged here are therefore the belt/contact
and remaining mechanism constraints themselves: nonnegative belt tension,
nonnegative local and integrated wrap normal loading, Coulomb-consistent
stick/slip states, active kinematic constraints, travel-stop reactions, and any
other explicitly one-sided retained contact.

## Shared case vocabulary

Reusable operating cases live in
`../../defaults/verification/operating_cases.json`. The library includes
deterministic reproduction anchors for:

- `secondary_slip_plus`;
- `both_slip_mp`.

An anchor does not bypass mechanics. It counts only if production
classification, the exact initial audit, hybrid continuation and exact successor
checks all pass.

## Scientific scope

The harness challenges the nominal Baja trajectory, static rest, deadzone and
engaged structural states, both shift directions, forward/reverse rotation, both
single-interface slip directions, all four both-slip quadrants, full geometry
range, belt tension field, distributed normal loading, stop/mechanism reactions,
8x8 closure self-consistency, and exact hybrid successors.

The completed run is summarized by
`CINDER_v1.1.2_mechanical_invariants_recap.pdf`.
