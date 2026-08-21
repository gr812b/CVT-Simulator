"""Contracts shared by mounted CINDER pulley-actuation force laws.

A force law is never told which named pulley hosts it. The host pulley
supplies its local motion, optional kinematic
coupling, and closure-column projection through :class:`PulleyActuationContext`.

The runtime path consumes only affine relations.  Rich named contribution
objects are intentionally created only when :meth:`PulleyActuator.inspect`
is requested after an integration.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from math import isclose, isfinite
from typing import Protocol, runtime_checkable

from cinder.model.cvt.closure import (
    AffineClosureScalar,
    ClosureUnknown,
    ClosureUnknowns,
)
from cinder.model.cvt.profiles import HelixShiftKinematics


@dataclass(frozen=True, slots=True)
class PulleyElementContribution:
    """Affine mechanical contribution from one pulley-mounted element.

    ``closing_force`` is positive in the local pulley-closing direction.
    ``shaft_torque`` is positive in the positive rotation direction of the
    pulley shaft.  Simple axial actuators only populate ``closing_force``;
    dynamic couplings such as a helix may populate both.
    """

    closing_force: AffineClosureScalar = field(default_factory=AffineClosureScalar.zero)
    shaft_torque: AffineClosureScalar = field(default_factory=AffineClosureScalar.zero)

    def __post_init__(self) -> None:
        if not isinstance(self.closing_force, AffineClosureScalar):
            raise TypeError("closing_force must be an AffineClosureScalar.")
        if not isinstance(self.shaft_torque, AffineClosureScalar):
            raise TypeError("shaft_torque must be an AffineClosureScalar.")

    @classmethod
    def zero(cls) -> "PulleyElementContribution":
        return cls()

    @classmethod
    def from_closing_force(
        cls, relation: AffineClosureScalar
    ) -> "PulleyElementContribution":
        return cls(closing_force=relation)

    def __add__(
        self, other: "PulleyElementContribution"
    ) -> "PulleyElementContribution":
        if not isinstance(other, PulleyElementContribution):
            return NotImplemented
        return PulleyElementContribution(
            closing_force=self.closing_force + other.closing_force,
            shaft_torque=self.shaft_torque + other.shaft_torque,
        )


class PulleyElement(Protocol):
    """One mounted component that can affect a pulley force and/or shaft torque."""

    def evaluate_element(
        self, context: "PulleyActuationContext"
    ) -> PulleyElementContribution:
        """Return the element contribution at one frozen RHS state."""


@dataclass(frozen=True, slots=True)
class PulleyClosureChannels:
    """Closure unknowns belonging to one mounted pulley shaft."""

    shaft_angular_acceleration: ClosureUnknown
    shaft_torque: ClosureUnknown
    normal_resultant: ClosureUnknown

    @classmethod
    def primary(cls) -> "PulleyClosureChannels":
        return cls(
            shaft_angular_acceleration=ClosureUnknown.PRIMARY_ANGULAR_ACCELERATION,
            shaft_torque=ClosureUnknown.PRIMARY_TORQUE,
            normal_resultant=ClosureUnknown.PRIMARY_NORMAL_RESULTANT,
        )

    @classmethod
    def secondary(cls) -> "PulleyClosureChannels":
        return cls(
            shaft_angular_acceleration=ClosureUnknown.SECONDARY_ANGULAR_ACCELERATION,
            shaft_torque=ClosureUnknown.SECONDARY_TORQUE,
            normal_resultant=ClosureUnknown.SECONDARY_NORMAL_RESULTANT,
        )


@dataclass(frozen=True, slots=True)
class HelicalCouplingState:
    """Live local state supplied by a pulley-mounted helical coupling."""

    kinematics: HelixShiftKinematics
    opening_per_axial_position: float = -1.0
    opening_offset: float = 0.0

    def __post_init__(self) -> None:
        if not isinstance(self.kinematics, HelixShiftKinematics):
            raise TypeError("kinematics must be a HelixShiftKinematics instance.")
        if (
            not isfinite(self.opening_per_axial_position)
            or self.opening_per_axial_position == 0.0
        ):
            raise ValueError("opening_per_axial_position must be finite and nonzero.")
        if not isfinite(self.opening_offset):
            raise ValueError("opening_offset must be finite.")

    @property
    def dtheta_daxial(self) -> float:
        return self.kinematics.dtheta_dopening * self.opening_per_axial_position

    @property
    def d2theta_daxial2(self) -> float:
        return self.kinematics.d2theta_dopening2 * self.opening_per_axial_position**2

    def validate_local_position(self, axial_position: float) -> None:
        if not isfinite(axial_position):
            raise ValueError("axial_position must be finite.")
        expected_opening = (
            self.opening_offset + self.opening_per_axial_position * axial_position
        )
        if not isclose(
            self.kinematics.opening_travel,
            expected_opening,
            rel_tol=1.0e-12,
            abs_tol=1.0e-12,
        ):
            raise ValueError(
                "helical coupling profile coordinate does not match its local axial mapping."
            )


@dataclass(frozen=True, slots=True)
class PulleyActuationContext:
    """All local information available to a mounted actuator at one RHS point.

    ``time`` is the physical evaluation time and is required for every
    context, even when the installed actuator is time independent. Basic laws
    such as springs and centrifugal ramps consume only the local
    position/speed fields. A helical torque-reaction law additionally consumes
    the host closure channels and :attr:`helical_coupling`.
    """

    time: float
    axial_position: float
    axial_speed: float
    shaft_speed: float
    shift_speed: float = 0.0
    closure_channels: PulleyClosureChannels | None = None
    helical_coupling: HelicalCouplingState | None = None
    movable_member_rotational_inertia: float | None = None

    def __post_init__(self) -> None:
        for name, value in (
            ("time", self.time),
            ("axial_position", self.axial_position),
            ("axial_speed", self.axial_speed),
            ("shaft_speed", self.shaft_speed),
            ("shift_speed", self.shift_speed),
        ):
            if not isfinite(value):
                raise ValueError(f"{name} must be finite.")
        if self.closure_channels is not None and not isinstance(
            self.closure_channels, PulleyClosureChannels
        ):
            raise TypeError("closure_channels must be a PulleyClosureChannels or None.")
        if self.helical_coupling is not None:
            if not isinstance(self.helical_coupling, HelicalCouplingState):
                raise TypeError(
                    "helical_coupling must be a HelicalCouplingState or None."
                )
            self.helical_coupling.validate_local_position(self.axial_position)
        if self.movable_member_rotational_inertia is not None and (
            not isfinite(self.movable_member_rotational_inertia)
            or self.movable_member_rotational_inertia < 0.0
        ):
            raise ValueError(
                "movable_member_rotational_inertia must be finite and non-negative."
            )


@dataclass(frozen=True, slots=True)
class ActuationContribution:
    """One named affine term exposed only by the post-integration inspect path."""

    key: str
    label: str
    relation: AffineClosureScalar

    def __post_init__(self) -> None:
        if not self.key or not self.key.strip():
            raise ValueError("ActuationContribution.key must be non-empty.")
        if not self.label or not self.label.strip():
            raise ValueError("ActuationContribution.label must be non-empty.")
        if not isinstance(self.relation, AffineClosureScalar):
            raise TypeError("relation must be an AffineClosureScalar instance.")

    def resolve(self, unknowns: ClosureUnknowns) -> float:
        """Resolve this named affine contribution at one closure solution."""

        return self.relation.evaluate(unknowns)


@dataclass(frozen=True, slots=True)
class ActuatorInspection:
    """Named local-force decomposition for one mounted actuator.

    ``total_relation`` is exactly the relation used by the RHS.  The
    contribution relations sum to that total.  This object is deliberately not
    produced by :meth:`PulleyActuator.evaluate_relation`.
    """

    total_relation: AffineClosureScalar
    contributions: tuple[ActuationContribution, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.total_relation, AffineClosureScalar):
            raise TypeError("total_relation must be an AffineClosureScalar instance.")
        if not self.contributions:
            raise ValueError("ActuatorInspection requires at least one contribution.")
        keys = tuple(item.key for item in self.contributions)
        if len(set(keys)) != len(keys):
            raise ValueError("ActuatorInspection contribution keys must be unique.")
        if not all(
            isinstance(item, ActuationContribution) for item in self.contributions
        ):
            raise TypeError("contributions must contain ActuationContribution values.")

    def resolve_total(self, unknowns: ClosureUnknowns) -> float:
        return self.total_relation.evaluate(unknowns)

    def resolve_contributions(self, unknowns: ClosureUnknowns) -> dict[str, float]:
        return {item.key: item.resolve(unknowns) for item in self.contributions}


class AxialForceLaw(Protocol):
    """One composable local axial-force law."""

    def evaluate(self, context: PulleyActuationContext) -> AffineClosureScalar:
        """Return one affine local axial-force contribution."""


@runtime_checkable
class InspectableAxialForceLaw(AxialForceLaw, Protocol):
    """Optional rich decomposition contract used outside the RHS hot path."""

    def inspect(
        self, context: PulleyActuationContext
    ) -> tuple[ActuationContribution, ...]:
        """Return named affine contributions that sum to :meth:`evaluate`."""
