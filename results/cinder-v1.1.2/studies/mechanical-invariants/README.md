# Mechanical invariants — operating-domain audit

This study is frozen as the CINDER 1.1.2 operating-domain mechanical-invariant
verification.

Run:

```bash
python verify_study.py
python run.py
# Reuse the identified audit; no dynamics are reintegrated:
python run.py --plot-only
```

`run.py` invokes `infrastructure/core.py` and decodes the shared Baja input
through `defaults.reference_model.decode_reference_case`, so the bilateral
secondary helix is part of the study's starting reference model rather than a
study-local overlay. `run.py` adds the deterministic rare-contact
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

The historical run is summarized by
`CINDER_v1.1.2_mechanical_invariants_recap.pdf`. The reproduced manuscript
selection and differences from that recap are recorded in
`provenance/SECTION_4_2_1.md`; the recap is not silently replaced.

## Selected manuscript figure

`run.py` now includes the maintained capability postprocessor and the selected
publication plot in `analysis/publication_plots.py`. Its two panels distinguish
initial contact persistence from local full-wrap contact loading. It does not
infer how frequently a regime occurs in a drive or the size of an admissible
neighbourhood. Raw generated evidence remains ignored by Git.

From repository root, with the frozen environment installed:

```bash
results/cinder-v1.1.2/.venv/bin/python results/cinder-v1.1.2/verify_environment.py
results/cinder-v1.1.2/.venv/bin/python results/cinder-v1.1.2/studies/mechanical-invariants/run.py
```

The default run recreates this study's `artifacts/`, runs the original canonical
audit, saves exact input snapshots and output hashes, checks the evidence and
writes `artifacts/publication/contact_regimes.{pdf,png}` plus values and a
figure-specific provenance record. It also produces `capability_map_draft.csv`
and `.md`, which retain their exploratory interpretation limits.

To reproduce the figure into a clean location from verified retained outputs:

```bash
results/cinder-v1.1.2/.venv/bin/python results/cinder-v1.1.2/studies/mechanical-invariants/run.py \
  --plot-only --figure-dir /tmp/cinder-4-2-1-figure
```

To use the evidence directory from the delivered archive instead, add
`--artifacts-dir /path/to/extracted/evidence`. This directory must contain
`execution_provenance.json`, `execution_inputs/` and the recorded output files.
Missing or changed inputs/outputs fail explicitly. Never run a full audit with
`--artifacts-dir` pointing at source files: a full run recreates its output
directory. Plot-only does not delete or reintegrate the evidence.

Copy the checked figure PDF/PNG into
`docs/CVT_Module_Formulation/figures/results/verification/` when integrating a
new author-reviewed selection. The selected asset, extracted data, generating
script and source hashes are connected by `contact_regimes_provenance.json`.
PDF export dates are suppressed for deterministic export.

Focused selection checks:

```bash
results/cinder-v1.1.2/.venv/bin/python -m unittest discover \
  -s results/cinder-v1.1.2/studies/mechanical-invariants/tests
```
