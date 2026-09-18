"""Release-local mechanical-energy accounting for the CINDER energy study.

This module reads the already-defined mechanics from the installed CINDER
release. It does not alter contact laws, transition rules, or integration
states. A few release-internal inspection hooks are intentionally used because
the total stored-energy inventory is not itself a serialized public result.
The enclosing results directory freezes the exact CINDER version, so those
inspection calls are reproducible.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from typing import Iterable

import numpy as np

from cinder.execution.hybrid.cvt_impact import (
    CVTVelocityTopology,
    kinetic_energy_for_topology,
)
from cinder.execution.hybrid.cvt_regime import CVTEngagementState
from cinder.model.cvt.actuation import AxialSpringForce, HelicalTorqueReactionForce
from cinder.model.cvt.contact import ContactInterface
from cinder.model.system import CVTState


@dataclass(frozen=True, slots=True)
class StoredEnergy:
    kinetic_J: float
    primary_axial_spring_J: float
    secondary_axial_spring_J: float
    primary_torsional_spring_J: float
    secondary_torsional_spring_J: float

    @property
    def potential_J(self) -> float:
        return (
            self.primary_axial_spring_J
            + self.secondary_axial_spring_J
            + self.primary_torsional_spring_J
            + self.secondary_torsional_spring_J
        )

    @property
    def total_J(self) -> float:
        return self.kinetic_J + self.potential_J

    def as_dict(self) -> dict[str, float]:
        return {
            "kinetic_J": self.kinetic_J,
            "primary_axial_spring_J": self.primary_axial_spring_J,
            "secondary_axial_spring_J": self.secondary_axial_spring_J,
            "primary_torsional_spring_J": self.primary_torsional_spring_J,
            "secondary_torsional_spring_J": self.secondary_torsional_spring_J,
            "potential_J": self.potential_J,
            "total_J": self.total_J,
        }


@dataclass(frozen=True, slots=True)
class ContactDissipationPower:
    primary_W: float
    secondary_W: float

    @property
    def total_W(self) -> float:
        return self.primary_W + self.secondary_W


def cvt_mode(mode):
    """Return the CVT sub-mode from a composed or CVT-only mode."""
    return getattr(mode, "cvt", mode)


def topology_for_mode(mode) -> CVTVelocityTopology:
    mode = cvt_mode(mode)
    return (
        CVTVelocityTopology.DEADZONE
        if mode.engagement is CVTEngagementState.DEADZONE
        else CVTVelocityTopology.ENGAGED
    )


def stored_energy(
    *,
    system,
    time: float,
    full_state,
    mode,
    boundaries=None,
) -> StoredEnergy:
    """Return every conservative energy term retained by this study inventory."""

    if boundaries is None:
        boundaries = system._shaft_boundaries(time=time, state=full_state)

    cvt_state = CVTState.from_vector(system.layout.view(full_state, "cvt"))
    topology = topology_for_mode(mode)
    model = system.cvt.model

    kinetic = float(
        kinetic_energy_for_topology(
            model=model,
            state=cvt_state,
            topology=topology,
            shaft_boundaries=boundaries,
        )
    )
    primary_x, secondary_x = local_axial_positions(
        model=model,
        state=cvt_state,
        topology=topology,
    )

    p_axial, p_torsional = actuator_potential(
        model=model,
        side="primary",
        axial_position=primary_x,
    )
    s_axial, s_torsional = actuator_potential(
        model=model,
        side="secondary",
        axial_position=secondary_x,
    )

    result = StoredEnergy(
        kinetic_J=kinetic,
        primary_axial_spring_J=p_axial,
        secondary_axial_spring_J=s_axial,
        primary_torsional_spring_J=p_torsional,
        secondary_torsional_spring_J=s_torsional,
    )
    if not isfinite(result.total_J):
        raise RuntimeError("Stored mechanical energy is not finite.")
    return result


def local_axial_positions(
    *,
    model,
    state: CVTState,
    topology: CVTVelocityTopology,
) -> tuple[float, float]:
    """Return mounted-pulley axial coordinates for potential-energy evaluation."""

    if topology is CVTVelocityTopology.ENGAGED:
        geometry = model.geometry.evaluate_engaged(state.shift_position)
        return (
            float(geometry.primary_axial_coordinate.value),
            float(geometry.secondary_axial_coordinate.value),
        )

    primary = model.geometry.evaluate_deadzone(state.shift_position)
    locked = model.geometry.evaluate_deadzone(model.geometry.spec.deadzone_shift)
    return (
        float(primary.primary_axial_coordinate.value),
        float(locked.secondary_axial_coordinate.value),
    )


def actuator_potential(
    *,
    model,
    side: str,
    axial_position: float,
) -> tuple[float, float]:
    """Return axial-spring and torsional-spring potential on one mounted pulley."""

    if side == "primary":
        actuator = model.primary_actuator
        coupling = model.primary_helical_coupling
    elif side == "secondary":
        actuator = model.secondary_actuator
        coupling = model.secondary_helical_coupling
    else:
        raise ValueError(f"Unknown pulley side {side!r}.")

    axial_energy = 0.0
    torsional_energy = 0.0
    for law in actuator.force_laws:
        if isinstance(law, AxialSpringForce):
            spec = law.spec
            compression = (
                spec.initial_compression
                + spec.compression_per_axial_position * axial_position
            )
            axial_energy += 0.5 * spec.stiffness * compression * compression

        elif isinstance(law, HelicalTorqueReactionForce):
            if coupling is None:
                raise RuntimeError("Helical torque-reaction law exists without a coupling.")
            kinematics = coupling.evaluate_from_local_coordinate(
                axial_position=axial_position,
                d_axial_position_ds=0.0,
                d2_axial_position_ds2=0.0,
            )
            twist = law.spec.initial_twist - kinematics.theta
            torsional_energy += 0.5 * law.spec.torsional_stiffness * twist * twist

    return float(axial_energy), float(torsional_energy)


def kinetic_slip_dissipation_power(
    *,
    system,
    time: float,
    full_state,
    mode,
    boundaries,
    injection_tolerance_W: float = 1.0e-5,
) -> ContactDissipationPower:
    """Return non-negative Coulomb dissipation at interfaces declared sliding."""

    mode = cvt_mode(mode)
    if mode.engagement is CVTEngagementState.DEADZONE:
        return ContactDissipationPower(0.0, 0.0)

    contact = mode.contact_regime
    if contact is None or not contact.mode.slipping_interfaces:
        return ContactDissipationPower(0.0, 0.0)

    physics = system.cvt._evaluate_physics(
        time=time,
        state=system.layout.view(full_state, "cvt"),
        mode=mode,
        shaft_boundaries=boundaries,
    )

    primary = 0.0
    secondary = 0.0
    for interface in contact.mode.slipping_interfaces:
        if interface is ContactInterface.PRIMARY:
            lam = float(physics.traction_utilization.primary_lambda)
            normal = float(physics.normal_at(interface))
            relative_speed = float(physics.relative_motion.relative_speed_at(interface))
        elif interface is ContactInterface.SECONDARY:
            lam = float(physics.traction_utilization.secondary_lambda)
            normal = float(physics.normal_at(interface))
            relative_speed = float(physics.relative_motion.relative_speed_at(interface))
        else:  # pragma: no cover
            raise ValueError(f"Unsupported contact interface {interface!r}.")

        # Contact-pair power is lambda*N*v_rel. Dissipation is its negative.
        dissipated = -lam * normal * relative_speed
        if dissipated < -injection_tolerance_W:
            raise RuntimeError(
                "Kinetic contact injects mechanical energy: "
                f"{dissipated:.9g} W at t={time:.12g} s on {interface.value}."
            )
        dissipated = max(0.0, dissipated)
        if interface is ContactInterface.PRIMARY:
            primary += dissipated
        else:
            secondary += dissipated

    return ContactDissipationPower(float(primary), float(secondary))


def stick_pair_power(
    *,
    system,
    time: float,
    full_state,
    mode,
    boundaries,
) -> tuple[float, float, float, float]:
    """Return signed numerical pair power and |v_rel| at declared sticking contacts.

    Exact sticking has zero relative velocity and therefore zero contact-pair
    power. Any nonzero value measured here is an integration/invariant-drift
    diagnostic; it is not treated as physical static-friction dissipation.
    """

    mode = cvt_mode(mode)
    if mode.engagement is CVTEngagementState.DEADZONE:
        return 0.0, 0.0, 0.0, 0.0

    contact = mode.contact_regime
    if contact is None or not contact.mode.sticking_interfaces:
        return 0.0, 0.0, 0.0, 0.0

    physics = system.cvt._evaluate_physics(
        time=time,
        state=system.layout.view(full_state, "cvt"),
        mode=mode,
        shaft_boundaries=boundaries,
    )

    p_power = s_power = 0.0
    p_vrel = s_vrel = 0.0
    for interface in contact.mode.sticking_interfaces:
        if interface is ContactInterface.PRIMARY:
            lam = float(physics.traction_utilization.primary_lambda)
            normal = float(physics.normal_at(interface))
            rel = float(physics.relative_motion.relative_speed_at(interface))
            p_power += lam * normal * rel
            p_vrel = max(p_vrel, abs(rel))
        elif interface is ContactInterface.SECONDARY:
            lam = float(physics.traction_utilization.secondary_lambda)
            normal = float(physics.normal_at(interface))
            rel = float(physics.relative_motion.relative_speed_at(interface))
            s_power += lam * normal * rel
            s_vrel = max(s_vrel, abs(rel))

    return float(p_power), float(s_power), float(p_vrel), float(s_vrel)


def impact_loss_from_transition(record) -> float:
    metadata = record.transition.metadata
    cvt_meta = metadata.get("cvt", metadata)
    if not isinstance(cvt_meta, dict):
        return 0.0
    return float(cvt_meta.get("impact_dissipated_energy_J", 0.0))


def impact_metadata(record) -> dict | None:
    metadata = record.transition.metadata
    cvt_meta = metadata.get("cvt", metadata)
    if not isinstance(cvt_meta, dict) or "impact_model" not in cvt_meta:
        return None
    return cvt_meta


def segment_times(
    start: float,
    end: float,
    *,
    step: float,
    minimum_intervals: int = 12,
) -> np.ndarray:
    """Return a segment-local grid that resolves even millisecond hybrid segments."""

    if step <= 0.0:
        raise ValueError("step must be positive.")
    if end <= start:
        return np.asarray((start,), dtype=float)
    duration = end - start
    intervals = max(int(np.ceil(duration / step)), minimum_intervals)
    return np.linspace(start, end, intervals + 1, dtype=float)


def cumulative_trapezoid(values: np.ndarray, times: np.ndarray) -> np.ndarray:
    output = np.zeros(values.size, dtype=float)
    if values.size > 1:
        output[1:] = np.cumsum(
            0.5 * (values[:-1] + values[1:]) * np.diff(times)
        )
    return output


def write_csv(path, rows: Iterable[dict]) -> None:
    import csv

    rows = list(rows)
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    fields: list[str] = []
    seen: set[str] = set()
    for row in rows:
        for key in row:
            if key not in seen:
                fields.append(key)
                seen.add(key)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
