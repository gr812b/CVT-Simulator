# PR #471 + develop semantic merge

This drop-in combines the formulation/impact corrections from PR #471 with the
newer runtime contracts already present on `develop`.

Kept from the formulation-alignment work:

- cord/pitch radius for traction/torque kinematics;
- signed physical normal/traction convention;
- one-sided deadzone/engaged geometry at `s = s_e`;
- velocity-level stick admissibility;
- generalized mass-metric capture/impact projection;
- secondary closed-stop low-ratio support and helix momentum transfer;
- upper/lower stop momentum-consistent impacts;
- exact geometry event surfaces with ULP-only boundary identity snapping.

Restored/merged from current `develop`:

- explicit physical `time` in `PulleyActuationContext` and actuation studies;
- time propagation through engaged, deadzone, classification, event, and
  inspection paths;
- zero-slip physical-limit fallback and simultaneous contact-topology exchange;
- immediate release of an already-active unilateral seat/stop if a contact
  topology change makes its recovered reaction tensile;
- zero-width deadzone / always-engaged operating-limit support.

Validation performed on this merged tree:

- 30 targeted smoke/merge-regression tests passed;
- default 45 s hill-step completed normally (12 transitions);
- tight 45 s energy audit completed with a -0.255713 J residual on
  78.159777 kJ net external work.

The older broad `test/cinder` suite still contains unrelated stale legacy
imports in `fixtures.py` (for example `cinder.model.boundaries.output`) and is
not used as the acceptance suite for this drop-in.
