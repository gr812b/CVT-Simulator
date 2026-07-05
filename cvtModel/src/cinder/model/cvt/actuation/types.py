"""Contracts shared by mounted CINDER pulley-actuation force laws.

A force law is never told whether it is installed on the input or output
pulley.  The host pulley supplies its local motion, optional kinematic
coupling, and closure-column projection through :class:`PulleyActuationContext`.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import isclose, isfinite
from typing import Protocol

from cinder.model.cvt.closure import (
    AffineClosureScalar,
    ClosureUnknown,
)
from cinder.model.cvt.profiles import HelixShiftKinematics


@dataclass(frozen=True, slots=True)
class PulleyClosureChannels:
    """Closure unknowns belonging to one mounted pulley shaft."""

    shaft_angular_acceleration: ClosureUnknown
    shaft_torque: ClosureUnknown
    normal_resultant: ClosureUnknown

    @classmethod
    def input_pulley(cls) -> "PulleyClosureChannels":
        return cls(
            shaft_angular_acceleration=ClosureUnknown.PRIMARY_ANGULAR_ACCELERATION,
            shaft_torque=ClosureUnknown.PRIMARY_TORQUE,
            normal_resultant=ClosureUnknown.PRIMARY_NORMAL_RESULTANT,
        )

    @classmethod
    def output_pulley(cls) -> "PulleyClosureChannels":
        return cls(
            shaft_angular_acceleration=ClosureUnknown.SECONDARY_ANGULAR_ACCELERATION,
            shaft_torque=ClosureUnknown.SECONDARY_TORQUE,
            normal_resultant=ClosureUnknown.SECONDARY_NORMAL_RESULTANT,
        )


@dataclass(frozen=True, slots=True)
class HelicalCouplingState:
    """Live local state supplied by a pulley-mounted helical coupling."""

    kinematics: HelixShiftKinematics
    opening_per_axial_position: float
    opening_offset: float = 0.0

    def __post_init__(self) -> None:
        if not isinstance(self.kinematics, HelixShiftKinematics):
            raise TypeError("kinematics must be a HelixShiftKinematics instance.")
        if (
            not isfinite(self.opening_per_axial_position)
            or self.opening_per_axial_position == 0.0
        ):
            raise ValueError("opening_per_axial_position must be finite and non-zero.")
        if not isfinite(self.opening_offset):
            raise ValueError("opening_offset must be finite.")

    def validate_local_position(self, axial_position: float) -> None:
        if not isfinite(axial_position):
            raise ValueError("axial_position must be finite.")
        expected_opening = self.opening_offset + (
            self.opening_per_axial_position * axial_position
        )
        if not isclose(
            self.kinematics.opening_travel,
            expected_opening,
            rel_tol=1.0e-12,
            abs_tol=1.0e-12,
        ):
            raise ValueError(
                "helical coupling opening travel must match the host local coordinate."
            )


@dataclass(frozen=True, slots=True)
class PulleyActuationContext:
    """All local information available to a mounted actuator at one RHS point.

    Basic laws such as springs and centrifugal ramps consume only the local
    position/speed fields.  A helical torque-reaction law additionally consumes
    the host closure channels and :attr:`helical_coupling`.
    """

    axial_position: float
    axial_speed: float
    shaft_speed: float
    shift_speed: float = 0.0
    closure_channels: PulleyClosureChannels | None = None
    helical_coupling: HelicalCouplingState | None = None
    movable_member_rotational_inertia: float | None = None

    def __post_init__(self) -> None:
        for name, value in (
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
                raise TypeError("helical_coupling must be a HelicalCouplingState or None.")
            self.helical_coupling.validate_local_position(self.axial_position)
        if self.movable_member_rotational_inertia is not None and (
            not isfinite(self.movable_member_rotational_inertia)
            or self.movable_member_rotational_inertia < 0.0
        ):
            raise ValueError(
                "movable_member_rotational_inertia must be finite and non-negative."
            )


class AxialForceLaw(Protocol):
    """One composable local axial-force law."""

    def evaluate(self, context: PulleyActuationContext) -> AffineClosureScalar:
        """Return one affine local axial-force contribution."""
