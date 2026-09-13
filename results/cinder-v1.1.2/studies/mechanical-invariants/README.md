# Mechanical invariants — operating-domain audit

This study replaces the earlier nominal-trajectory-only mechanical-invariants
check for CINDER 1.1.2. The canonical policy-aware run is:

```bash
python verify_study.py
python run_reference.py
python run_capability_probes.py
python build_capability_map.py
```

`run.py` remains the core audit implementation. `run_reference.py` is the
results-reference entry point: it decodes the frozen case through the shared
results helper, tries shared rare-contact reproduction anchors before the
ordinary search, then runs the unchanged core audit and records the active
reference model beside the artifacts. Nothing is installed or applied globally.

## Reference topology

For general result studies the secondary torque-reactive helix is a
zero-clearance **bilateral/slotted** contact. The signed production helix torque,
axial force, torsional spring and movable-member inertia are untouched. Only the
selected-flank unilateral admissibility check is removed. This is intentional:
this study is primarily trying to find the limits of the belt/contact reduction,
not the limits of one particular helix flank design.

Other unilateral contacts and travel-stop reactions remain hard physical
constraints. A dedicated helix-topology study can later compare unilateral and
slotted behavior directly.

## Shared case vocabulary

Reusable operating cases live in
`../../defaults/verification_operating_cases.json`. In addition to the standard
search domains, that file now contains deterministic reproduction anchors for
the two contact classes that the broad missing-coverage exploration showed were
valid but unusually difficult to discover:

- `secondary_slip_plus`;
- `both_slip_mp`.

The anchors do **not** bypass classification or mechanics. They count only when
CINDER's production initial classifier selects the requested branch, the exact
initial state passes every hard invariant, a real hybrid continuation completes,
and exact successor states remain admissible. If an anchor ever stops passing,
the ordinary deterministic search still runs and the study remains REVIEW/FAIL
rather than forcing coverage.

## Scientific scope

The harness challenges the nominal Baja trajectory, static rest, deadzone and
engaged structural states, both shift directions, forward/reverse rotation, both
single-interface slip directions, all four both-slip quadrants, full geometry
range, belt tension field, distributed normal loading, stop/mechanism reactions,
8x8 closure self-consistency, and exact hybrid successors.

`PASS` means every required deterministic class was found and every accepted
state/successor satisfied the retained topology. It is broad operating-domain
evidence, not proof over the continuum of every real-valued initial condition.

The more interesting follow-on is **capability**, not just coverage.
`CAPABILITY_INTERPRETATION.md` records the assumption-to-consequence map and the
planned local-neighbourhood refinement needed to describe which regimes are
broad/easy, valid but transient, or extreme/narrow. `build_capability_map.py`
turns each run's raw artifacts into a preliminary diagnostic table without
pretending those provisional labels are already publication-grade.

Generated results live in `artifacts/` and are not committed by the clean study.
