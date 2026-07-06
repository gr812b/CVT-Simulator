# CINDER Getting Started

CINDER is a mechanics library for rubber V-belt CVTs. It can do three useful things without a backend or frontend:

1. **Describe and validate one CVT assembly**
2. **Run static design studies** for geometry and actuator clamping force
3. **Run a transient simulation** once engine, output boundary, scenario, and solver settings are supplied

This guide uses the stable external-facing helpers in `cinder.contracts` where possible. They are the easiest path for scripts, saved designs, a CLI, or a future backend.

---

## 1. Setup

From the repository root, create an editable development install:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
```

On macOS/Linux, activate the environment with `source .venv/bin/activate`.

CINDER itself needs NumPy and SciPy. It has no plotting dependency. Project-level plotting and tuning scripts belong outside `src/cinder`, for example under the repository’s `launchTools/` directory.

---

## 2. The shortest useful starting point

There is an editable, complete example assembly document at:

```text
examples/baja_baseline_assembly.json
```

Load it, decode it into a real CVT assembly, and run a preflight check:

```python
import json
from pathlib import Path

from cinder.contracts import decode_assembly_document, validate_assembly

payload = json.loads(Path("examples/baja_baseline_assembly.json").read_text())
assembly = decode_assembly_document(payload)

report = validate_assembly(assembly)
for finding in report.findings:
    print(f"[{finding.severity}] {finding.code}: {finding.message}")

assert report.is_valid
```

`assembly` is now the core CVT-only object used by static studies and simulations.

---

## 3. How to know what inputs a component needs

Ask CINDER for its factual component catalog and its public conventions:

```python
import json
from cinder.contracts import component_catalog_document, public_conventions

print(json.dumps(public_conventions().as_dict(), indent=2))
print(json.dumps(component_catalog_document(), indent=2))
```

The catalog currently lists the built-in document-supported mechanisms:

```text
axial_spring
centrifugal_ramp
helical_torque_reaction
```

For each component it tells you:

```text
parameter key
human label
unit
whether it is required
basic allowed range
short description
```

Use this instead of guessing field names. For example, an axial spring uses:

```json
{
  "kind": "axial_spring",
  "stiffness_N_per_m": 12784.0,
  "initial_compression_m": 0.10,
  "compression_per_axial_position": 1.0
}
```

A centrifugal ramp uses a mass, an initial radius, and a piecewise ramp profile. A torque-reactive helix uses torsional stiffness, initial twist, a movable-member torque fraction, and a separate output-pulley helical-coupling profile.

The example JSON is the best complete reference for the current document shape.

---

## 4. Conventions worth knowing

CINDER uses SI values internally:

```text
metres, seconds, radians, kilograms, newtons, newton-metres
```

The main CVT convention is:

```text
ratio R = secondary effective radius / primary effective radius
R > 1 means reduction / low ratio
increasing global shift closes the primary, increases primary radius, and lowers R
positive local clamping force closes the pulley it is mounted on
```

Use the unit-bearing output names directly:

```text
shift_position_m
shaft_speed_rad_per_s
secondary_torque_Nm
total_clamping_force_N
ratio_change_per_mm_shift
```

For display, convert only at the edge of your app or script:

```python
rpm = shaft_speed_rad_per_s * 60.0 / (2.0 * 3.141592653589793)
mm = shift_position_m * 1e3
```

---

## 5. Edit and save an assembly design

Assembly documents are plain JSON and intentionally contain only the CVT:

```text
belt and pulley geometry
contact friction coefficient
inertias
input pulley mechanisms
output pulley mechanisms and helix geometry
```

They do **not** contain engine curves, vehicle data, road profiles, a scenario, or solver settings. Those belong to the simulation case, because the same CVT can be run against different engines, vehicles, roads, or dynos.

To save an assembly after editing it in Python:

```python
from cinder.contracts import encode_assembly_document

updated_payload = encode_assembly_document(assembly)
Path("my_cvt_assembly.json").write_text(
    json.dumps(updated_payload, indent=2),
    encoding="utf-8",
)
```

If a document contains a malformed field or an unsupported custom mechanism, `decode_assembly_document(...)` raises a clear error instead of silently changing the physics.

---

## 6. Static geometry study

A geometry study needs only belt/shift geometry. It does not need an engine, vehicle, contact solve, or time integration.

### Case A: start from endpoint radii

Use this when you know the belt and the small-primary / large-secondary endpoint.

```python
from cinder.studies.geometry import (
    EndpointRadiiDesignRequest,
    GeometryDesignContext,
    evaluate_geometry_feasibility,
    sample_geometry_path,
    solve_geometry_from_endpoint_radii,
    summarize_geometry_design,
)

spec = assembly.geometry.spec
context = GeometryDesignContext(
    belt=spec.belt,
    belt_outer_length=spec.belt_outer_length,
    sheave_half_angle=spec.sheave_half_angle,
    deadzone_shift=spec.deadzone_shift,
    max_shift=spec.max_shift,
)

design = solve_geometry_from_endpoint_radii(
    EndpointRadiiDesignRequest(
        context=context,
        primary_outer_radius_at_zero_shift=spec.primary_outer_radius_at_zero_shift,
        secondary_outer_radius_at_zero_shift=spec.secondary_outer_radius_at_zero_shift,
    )
)

summary = summarize_geometry_design(design)
path = sample_geometry_path(design, sample_count=201)
feasibility = evaluate_geometry_feasibility(design)

print(summary.center_distance)
print(summary.maximum_ratio, summary.minimum_ratio, summary.ratio_span)
print(path.ratio_change_per_mm_shift)
print(feasibility.issues)
```

### Case B: start from target ratios

Use this when you know the belt and want a requested ratio range:

```python
from cinder.studies.geometry import (
    TargetRatioDesignRequest,
    solve_geometry_from_target_ratios,
)

design = solve_geometry_from_target_ratios(
    TargetRatioDesignRequest(
        context=context,
        maximum_ratio=4.9,
        minimum_ratio=1.13,
    )
)
```

With the current fixed active shift-travel convention, Case B returns one compatible geometry or raises `GeometryDesignInfeasibleError`.

### Geometry fields for plots

The path above is enough for line plots such as ratio vs shift or wrap angle vs shift. For the radius-plane and 3D sensitivity plots, call the fields separately:

```python
import numpy as np
from cinder.studies.geometry import (
    evaluate_radius_plane,
    evaluate_ratio_sensitivity_field,
)

primary_axis = np.linspace(
    summary.primary_outer_radius_min,
    summary.primary_outer_radius_max,
    100,
)
secondary_axis = np.linspace(
    summary.secondary_outer_radius_min,
    summary.secondary_outer_radius_max,
    100,
)

plane = evaluate_radius_plane(
    belt=spec.belt,
    center_distance=design.center_distance,
    primary_outer_radius=primary_axis,
    secondary_outer_radius=secondary_axis,
)

sensitivity = evaluate_ratio_sensitivity_field(
    belt=spec.belt,
    center_distance=design.center_distance,
    sheave_half_angle=spec.sheave_half_angle,
    primary_outer_radius=primary_axis,
    secondary_outer_radius=secondary_axis,
)
```

The returned arrays are raw numeric data. Plotting is up to your script or frontend.

---

## 7. Static actuator clamping-force study

This study samples one existing pulley actuator from one CVT assembly. It needs only:

```text
one assembly
one selected pulley
one frozen operating point
one or two quantities to sweep
```

It does not need an engine, vehicle, contact solve, or transient run.

### Primary-style example: shift position × shaft speed

```python
import numpy as np
from cinder.studies.actuation import (
    ActuationOperatingPoint,
    ActuationResponseAxis,
    ActuationStateCoordinate,
    PulleyClampingForceStudyRequest,
    PulleyLocation,
    sample_pulley_clamping_force,
)

field = sample_pulley_clamping_force(
    PulleyClampingForceStudyRequest(
        cvt=assembly,
        pulley=PulleyLocation.INPUT,
        point=ActuationOperatingPoint(
            shift_position=spec.deadzone_shift,
        ),
        axes=(
            ActuationResponseAxis(
                ActuationStateCoordinate.SHIFT_POSITION,
                np.linspace(spec.deadzone_shift, spec.max_shift, 81),
            ),
            ActuationResponseAxis(
                ActuationStateCoordinate.SHAFT_SPEED,
                np.linspace(0.0, 6000.0 * 2.0 * np.pi / 60.0, 81),
            ),
        ),
    )
)

print(field.column_keys)
total_force = field.column("total_clamping_force_N")
```

### Secondary-style example: shift position × reacted secondary torque

Torque-reactive mechanisms need a closure unknown as an axis or fixed value. Use the real `ClosureUnknown` enum rather than a text label:

```python
from cinder.model.cvt.closure import ClosureUnknown
from cinder.studies.actuation import PulleyLocation

field = sample_pulley_clamping_force(
    PulleyClampingForceStudyRequest(
        cvt=assembly,
        pulley=PulleyLocation.OUTPUT,
        point=ActuationOperatingPoint(
            shift_position=spec.deadzone_shift,
        ),
        axes=(
            ActuationResponseAxis(
                ActuationStateCoordinate.SHIFT_POSITION,
                np.linspace(spec.deadzone_shift, spec.max_shift, 81),
            ),
            ActuationResponseAxis(
                ClosureUnknown.SECONDARY_TORQUE,
                np.linspace(0.0, 140.0, 81),
            ),
        ),
    )
)

for key in field.column_keys:
    print(key)
```

The result tells you what to plot. Typical returned columns are:

```text
shift_position_m
shaft_speed_rad_per_s
secondary_torque_Nm
centrifugal_ramp_clamping_force_N
axial_spring_clamping_force_N
helix_reacted_shaft_torque_clamping_force_N
total_clamping_force_N
total_gain_secondary_torque_N_per_Nm
```

Do not reconstruct the total yourself in application logic unless you are performing a test. Treat the returned columns as the authoritative study result.

---

## 8. Run a transient simulation

A simulation adds the non-CVT parts:

```text
input boundary, such as an engine torque curve
output boundary, such as a fixed dyno load or vehicle/final-drive model
scenario with initial state and time span
operating configuration with traction and solver settings
```

Here is a small CINDER-only fixed-load example. It is not meant to be a tuned
vehicle launch; it just shows the construction pattern without relying on any
project-internal tooling.

```python
import numpy as np

from cinder.execution.hybrid import (
    CVTOperatingSystemConfig,
    CVTShiftOperatingLimits,
    EngagedContactSolveSettings,
    LambdaSearchBounds,
)
from cinder.model.boundaries.input.engine import (
    EngineTorquePoint,
    FullThrottleTorqueCurve,
    TorqueCurveSpec,
)
from cinder.model.boundaries.output import FixedOutputLoad
from cinder.model.cvt.contact import ContactTractionLaw, ContactTractionUtilization
from cinder.model.system import CVTDynamicState, CVTSimulationCase, OperatingScenario

engine = FullThrottleTorqueCurve(
    TorqueCurveSpec(
        points=(
            EngineTorquePoint(angular_speed=1500.0 * 2.0 * np.pi / 60.0, torque=0.0),
            EngineTorquePoint(angular_speed=3000.0 * 2.0 * np.pi / 60.0, torque=18.0),
            EngineTorquePoint(angular_speed=5000.0 * 2.0 * np.pi / 60.0, torque=18.0),
            EngineTorquePoint(angular_speed=6500.0 * 2.0 * np.pi / 60.0, torque=0.0),
        ),
        low_speed_braking_torque=-2.0,
        low_speed_braking_peak_speed=700.0 * 2.0 * np.pi / 60.0,
        high_speed_braking_torque=-5.0,
        high_speed_braking_transition_width=500.0 * 2.0 * np.pi / 60.0,
    )
)

scenario = OperatingScenario(
    time_span=(0.0, 2.0),
    initial_state=CVTDynamicState(
        primary_angular_speed=1800.0 * 2.0 * np.pi / 60.0,
        secondary_angular_speed=0.0,
        belt_speed=0.0,
        shift_position=0.0,
        shift_speed=0.0,
        secondary_shaft_angle=0.0,
    ),
)

case = CVTSimulationCase(
    cvt=assembly,
    input_boundary=engine,
    output_boundary=FixedOutputLoad(external_torque=-5.0, added_rotational_inertia=0.05),
    scenario=scenario,
)

configuration = CVTOperatingSystemConfig(
    traction_law=ContactTractionLaw.symmetric(
        primary_static_lambda_limit=0.65,
        secondary_static_lambda_limit=0.65,
        primary_kinetic_lambda_magnitude=0.55,
        secondary_kinetic_lambda_magnitude=0.55,
    ),
    solve_settings=EngagedContactSolveSettings(
        lambda_search_bounds=LambdaSearchBounds.symmetric(
            primary_half_width=3.0,
            secondary_half_width=3.0,
        ),
        initial_guess=ContactTractionUtilization(
            primary_lambda=0.0,
            secondary_lambda=0.0,
        ),
        maximum_closure_condition_number=1.0e8,
    ),
    operating_limits=CVTShiftOperatingLimits.from_geometry_spec(assembly.geometry.spec),
)

system = configuration.build(case)
result = system.run(
    time_span=case.scenario.time_span,
    initial_state=case.scenario.initial_state,
)
```

`system.run(...)` returns a chart-ready report on a **10 ms grid by default**.
The solver itself still takes adaptive internal steps.

Useful result entry points:

```python
result.segments       # reported segments, each with time and named signals
result.transitions    # exact hybrid event/reset records
result.trace          # raw adaptive solver trace
result.summary        # compact duration/transition/final-state summary
```

Read a report signal by key:

```python
for segment in result.segments:
    rpm = segment.signal("state.primary_angular_speed").values * 60.0 / (2.0 * np.pi)
    ratio = segment.signal("geometry.effective_ratio_secondary_over_primary").values
```

Request another report spacing when needed:

```python
from cinder.results import ReportingGrid, ReportingSettings

result = system.run(
    time_span=(0.0, 30.0),
    initial_state=case.scenario.initial_state,
    reporting_settings=ReportingSettings(
        grid=ReportingGrid.uniform_time_step(0.02),
    ),
)
```

For the lean raw solver result only:

```python
trace = system.integrate_trace(
    time_span=(0.0, 30.0),
    initial_state=case.scenario.initial_state,
)
```

---

## 9. Make results JSON-safe

For a backend or saved artifact, project results through `cinder.contracts` rather than writing NumPy objects directly:

```python
import json
from cinder.contracts import (
    project_clamping_force_response,
    project_geometry_path,
    project_simulation_result,
    summarize_simulation,
)

geometry_payload = project_geometry_path(path)
actuation_payload = project_clamping_force_response(field)
simulation_payload = project_simulation_result(result)
metrics = summarize_simulation(result)

Path("simulation_result.json").write_text(
    json.dumps(simulation_payload, indent=2),
    encoding="utf-8",
)
```

Projected study fields use self-describing columns:

```text
kind
shape
axis_keys
columns[]
  key
  label
  unit
  description
  values
```

That is enough for a frontend to choose its own tables and plots without knowing CINDER’s internal classes.

---

## 10. Included runnable example

This repository includes one small CINDER-only smoke example:

```powershell
python examples/quickstart.py
```

It follows this path:

```text
assembly JSON
→ decode
→ validate
→ geometry study
→ actuator study
→ JSON-safe projection
```

Project-specific launch scripts, plotting dashboards, and tuning sweeps can use
these same APIs, but they stay outside `src/cinder` and outside the public
installation contract.
