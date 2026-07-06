# Static Actuator Clamping Study

This study samples **one actuator on one existing CVT assembly**. It does not
need an engine, vehicle boundary, contact solve, or time integration.

```python
field = sample_pulley_clamping_force(
    PulleyClampingForceStudyRequest(
        cvt=assembly,
        pulley=PulleyLocation.OUTPUT,
        point=ActuationOperatingPoint(
            shift_position=...,            # global CVT shift coordinate [m]
            shaft_speed=...,               # selected-pulley speed [rad/s]
            closure_unknowns=...,          # fixed affine unknown values
        ),
        axes=(
            ActuationResponseAxis(
                ActuationStateCoordinate.SHIFT_POSITION,
                ...,
            ),
            ActuationResponseAxis(
                ClosureUnknown.SECONDARY_TORQUE,
                ...,
            ),
        ),
    )
)
```

`axes` selects one or two real quantities to vary. State quantities use
`ActuationStateCoordinate`; affine quantities use CINDER's existing
`ClosureUnknown` enum directly. Every other value stays fixed at `point`.

The result contains only self-describing numeric columns, for example:

```text
shift_position_m
secondary_torque_Nm
axial_spring_clamping_force_N
helix_torsional_preload_clamping_force_N
helix_reacted_shaft_torque_clamping_force_N
total_clamping_force_N
total_gain_secondary_torque_N_per_Nm
```

The frontend or backend can inspect these columns, choose the axes, and plot
any returned force columns. The study performs no actuator-specific plotting
or force calculations outside the production `PulleyActuator` path.

The repository-level internal tool `launchTools/run_actuation_clamping_study.py` is a smoke-test consumer:
it calls the study, writes raw CSV tables, checks that returned contribution
columns sum to the returned total, and plots only non-constant returned force
columns.
