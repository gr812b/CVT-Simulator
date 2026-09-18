# Frozen Baja reference input

`simulation_case.json` is the authoritative public CINDER 1.1.2 simulation
document used as the parameter/state baseline for shared Baja-reference studies.

`tuning.json` is the human-readable tuning manifest and is secondary to the
executable public document.

`provenance.json` records the release source identifiers.

The public v1.1.2 schema does not encode the results programme's bilateral helix
topology. That executable results interpretation is owned by
`../reference_model/`; the public document itself remains valid unmodified
CINDER 1.1.2 input.
