# Shared v1.1.2 results support

This directory contains ordinary **results-side Python helpers**. Nothing here is
installed into the venv and nothing is imported automatically when Python starts.
The frozen `cinder-cvt==1.1.2` wheel remains untouched.

## Shared results reference model

`reference_model.py` provides the standard v1.1.2 results decoder:

```python
from support.reference_model import decode_results_simulation_case_document
```

That helper first uses CINDER's public simulation-document decoder, then replaces
only the secondary `HelicalTorqueReactionForce` with a zero-clearance
**bilateral/slotted** twin. The inherited signed helix torque, axial force,
torsional spring, movable-member inertia, shaft reaction, geometry and contact
kinematics are unchanged. The twin simply does not advertise a selected-flank
unilateral compression margin to `PulleyActuator`; a sign reversal is therefore
carried by the opposite slot flank.

This is the default reference topology for result studies that use the shared
results decoder. A study that intentionally wants the published unilateral helix
can simply use `cinder.contracts.decode_simulation_case_document` directly. No
environment variable or global policy switch is required.
