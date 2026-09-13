# Replacement notes

This package is the operating-domain replacement for the earlier nominal-only
CINDER v1.1.2 mechanical-invariants study.

Earlier revisions added controlled fixed-boundary initial-condition searches,
all gross contact modes/signs, reverse rotation, free shift both ways, static
rest, structural boundary arrivals, full-domain geometry checks, exact belt
field admissibility, exact successor audits, negative controls, and the shared
release-level operating-case library.

## Results-reference / rare-contact revision

This revision incorporates the conclusions of the dedicated missing-coverage
exploration:

- general v1.1.2 result studies now use a results-local zero-clearance
  **bilateral/slotted secondary helix**; the production signed force/torque law
  is unchanged and only the selected-flank unilateral margin is removed;
- the policy lives under `results/cinder-v1.1.2/support/` as an ordinary shared decoder/helper; nothing is auto-installed or applied process-wide, and no `cvtModel/` or published wheel source is modified;
- the active policy is declared in `../../defaults/results_reference_model.json`;
- two rare but fully demonstrated contact states are promoted into the shared
  operating-case defaults as deterministic reproduction anchors:
  `secondary_slip_plus` (exploration attempt 2535) and `both_slip_mp`
  (attempt 3951);
- `run_reference.py` tries those anchors first, but still requires the production
  classifier, full hard-invariant audit, real hybrid continuation and exact
  successor checks; it falls back to the ordinary deterministic search if an
  anchor fails;
- two states whose earlier continuations terminated only on unilateral helix
  lift-off are retained as slotted-topology capability probes;
- `CAPABILITY_INTERPRETATION.md` freezes the assumption-to-consequence framing
  and the next local-neighbourhood refinement needed to turn coverage into a
  defensible broad/easy vs constrained/extreme operating-domain map;
- `build_capability_map.py` produces a preliminary artifact-level diagnostic
  table without treating its provisional labels as publication-grade claims.

- `run_capability_probes.py` directly replays the two states that previously terminated only on unilateral helix lift-off under the slotted policy; these probes are descriptive and do not gate invariant PASS.
