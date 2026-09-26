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

## Current manuscript selection — 24 September rebuild

The main text now presents the actual selected operating cases and dimensional
mechanical results. The former contact-persistence figure and its main-text
recommendation are superseded. They remain historical, not mandatory designs.
`analysis/reader_evidence.py` produces the numerical TeX values and a complete
extrema/mask record. It distinguishes cases from coverage tags and saved points,
includes exact outgoing states, and retains signed tolerance residuals.

The spatial wrap-loading figure is retained as **Appendix D.1 support**, not the
organising argument of 4.2.1. Its maintained generator is
`analysis/plot_profile.py`; `analysis/reconstruct_profile.py` can recreate its
two event-side fields with frozen CINDER 1.1.2. The selected event is a sliding
reversal, not evidence that every possible sticking root was excluded.

From repository root, using the frozen environment:

```bash
results/cinder-v1.1.2/.venv/bin/python results/cinder-v1.1.2/verify_environment.py
# Reuse the delivery's evidence/ (which includes profiles/); no simulation:
results/cinder-v1.1.2/.venv/bin/python results/cinder-v1.1.2/studies/mechanical-invariants/run.py \
  --plot-only --artifacts-dir /path/to/delivery/evidence --figure-dir /tmp/cinder-reader-evidence
```

For separately retained profile data, add `--profile-data-dir /path/to/profile/data`.
The complete audit's `execution_provenance.json` and input/output snapshots are
required. The profile inputs must hash-match that audit. Plot-only does not
integrate dynamics. It writes `verification_values.tex`, `reader_evidence.json`,
`reader_evidence_provenance.json`, `primary_wrap_profiles.{pdf,png}` and figure
provenance. The inherited capability-map postprocessor remains exploratory.

A fresh `python run.py` still runs the canonical audit, then reconstructs the
selected profile before plotting. It recreates the generated `artifacts/`
directory as before. Never point a full run at retained source evidence.
The original rebuild reused the retained full audit. The subsequent
author-requested drift explanation adds the targeted check below.

### Targeted sticking-speed drift check

To reproduce the numerical support for the revised tolerance explanation:

```bash
results/cinder-v1.1.2/.venv/bin/python results/cinder-v1.1.2/studies/mechanical-invariants/run.py \
  --check-stick-drift --artifacts-dir /path/to/delivery/evidence \
  --figure-dir /tmp/cinder-reader-evidence
```

`analysis/sticking_drift.py` identifies the largest applicable sticking drift
across the retained segment and exact outgoing states. It loads the archived
entry point and selected seed, reproduces the original anchor-selection
stage, and starts nominal and tighter integrations from identical copies of
the resulting prepared system. This preserves the contact solver's numerical
continuation history; simply reconstructing the state does not reproduce the
archived numerical path exactly. The final audit's bench settings are used,
not the distinct settings used during anchor selection.

The command checks the frozen environment and all original input/output
hashes. It requires agreement with all 92 retained rows in time, mode, shift,
shift speed and both relative speeds, plus the retained transition names and
reasons. Both integrations are audited with the original masks and guards.
Their native segment/end/event-side samples are exported without interpolation
across transitions. `sticking_drift_check.json` records settings, selected
extrema, signed speeds, full event signatures and provenance; the companion
TeX file supplies the main-text values. The original audit is not modified.
The retained result is in `provenance/sticking_drift_2026-09-24/`.

Only relative and absolute integration tolerances change (both divided by
ten); step cap, initial state, loading, model and audit spacing stay fixed.
The smaller sampled mismatch and unchanged event sequence support the local
drift explanation. They do not establish global convergence or turn the
1 mm/s reporting guard into a physical friction parameter.

Focused tests:

```bash
results/cinder-v1.1.2/.venv/bin/python -m unittest discover \
  -s results/cinder-v1.1.2/studies/mechanical-invariants/tests -v
```

The main passage, integration/build tools and current brief are in
`docs/CVT_Module_Formulation/results-finalization/rebuild-4-2-1/`.
See that unit's README before integrating into a later manuscript.

## Historical selection — 23 September (superseded)

The 23 September `run.py` included the maintained capability postprocessor and the selected
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

The following command is retained as historical documentation of that selection;
the current command above produces the replacement tables and appendix figure:

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
