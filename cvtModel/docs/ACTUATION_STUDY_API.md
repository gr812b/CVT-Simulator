# Static actuator clamping study

The actuation study samples one existing pulley actuator without constructing
an engine, vehicle boundary, belt-contact solve, or time integration.

```python
from cinder.studies import (
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
        pulley=PulleyLocation.SECONDARY,
        point=ActuationOperatingPoint(
            time=0.0,
            shift_position=...,
            shaft_speed=...,
            closure_unknowns=...,
        ),
        axes=(
            ActuationResponseAxis(
                ActuationStateCoordinate.SHIFT_POSITION,
                ...,
            ),
        ),
    )
)
```

`axes` selects one or two physical quantities to vary. All other values remain
fixed at the supplied operating point. Time is explicit even for a nominally
static study so time-dependent actuator laws are sampled deliberately.

The returned field is numeric and self-describing. Depending on the actuator,
columns can include individual clamping-force contributions, total clamping
force, and gains with respect to selected closure unknowns.

The study uses the same production `PulleyActuator` force laws as the dynamic
solver; it does not maintain a second actuator model for plotting.
