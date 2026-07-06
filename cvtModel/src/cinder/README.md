# CINDER package layout

CINDER separates the physical model, numerical execution, and post-integration
engineering results:

```text
cinder/
  model/
    cvt/          # belt/pulley geometry, profiles, actuation, contact, inertia, closure, equations
    boundaries/   # input torque sources and output-side vehicle/dyno mappings
    system/       # CVTAssemblySpec, CVTSimulationCase, state, and runtime evaluator
  execution/
    hybrid/       # integration, modes, events, impacts, and transition logic
  results/        # raw traces, state inspection, signal materialization, observers, audit access
  studies/        # static engineering analyses built above resolved model objects
    geometry/     # Case A/B geometry solves, paths, radius planes, sensitivity fields
```

`model` contains physical laws and state-frozen evaluation. `execution` contains
no CVT force laws: it advances the evaluator through hybrid regimes. `results`
replays the same model at selected saved states after integration; it does not
change the integrated trajectory.

## Static geometry studies

`cinder.studies.geometry` adds a small design-study layer above the resolved
`BeltPulleyGeometrySpec`. It deliberately does not add plotting or frontend
objects. The two solvers are:

- `solve_geometry_from_endpoint_radii(...)` for Case A, using the low-ratio
  primary/secondary outer radii;
- `solve_geometry_from_target_ratios(...)` for Case B, using desired maximum
  and minimum effective-radius ratios.

Both return the same `ResolvedGeometryDesign`, which can be passed to the
independent `sample_geometry_path`, `evaluate_radius_plane`,
`evaluate_ratio_sensitivity_field`, and `evaluate_geometry_feasibility` calls.
The last two calls return numeric fields for client-side contour and surface
rendering; CINDER itself has no plotting dependency.

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

## Lean runtime versus expanded inspection

The normal hybrid RHS uses only the runtime evaluation required to advance the
state:

```python
runtime = system.evaluate_runtime(t, state, mode)
derivative = runtime.derivative
```

This path does not build labels, chart signals, contribution dictionaries, or
closure audit matrices. Engaged-contact closure uses its lean solve path during
normal integration.

For a detailed explanation of one frozen state, use the explicit inspection
path:

```python
inspection = system.inspect(t, state, mode)
```

Inspection can expose actuator terms, contact quantities, and—when explicitly
requested through `inspect_cvt_state(..., include_closure_audit=True)`—the full
closure matrix, right-hand side, residuals, rank, and condition number.

## Raw trace and reported result

The raw integrator output remains available through `integrate()`. To make that
boundary explicit:

```python
trace = system.integrate_trace(
    time_span=case.scenario.time_span,
    initial_state=case.scenario.initial_state,
)
```

A result report is built afterward and can be sampled independently of solver
steps:

```python
from cinder.results import CVTResultBuilder, ReportingGrid, ReportingSettings

# Native uses every accepted solver state and needs no retained dense output.
result = CVTResultBuilder(system=system).build(
    trace,
    settings=ReportingSettings(grid=ReportingGrid.native()),
)
```

The high-level convenience call returns CINDER's standard 10 ms frontend/report grid:

```python
result = system.run(
    time_span=case.scenario.time_span,
    initial_state=case.scenario.initial_state,
)
```

Override the grid only when the caller has a specific need:

```python
from cinder.results import ReportingGrid, ReportingSettings

coarser_result = system.run(
    time_span=case.scenario.time_span,
    initial_state=case.scenario.initial_state,
    reporting_settings=ReportingSettings(
        grid=ReportingGrid.uniform_time_step(0.02),
    ),
)

accepted_step_result = system.run(
    time_span=case.scenario.time_span,
    initial_state=case.scenario.initial_state,
    reporting_settings=ReportingSettings.native(),
)
```

`system.run()` automatically retains SciPy's per-segment dense solution when a
uniform grid is requested. The raw adaptive trace is still retained unchanged in
`result.trace`; CINDER evaluates SciPy's own continuous solution at the requested
report times and never interpolates a state across a hybrid transition. Each
transition remains represented by exact pre- and post-transition points, even
when they share the same timestamp. To manually build a uniform report from a
trace, integrate with `HybridIntegratorSettings(retain_dense_output=True)` first.

`CVTIntegrationResult` preserves raw hybrid segments and transitions while
adding stable generic signal channels. Standard groups include:

- `state`: integrated state histories;
- `geometry`: radii, ratio, and wrap angles;
- `boundary` / `vehicle`: source and load observables;
- `actuation`: total clamp and per-law contributions;
- `contact`: lambdas, margins, relative speeds, normals, and transmitted torque;
- `observer`: postprocessed shaft angle, work, and slip-dissipation estimates.

Reports only add cost when materialized. `integrate()` and `integrate_trace()`
remain lean and do not replay reporting states.

## Generic pulley actuation

`PulleyActuator` sums force laws through `evaluate_relation()`, the minimal
RHS-facing API. A mounted helical torque reaction receives a
`PulleyClosureChannels` map from its host pulley rather than hard-coding input
or output closure columns. The installed `HelicalPulleyCoupling` lives
structurally inside that `PulleySpec`, rather than in a global selector object.

The present six-state shift equations retain the validated output-pulley
helical kinematics. Supporting an input-mounted helix in the complete dynamic
system requires a generalized rotational-coordinate derivation, so assembly
construction rejects that configuration rather than silently ignoring it. The
actuator law itself is generic today and can be evaluated through the same
contract on either pulley.

## Clean break

The package contains `model`, `execution`, `results`, and the static `studies`
layer. There are no legacy root modules, alias packages, or fallback constructor
paths.
