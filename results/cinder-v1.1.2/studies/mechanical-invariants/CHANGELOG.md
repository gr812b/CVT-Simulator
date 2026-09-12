# Replacement notes

This package is intended to replace the earlier CINDER v1.1.2 `mechanical-invariants` folder.

Major changes:

- nominal Baja run retained but no longer treated as sufficient coverage;
- controlled bench uses production `FixedShaftBoundary` + `NoHost` around the exact frozen plant;
- deterministic initial-condition search for all four engaged contact modes;
- both kinetic directions at each pulley and all four both-slip quadrants;
- forward and reverse overall rotation cases;
- interior free-shift continuations with both positive and negative shift velocity;
- true zero-speed / zero-external-torque static lower-stop case integrated as a hold test;
- full-domain geometry sweep with one-sided deadzone checks and finite-difference derivative cross-checks;
- explicit deadzone-free case and directed lower-stop, engagement, low-ratio-seat, and upper-stop arrivals;
- exact minimum full-loop belt tension check;
- exact minimum distributed wrap normal-loading check;
- reconstructed wrap-normal integral cross-check against solved `N_p,N_s`;
- generic unilateral mounted-mechanism margin audit;
- exact post-transition states are hard pass criteria;
- outgoing slip segment endpoints are excluded only from the narrow direction-consistency check at a zero-crossing event;
- invalid-state negative controls and engagement one-sided classifier controls;
- explicit PASS / REVIEW / FAIL distinction based on hard mechanics vs missing coverage.

## Follow-up revision after first operating-domain run

The first domain run returned no hard invariant failures but exposed five coverage gaps. This revision changes the harness, not the CVT mechanics:

- slip-direction searches now try both signs of overall rotation before declaring a requested relative-slip class missing;
- a short-lived kinetic branch may count when it persists for a resolved nonzero interval above the event-time scale and the complete short hybrid continuation plus exact successor states remain admissible; the previous 0.5 ms dwell requirement was an arbitrary verification artifact;
- rejected classified candidates now retain field-level diagnostics (minimum tension, local normal loading, resultants, static margins, mechanism margin, closure residual) and full classifier error text;
- a small edge-domain fallback search probes low/high shift, speed, slip, and wider signed shaft torque values without exploding the main grid;
- nonzero-sdot engaged probes now use CINDER's production representative-contact-speed definition to initialize zero relative motion, including the secondary helical member kinematics;
- lower-stop arrival probes now include low/zero primary and secondary speeds instead of only the high-RPM deadzone setup that tended to reverse before reaching the stop;
- positive/negative free-shift coverage is credited from any audited engaged-free trajectory, including the frozen nominal case, rather than only from a dedicated synthetic case ID.
