"""Momentum-consistent velocity projections for CVT hybrid events.

Rigid topology changes and metal-stop impacts can change which physical
velocities are compatible with the reduced four-velocity vector

    u = [omega_p, omega_s, v_b, s_dot].

A scalar ``s_dot <- 0`` reset is not generally momentum-consistent once a
movable sheave has relative helix rotation.  This module instead projects the
pre-event physical velocity field onto the post-event kinematic tangent using
the instantaneous kinetic-energy metric.

For physical velocity maps ``z_- = J_- u_-`` and ``z_+ = J_+ u_+`` with
physical inertia matrix ``W``, the unconstrained plastic capture solves

    (J_+^T W J_+) u_+ = J_+^T W J_- u_-.

Additional post-event velocity constraints (metal stop, belt/secondary lock,
or a sticking belt interface that is intentionally retained through an
impact) are imposed with a KKT solve.  This is the multidimensional form of
the familiar one-DOF ``m_old v_old = m_new v_new`` momentum projection.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from math import isfinite

import numpy as np
from numpy.typing import NDArray

from cinder.model.cvt.actuation import CentrifugalRampForce
from cinder.model.system.evaluator import MechanicalCVTPlant
from cinder.model.system.ports import CVTShaftBoundaryValues
from cinder.model.system.state import CVTState


class CVTVelocityTopology(str, Enum):
    DEADZONE = "deadzone"
    ENGAGED = "engaged"


@dataclass(frozen=True, slots=True)
class CVTImpactProjection:
    """One momentum-consistent plastic velocity reset."""

    successor_state: NDArray[np.float64]
    pre_kinetic_energy: float
    post_kinetic_energy: float
    dissipated_energy: float
    constraint_residual: float
    momentum_residual: float

    def metadata(self) -> dict[str, float | str]:
        return {
            "impact_model": "mass_metric_momentum_projection",
            "impact_pre_kinetic_energy_J": self.pre_kinetic_energy,
            "impact_post_kinetic_energy_J": self.post_kinetic_energy,
            "impact_dissipated_energy_J": self.dissipated_energy,
            "impact_constraint_residual": self.constraint_residual,
            "impact_momentum_residual": self.momentum_residual,
        }


def project_cvt_velocity_topology(
    *,
    model: MechanicalCVTPlant,
    vector: NDArray[np.float64],
    shift_position: float,
    from_topology: CVTVelocityTopology,
    to_topology: CVTVelocityTopology,
    shaft_boundaries: CVTShaftBoundaryValues | None = None,
    stop_shift_velocity: bool = False,
    lock_primary_belt: bool = False,
    lock_secondary_belt: bool = False,
) -> CVTImpactProjection:
    """Project a CVT event onto its physically compatible post-event tangent.

    The position is first placed exactly on ``shift_position``.  Only the four
    generalized velocities ``[omega_p, omega_s, v_b, s_dot]`` are projected.
    External torques/forces are non-impulsive and therefore do not enter the
    instantaneous map; referred shaft inertias supplied by ``shaft_boundaries``
    do enter the kinetic metric.
    """

    if shaft_boundaries is None:
        shaft_boundaries = CVTShaftBoundaryValues.zero()
    if not isinstance(shaft_boundaries, CVTShaftBoundaryValues):
        raise TypeError("shaft_boundaries must be a CVTShaftBoundaryValues instance.")
    if not isinstance(from_topology, CVTVelocityTopology):
        raise TypeError("from_topology must be a CVTVelocityTopology.")
    if not isinstance(to_topology, CVTVelocityTopology):
        raise TypeError("to_topology must be a CVTVelocityTopology.")

    state = CVTState.from_vector(vector)
    boundary_state = CVTState(
        primary_angular_speed=state.primary_angular_speed,
        secondary_angular_speed=state.secondary_angular_speed,
        belt_speed=state.belt_speed,
        shift_position=float(shift_position),
        shift_speed=state.shift_speed,
    )

    rows_minus, weights_minus = _physical_velocity_map(
        model=model,
        state=boundary_state,
        topology=from_topology,
        shaft_boundaries=shaft_boundaries,
    )
    rows_plus, weights_plus = _physical_velocity_map(
        model=model,
        state=boundary_state,
        topology=to_topology,
        shaft_boundaries=shaft_boundaries,
    )
    if rows_minus.shape != rows_plus.shape or not np.allclose(
        weights_minus,
        weights_plus,
        rtol=1.0e-13,
        atol=1.0e-15,
    ):
        raise RuntimeError(
            "Impact physical component basis changed incompatibly across topology."
        )

    weights = weights_plus
    weighted_rows_plus = rows_plus * weights[:, np.newaxis]
    mass_plus = rows_plus.T @ weighted_rows_plus
    cross = rows_plus.T @ (rows_minus * weights[:, np.newaxis])

    velocity_minus = np.asarray(
        (
            state.primary_angular_speed,
            state.secondary_angular_speed,
            state.belt_speed,
            state.shift_speed,
        ),
        dtype=float,
    )
    rhs_momentum = cross @ velocity_minus

    constraints: list[NDArray[np.float64]] = []
    if stop_shift_velocity:
        constraints.append(np.asarray((0.0, 0.0, 0.0, 1.0), dtype=float))

    geometry_plus = _geometry_for_topology(
        model=model,
        shift_position=float(shift_position),
        topology=to_topology,
    )
    if lock_primary_belt:
        constraints.append(
            np.asarray(
                (-geometry_plus.primary.effective, 0.0, 1.0, 0.0),
                dtype=float,
            )
        )
    if lock_secondary_belt:
        constraints.append(
            np.asarray(
                (0.0, -geometry_plus.secondary.effective, 1.0, 0.0),
                dtype=float,
            )
        )

    if constraints:
        constraint_matrix = np.vstack(constraints)
        zero_block = np.zeros(
            (constraint_matrix.shape[0], constraint_matrix.shape[0]), dtype=float
        )
        kkt = np.block(
            [
                [mass_plus, constraint_matrix.T],
                [constraint_matrix, zero_block],
            ]
        )
        rhs = np.concatenate(
            (rhs_momentum, np.zeros(constraint_matrix.shape[0], dtype=float))
        )
        solution = np.linalg.solve(kkt, rhs)
        velocity_plus = solution[:4]
        multipliers = solution[4:]
        constraint_residual = float(np.max(np.abs(constraint_matrix @ velocity_plus)))
        momentum_residual = float(
            np.max(
                np.abs(
                    mass_plus @ velocity_plus
                    + constraint_matrix.T @ multipliers
                    - rhs_momentum
                )
            )
        )
    else:
        velocity_plus = np.linalg.solve(mass_plus, rhs_momentum)
        constraint_residual = 0.0
        momentum_residual = float(
            np.max(np.abs(mass_plus @ velocity_plus - rhs_momentum))
        )

    physical_minus = rows_minus @ velocity_minus
    physical_plus = rows_plus @ velocity_plus
    pre_energy = 0.5 * float(np.dot(weights, physical_minus**2))
    post_energy = 0.5 * float(np.dot(weights, physical_plus**2))
    loss = pre_energy - post_energy

    scale = max(1.0, abs(pre_energy), abs(post_energy))
    tolerance = 4096.0 * np.finfo(float).eps * scale
    if loss < -tolerance:
        raise RuntimeError(
            "Plastic CVT impact projection created kinetic energy: "
            f"delta={-loss:.9g} J."
        )
    if abs(loss) <= tolerance:
        loss = max(0.0, loss)

    successor = np.array(vector, dtype=float, copy=True)
    successor[0] = velocity_plus[0]
    successor[1] = velocity_plus[1]
    successor[2] = velocity_plus[2]
    successor[3] = float(shift_position)
    successor[4] = velocity_plus[3]

    return CVTImpactProjection(
        successor_state=successor,
        pre_kinetic_energy=pre_energy,
        post_kinetic_energy=post_energy,
        dissipated_energy=float(loss),
        constraint_residual=constraint_residual,
        momentum_residual=momentum_residual,
    )


def kinetic_energy_for_topology(
    *,
    model: MechanicalCVTPlant,
    state: CVTState,
    topology: CVTVelocityTopology,
    shaft_boundaries: CVTShaftBoundaryValues | None = None,
) -> float:
    """Return the kinetic energy represented by the current reduced model."""

    if shaft_boundaries is None:
        shaft_boundaries = CVTShaftBoundaryValues.zero()
    rows, weights = _physical_velocity_map(
        model=model,
        state=state,
        topology=topology,
        shaft_boundaries=shaft_boundaries,
    )
    velocity = np.asarray(
        (
            state.primary_angular_speed,
            state.secondary_angular_speed,
            state.belt_speed,
            state.shift_speed,
        ),
        dtype=float,
    )
    physical = rows @ velocity
    return 0.5 * float(np.dot(weights, physical**2))


def _physical_velocity_map(
    *,
    model: MechanicalCVTPlant,
    state: CVTState,
    topology: CVTVelocityTopology,
    shaft_boundaries: CVTShaftBoundaryValues,
) -> tuple[NDArray[np.float64], NDArray[np.float64]]:
    """Return ``(J, Wdiag)`` for all kinetic terms retained by the model.

    Belt axial kinetic energy is intentionally absent because the present
    formulation does not retain belt axial inertia in the dynamics.  The
    point-mass flyweight model contributes its shaft-axis inertia ``m r^2``;
    its future pivot/radial kinetic energy should be added here when that
    geometry is introduced.
    """

    geometry = _geometry_for_topology(
        model=model,
        shift_position=state.shift_position,
        topology=topology,
    )

    primary_coordinate = geometry.primary_axial_coordinate
    secondary_coordinate = geometry.secondary_axial_coordinate

    primary_h = _helix_shift_ratio(
        model=model,
        side="primary",
        coordinate=primary_coordinate,
    )
    secondary_h = _helix_shift_ratio(
        model=model,
        side="secondary",
        coordinate=secondary_coordinate,
    )

    rows: list[tuple[float, float, float, float]] = []
    weights: list[float] = []

    def add(weight: float, row: tuple[float, float, float, float]) -> None:
        if not isfinite(weight) or weight < 0.0:
            raise ValueError(
                "Physical impact inertia weights must be finite/nonnegative."
            )
        if weight == 0.0:
            return
        rows.append(row)
        weights.append(float(weight))

    add(
        model.inertias.primary.fixed_rotating_hardware_inertia
        + shaft_boundaries.primary.equivalent_inertia,
        (1.0, 0.0, 0.0, 0.0),
    )
    add(
        model.inertias.primary.movable_sheave_rotational_inertia,
        (1.0, 0.0, 0.0, primary_h),
    )
    add(
        model.inertias.secondary.fixed_side.total
        + shaft_boundaries.secondary.equivalent_inertia,
        (0.0, 1.0, 0.0, 0.0),
    )
    add(
        model.inertias.secondary.movable_sheave_rotational_inertia,
        (0.0, 1.0, 0.0, secondary_h),
    )
    add(model.inertias.belt.mass, (0.0, 0.0, 1.0, 0.0))
    add(
        model.inertias.axial_translation.primary_moving_sheave_mass,
        (0.0, 0.0, 0.0, primary_coordinate.d_value_ds),
    )
    add(
        model.inertias.axial_translation.secondary_moving_sheave_mass,
        (0.0, 0.0, 0.0, secondary_coordinate.d_value_ds),
    )

    for inertia in _flyweight_shaft_inertias(
        actuator=model.primary_actuator,
        axial_position=primary_coordinate.value,
    ):
        add(inertia, (1.0, 0.0, 0.0, 0.0))
    for inertia in _flyweight_shaft_inertias(
        actuator=model.secondary_actuator,
        axial_position=secondary_coordinate.value,
    ):
        add(inertia, (0.0, 1.0, 0.0, 0.0))

    matrix = np.asarray(rows, dtype=float)
    weight_vector = np.asarray(weights, dtype=float)
    if matrix.ndim != 2 or matrix.shape[1] != 4 or matrix.shape[0] == 0:
        raise RuntimeError("Impact kinetic map is empty or malformed.")
    return matrix, weight_vector


def _geometry_for_topology(
    *,
    model: MechanicalCVTPlant,
    shift_position: float,
    topology: CVTVelocityTopology,
):
    if topology is CVTVelocityTopology.ENGAGED:
        return model.geometry.evaluate_engaged(shift_position)
    if topology is CVTVelocityTopology.DEADZONE:
        # Primary motion remains live through deadzone while the secondary is
        # fixed at the engagement geometry.  At the engagement position the
        # deadzone-side evaluator already returns exactly that locked tangent.
        geometry = model.geometry.evaluate_deadzone(shift_position)
        if shift_position == model.geometry.spec.deadzone_shift:
            return geometry

        locked = model.geometry.evaluate_deadzone(model.geometry.spec.deadzone_shift)
        return type(geometry)(
            shift=geometry.shift,
            primary=geometry.primary,
            secondary=locked.secondary,
            primary_wrap_angle=locked.primary_wrap_angle,
            secondary_wrap_angle=locked.secondary_wrap_angle,
            primary_axial_coordinate=geometry.primary_axial_coordinate,
            secondary_axial_coordinate=locked.secondary_axial_coordinate,
            belt_axial_coordinate=locked.belt_axial_coordinate,
        )
    raise ValueError(f"Unsupported velocity topology: {topology!r}.")


def _helix_shift_ratio(*, model: MechanicalCVTPlant, side: str, coordinate) -> float:
    coupling = (
        model.primary_helical_coupling
        if side == "primary"
        else model.secondary_helical_coupling
    )
    if coupling is None:
        return 0.0
    return float(
        coupling.evaluate_from_local_coordinate(
            axial_position=coordinate.value,
            d_axial_position_ds=coordinate.d_value_ds,
            d2_axial_position_ds2=coordinate.d2_value_ds2,
        ).dtheta_ds
    )


def _flyweight_shaft_inertias(*, actuator, axial_position: float) -> tuple[float, ...]:
    inertias: list[float] = []
    for law in actuator.force_laws:
        if not isinstance(law, CentrifugalRampForce):
            continue
        spec = law.spec
        ramp = spec.radial_displacement_profile.evaluate(axial_position)
        radius = spec.radius_at_zero_position + ramp.value
        inertia = spec.flyweight_mass * radius * radius
        if not isfinite(inertia) or inertia < 0.0:
            raise ValueError("Flyweight impact inertia must be finite/nonnegative.")
        inertias.append(float(inertia))
    return tuple(inertias)
