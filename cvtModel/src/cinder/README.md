# CINDER package layout

CINDER separates the physical model from numerical execution:

```text
cinder/
  model/
    cvt/          # belt/pulley geometry, profiles, actuation, contact, inertia, closure, equations
    boundaries/   # input torque sources and output-side vehicle/dyno mappings
    system/       # CVTAssemblySpec, CVTSimulationCase, state, and runtime evaluator
  execution/
    hybrid/       # integration, modes, events, impacts, and transition logic
```

`model` contains physical laws and the state-frozen evaluator. `execution`
contains no CVT force laws: it advances the evaluator through hybrid regimes.
`studies` and `results` are intentionally deferred to the next phase.

## CVT-only assembly and executable case

```python
from cinder.execution.hybrid.cvt_operating_hybrid import CVTOperatingSystemConfig
from cinder.model.system import CVTAssemblySpec, CVTSimulationCase

assembly = CVTAssemblySpec(...)
case = CVTSimulationCase(
    cvt=assembly,
    input_boundary=engine_or_motor,
    output_boundary=vehicle_or_dyno,
    scenario=scenario,
)
execution = CVTOperatingSystemConfig(
    traction_law=traction_law,
    solve_settings=solve_settings,
    operating_limits=operating_limits,
)
system = execution.build(case)
```

A final drive, wheel, vehicle, and road profile live in the output boundary,
because together they define the output-shaft torque/inertia mapping. They do
not belong in `CVTAssemblySpec`.

## Generic pulley actuation

`PulleyActuator` sums force laws through `evaluate_relation()`, the minimal
RHS-facing API. A mounted helical torque reaction receives a
`PulleyClosureChannels` map from its host pulley rather than hard-coding input
or output closure columns.  The installed `HelicalPulleyCoupling` lives
structurally inside that `PulleySpec`, rather than in a global selector object.

The current six-state shift equations retain the validated output-pulley
helical kinematics. Supporting an input-mounted helix in the complete dynamic
system requires a generalized rotational-coordinate derivation, so assembly
construction rejects that configuration rather than silently ignoring it. The
actuator law itself is generic today and can be evaluated through the same
contract on either pulley.

## Clean break

Only the `model` and `execution` paths exist in this package. There are no
legacy root modules, alias packages, or fallback constructor paths.
