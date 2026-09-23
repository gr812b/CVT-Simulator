# Data available for drafting Section 4.5 and its appendix

Use the newly returned final run, not the exploratory result as a substitute.

- `suite.json`: exact selection, execution controls and environment.
- `unified_course/campaign.json`: analytic road parameters, ordered sector
  intervals, all selected tune dictionaries and final numerical controls.
- `*/competitors_resolved.csv`: physical mass, spring-rate/preload, ramp, and helix values plus
  every serialized departure from the common baseline.
- `*/cases/*/resolved_case.json`: independent complete initial configuration,
  course, controls and tune identity for that individual trajectory.
- `*/cases/*/model_identity.json`: actuator/boundary classes and referred
  inertias; confirms the full-dynamic bilateral common mechanics.
- `*/cases/*/definition_checks.json`, `ramp_profile.csv`, and
  `shape_mechanism_map.csv`: released fixed-pivot geometry validation and the
  physical spring/ramp/mechanism maps used for the selected shape cases.
- `*/cases/*/events.json`: exact before/after states, timestamps, positions,
  regime transitions, velocity jumps and available capture metadata.
- `*/cases/*/diagnostics.csv`: solved accelerations, forces, torques, contact
  margins, power transfer and loss diagnostics alongside vehicle response.
- `unified_course/shift_shape.html` plus `shift_shape_*.csv`: opening-flat
  free-shift/stick--stick RPM--RPM shape comparisons, local secants, and exact
  definitions; these deliberately exclude clutch slip, support-held motion,
  hill backshift and descent.
- The selected D02 mechanism family is `D02`, `D02_M`, `D02_M170`, and `D02_P`.
  Use the saved hill events and diagnostics to distinguish traction failure,
  successful repair, and high-primary-force resistance to backshift; do not
  infer those outcomes from the case labels alone.
- `unified_course/final_checks/`: settling criteria, every tested window,
  tail means and failure chronology. Quote means as settled only for passing
  rows, retaining the finite-window qualification.
- `tables/`: all experiments' outcomes, time/sector records, cyclic metrics,
  settling records, event index and physical tune values in one place.
- `flat_800m/feature_metrics.csv`: full-shift attainment and final-window flat
  behavior for R00 versus U55. This finite experiment does not prove global
  mathematical unreachability.
- Case `summary.json` and `execution.log`: stopping reason and runtime. A
  progress/rollback censor is different from a model-domain/numerical error.

Presentation groups organize existing data, not independent extra runs.
Energy diagnostics remain distinct from physical efficiency. The descent's
full-throttle overspeed-tail behavior must remain attached to the engine-boundary
assumptions. No outcome-based changes to the frozen course are made here.
