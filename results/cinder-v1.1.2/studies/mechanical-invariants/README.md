# Mechanical invariants — operating-domain audit

This folder **replaces** the earlier nominal-trajectory-only `mechanical-invariants` study for CINDER 1.1.2.

Run from this directory with the same frozen release environment used by the other v1.1.2 studies:

```bash
python verify_study.py
python run.py
```

The study intentionally uses two kinds of systems. The realistic reference case is decoded from `../../defaults/baja_reference_simulation_case.json`. Controlled mechanics cases reuse the **same decoded production CVT assembly** but attach CINDER's existing `FixedShaftBoundary` to both shafts and `NoHost`. No alternative test-only CVT equations are introduced.

The controlled cases exist because a nominal launch cannot exercise the full initial-value capability of the model. The harness deliberately searches for admissible initial conditions covering stick-stick, both mixed stick/slip modes, both kinetic directions at each interface, all four both-slip relative-velocity quadrants, forward/reverse overall rotation, deadzone/static states, and directed arrivals at each structural boundary. Candidate states only count when CINDER's **production initial classifier** selects the requested branch and a short production hybrid integration remains mechanically admissible. Slip-direction searches try both overall rotation signs; rejected classified candidates retain the field-level margins needed to determine whether a missing class is a search limitation or a genuinely inadmissible topology.

For nonzero-shift-speed engaged probes, the harness initializes tangential compatibility using CINDER's production representative-contact-speed definition, so secondary helix motion is included rather than approximated away. The field-level engaged checks include the complete recovered belt tension field and distributed wrap normal loading, not only the integrated pulley normal resultants. See `REFERENCE.md` for the precise scientific claim and pass logic.

`PASS` is intentionally demanding: every required coverage class must be found, all accepted samples and exact successor states must satisfy the invariant checks, and invalid-state controls must be rejected. `REVIEW` means no hard invariant failed but at least one requested coverage class could not be populated by the deterministic search. `FAIL` means an accepted state violated a hard invariant or a negative/classifier control failed.

Generated results live in `artifacts/` and are not committed by the clean-study package.
