"""Shared physical relative-motion definitions for every engaged contact mode.

The reduced wrap contact uses one representative tangential surface speed per
pulley. When a helical movable sheave rotates relative to its shaft, that
representative speed preserves the power carried by the same movable/fixed
face torque split already present in the actuator model.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from math import isfinite
from typing import TYPE_CHECKING, Iterable

import numpy as np
from numpy.typing import NDArray

from .tolerances import ContactKinematicTolerances

if TYPE_CHECKING:
    from cinder.model.cvt.closure import ClosureUnknowns
    from cinder.model.system.evaluator import DynamicsSnapshot


class ContactInterface(str, Enum):
    """The two belt--pulley contact interfaces."""

    PRIMARY = "primary"
    SECONDARY = "secondary"


class SlipDirection(str, Enum):
    """Direction of belt motion relative to the represented pulley surface."""

    BELT_LEADS_PULLEY = "belt_leads_pulley"
    PULLEY_LEADS_BELT = "pulley_leads_belt"
    INDETERMINATE = "indeterminate"


@dataclass(frozen=True, slots=True)
class ContactRelativeMotion:
    """Velocity- and acceleration-level relative motion at both interfaces.

    The reduced contact compares belt transport against one representative
    contact angular speed ``omega_bar_j``:

        v_rel,j = v_b - r_j omega_bar_j,
        a_rel,j = v_b_dot - r_j omega_bar_dot_j
                  - r_j' s_dot omega_bar_j.

    With no differential sheave rotation, ``omega_bar_j = omega_j``. If a
    helical movable member carries fraction ``f`` of the belt torque, preserving
    the power of the two face-torque paths gives

        omega_bar_j = omega_j + f theta_dot_j.

    A sticking interface imposes ``a_rel,j = 0``. A slipping interface leaves
    that residual unconstrained and uses ``v_rel,j`` (or, at zero speed,
    ``a_rel,j``) for direction and re-stick logic.
    """

    primary_relative_speed: float
    secondary_relative_speed: float
    primary_relative_acceleration: float
    secondary_relative_acceleration: float

    def __post_init__(self) -> None:
        for name, value in (
            ("primary_relative_speed", self.primary_relative_speed),
            ("secondary_relative_speed", self.secondary_relative_speed),
            ("primary_relative_acceleration", self.primary_relative_acceleration),
            ("secondary_relative_acceleration", self.secondary_relative_acceleration),
        ):
            if not isfinite(value):
                raise ValueError(f"{name} must be finite.")

    def relative_speed_at(self, interface: ContactInterface) -> float:
        if interface is ContactInterface.PRIMARY:
            return self.primary_relative_speed
        if interface is ContactInterface.SECONDARY:
            return self.secondary_relative_speed
        raise ValueError(f"Unsupported contact interface: {interface!r}.")

    def relative_acceleration_at(self, interface: ContactInterface) -> float:
        if interface is ContactInterface.PRIMARY:
            return self.primary_relative_acceleration
        if interface is ContactInterface.SECONDARY:
            return self.secondary_relative_acceleration
        raise ValueError(f"Unsupported contact interface: {interface!r}.")

    def acceleration_residual_vector(
        self,
        interfaces: Iterable[ContactInterface],
    ) -> NDArray[np.float64]:
        """Return stick residuals in the supplied interface order."""

        values = np.asarray(
            [self.relative_acceleration_at(interface) for interface in interfaces],
            dtype=float,
        )
        if values.ndim != 1 or values.size == 0:
            raise ValueError("interfaces must contain at least one contact interface.")
        values.setflags(write=False)
        return values

    @property
    def both_acceleration_residuals(self) -> NDArray[np.float64]:
        """Return ``[a_rel,p, a_rel,s]`` in canonical interface order."""

        return self.acceleration_residual_vector(
            (ContactInterface.PRIMARY, ContactInterface.SECONDARY)
        )

    def is_stick_compatible_at(
        self,
        interface: ContactInterface,
        *,
        tolerances: ContactKinematicTolerances,
    ) -> bool:
        return (
            abs(self.relative_acceleration_at(interface))
            <= tolerances.stick_acceleration_tolerance
        )

    def are_stick_compatible(
        self,
        interfaces: Iterable[ContactInterface],
        *,
        tolerances: ContactKinematicTolerances,
    ) -> bool:
        ordered = tuple(interfaces)
        if not ordered:
            raise ValueError("interfaces must contain at least one contact interface.")
        return all(
            self.is_stick_compatible_at(interface, tolerances=tolerances)
            for interface in ordered
        )

    def slip_direction_at(
        self,
        interface: ContactInterface,
        *,
        tolerances: ContactKinematicTolerances,
    ) -> SlipDirection:
        return infer_slip_direction(
            relative_speed=self.relative_speed_at(interface),
            relative_acceleration=self.relative_acceleration_at(interface),
            tolerances=tolerances,
        )


@dataclass(frozen=True, slots=True)
class _RepresentativeAngularMotion:
    speed: float
    acceleration: float
    movable_torque_fraction: float
    helix_speed_per_shift_speed: float


@dataclass(frozen=True, slots=True)
class _RepresentativeContactCoefficients:
    movable_torque_fraction: float
    dtheta_ds_weighted: float
    d2theta_ds2_weighted: float


def evaluate_contact_relative_speed(
    *,
    snapshot: "DynamicsSnapshot",
    interface: ContactInterface,
) -> float:
    """Return velocity-level relative motion for one reduced wrap contact.

    This helper is intentionally independent of the closure unknowns so hybrid
    initial-regime classification and zero-speed event logic use the exact same
    representative contact speed as the continuous stick/slip closure.
    """

    state = snapshot.state
    if interface is ContactInterface.PRIMARY:
        radius = snapshot.geometry.primary.effective
    elif interface is ContactInterface.SECONDARY:
        radius = snapshot.geometry.secondary.effective
    else:  # pragma: no cover
        raise ValueError(f"Unsupported contact interface: {interface!r}.")
    return float(
        state.belt_speed
        - radius * _representative_angular_speed(snapshot=snapshot, interface=interface)
    )


def evaluate_contact_relative_motion(
    *,
    snapshot: "DynamicsSnapshot",
    unknowns: "ClosureUnknowns",
) -> ContactRelativeMotion:
    """Evaluate both reduced contact kinematics from one solved snapshot.

    A torque-reactive helix contributes an axial force gain
    ``f * dtheta/dx`` with respect to the host belt-torque unknown. Multiplying
    that existing gain by ``dx/ds`` recovers ``f * dtheta/ds``. The contact law
    therefore uses exactly the same face-torque fraction as the actuator rather
    than introducing a second independently configured split.
    """

    state = snapshot.state
    geometry = snapshot.geometry

    primary_motion = _representative_angular_motion(
        snapshot=snapshot,
        unknowns=unknowns,
        interface=ContactInterface.PRIMARY,
    )
    secondary_motion = _representative_angular_motion(
        snapshot=snapshot,
        unknowns=unknowns,
        interface=ContactInterface.SECONDARY,
    )

    primary = geometry.primary
    secondary = geometry.secondary
    return ContactRelativeMotion(
        primary_relative_speed=(
            state.belt_speed - primary.effective * primary_motion.speed
        ),
        secondary_relative_speed=(
            state.belt_speed - secondary.effective * secondary_motion.speed
        ),
        primary_relative_acceleration=(
            unknowns.belt_acceleration
            - primary.effective * primary_motion.acceleration
            - primary.d_effective_ds * state.shift_speed * primary_motion.speed
        ),
        secondary_relative_acceleration=(
            unknowns.belt_acceleration
            - secondary.effective * secondary_motion.acceleration
            - secondary.d_effective_ds * state.shift_speed * secondary_motion.speed
        ),
    )


def _representative_angular_speed(
    *,
    snapshot: "DynamicsSnapshot",
    interface: ContactInterface,
) -> float:
    state = snapshot.state
    if interface is ContactInterface.PRIMARY:
        shaft_speed = state.primary_angular_speed
    elif interface is ContactInterface.SECONDARY:
        shaft_speed = state.secondary_angular_speed
    else:  # pragma: no cover
        raise ValueError(f"Unsupported contact interface: {interface!r}.")
    coefficients = _representative_contact_coefficients(
        snapshot=snapshot,
        interface=interface,
    )
    return float(shaft_speed + coefficients.dtheta_ds_weighted * state.shift_speed)


def _representative_angular_motion(
    *,
    snapshot: "DynamicsSnapshot",
    unknowns: "ClosureUnknowns",
    interface: ContactInterface,
) -> _RepresentativeAngularMotion:
    state = snapshot.state

    if interface is ContactInterface.PRIMARY:
        shaft_speed = state.primary_angular_speed
        shaft_acceleration = unknowns.primary_angular_acceleration
    elif interface is ContactInterface.SECONDARY:
        shaft_speed = state.secondary_angular_speed
        shaft_acceleration = unknowns.secondary_angular_acceleration
    else:  # pragma: no cover
        raise ValueError(f"Unsupported contact interface: {interface!r}.")

    coefficients = _representative_contact_coefficients(
        snapshot=snapshot,
        interface=interface,
    )
    representative_speed = (
        shaft_speed + coefficients.dtheta_ds_weighted * state.shift_speed
    )
    representative_acceleration = (
        shaft_acceleration
        + coefficients.dtheta_ds_weighted * unknowns.shift_acceleration
        + coefficients.d2theta_ds2_weighted * state.shift_speed**2
    )

    return _RepresentativeAngularMotion(
        speed=float(representative_speed),
        acceleration=float(representative_acceleration),
        movable_torque_fraction=coefficients.movable_torque_fraction,
        helix_speed_per_shift_speed=coefficients.dtheta_ds_weighted,
    )


def _representative_contact_coefficients(
    *,
    snapshot: "DynamicsSnapshot",
    interface: ContactInterface,
) -> _RepresentativeContactCoefficients:
    if interface is ContactInterface.PRIMARY:
        helix = snapshot.primary_helix
        axial_coordinate = snapshot.geometry.primary_axial_coordinate
        torque_force_gain = snapshot.primary_actuation.gains.primary_torque
    elif interface is ContactInterface.SECONDARY:
        helix = snapshot.secondary_helix
        axial_coordinate = snapshot.geometry.secondary_axial_coordinate
        torque_force_gain = snapshot.secondary_actuation.gains.secondary_torque
    else:  # pragma: no cover
        raise ValueError(f"Unsupported contact interface: {interface!r}.")

    if helix is None:
        return _RepresentativeContactCoefficients(
            movable_torque_fraction=0.0,
            dtheta_ds_weighted=0.0,
            d2theta_ds2_weighted=0.0,
        )

    # HelicalTorqueReactionForce contributes
    #     F_x <- f * tau_belt * dtheta/dx.
    # Its affine torque gain is therefore f*dtheta/dx; multiplying by dx/ds
    # produces the power-equivalent angular shift gain f*dtheta/ds.
    weighted_dtheta_ds = float(torque_force_gain * axial_coordinate.d_value_ds)
    dtheta_ds = float(helix.dtheta_ds)

    scale = max(1.0, abs(weighted_dtheta_ds), abs(dtheta_ds))
    tolerance = 4096.0 * np.finfo(float).eps * scale
    if abs(dtheta_ds) <= tolerance:
        if abs(weighted_dtheta_ds) > tolerance:
            raise RuntimeError(
                "Torque-reactive actuation implies a contact-speed helix term "
                "while dtheta/ds is numerically zero."
            )
        fraction = 0.0
    else:
        fraction = weighted_dtheta_ds / dtheta_ds
        if fraction < -1.0e-10 or fraction > 1.0 + 1.0e-10:
            raise RuntimeError(
                "Inferred movable-member belt-torque fraction lies outside [0, 1]: "
                f"{fraction:.12g}."
            )
        fraction = min(1.0, max(0.0, fraction))

    return _RepresentativeContactCoefficients(
        movable_torque_fraction=float(fraction),
        dtheta_ds_weighted=float(weighted_dtheta_ds),
        d2theta_ds2_weighted=(fraction * float(helix.d2theta_ds2)),
    )


def infer_slip_direction(
    *,
    relative_speed: float,
    relative_acceleration: float,
    tolerances: ContactKinematicTolerances,
) -> SlipDirection:
    """Infer established slip, or only an incipient direction at zero speed."""

    if relative_speed > tolerances.relative_speed_tolerance:
        return SlipDirection.BELT_LEADS_PULLEY
    if relative_speed < -tolerances.relative_speed_tolerance:
        return SlipDirection.PULLEY_LEADS_BELT
    if relative_acceleration > tolerances.relative_acceleration_tolerance:
        return SlipDirection.BELT_LEADS_PULLEY
    if relative_acceleration < -tolerances.relative_acceleration_tolerance:
        return SlipDirection.PULLEY_LEADS_BELT
    return SlipDirection.INDETERMINATE
