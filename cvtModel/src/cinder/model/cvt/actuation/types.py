"""Contracts shared by mounted CINDER pulley-actuation force laws."""

from __future__ import annotations

from dataclasses import dataclass
from math import isclose, isfinite
from typing import Protocol

from cinder.model.cvt.closure import (
    AffineClosureScalar,
    ClosureGains,
    ClosureUnknown,
    ClosureUnknowns,
)
from cinder.model.cvt.profiles import HelixShiftKinematics


@dataclass(frozen=True, slots=True)
class PulleyClosureChannels:
    """Closure columns belonging to one physical pulley shaft.

    This is supplied by the pulley mount/system evaluator, not selected by a
    force law.  It makes a force law reusable on either shaft without strings
    such as ``mounted_pulley='driven'``.
    """

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
class PulleyActuationState:
    """Known local quantities shared by all axial-force laws."""

    axial_position: float
    axial_speed: float
    shaft_speed: float

    def __post_init__(self) -> None:
        for name, value in (
            ("axial_position", self.axial_position),
            ("axial_speed", self.axial_speed),
            ("shaft_speed", self.shaft_speed),
        ):
            if not isfinite(value):
                raise ValueError(f"{name} must be finite.")


@dataclass(frozen=True, slots=True)
class HelicalTorqueReactionState(PulleyActuationState):
    """Additional state for one mounted helical torque-reaction law."""

    global_shift_speed: float
    helix_kinematics: HelixShiftKinematics
    closure_channels: PulleyClosureChannels
    movable_member_inertia: float | None = None
    opening_per_axial_position: float = -1.0
    opening_offset: float = 0.0

    def __post_init__(self) -> None:
        PulleyActuationState.__post_init__(self)
        if not isfinite(self.global_shift_speed):
            raise ValueError("global_shift_speed must be finite.")
        if not isinstance(self.helix_kinematics, HelixShiftKinematics):
            raise TypeError("helix_kinematics must be a HelixShiftKinematics instance.")
        if not isinstance(self.closure_channels, PulleyClosureChannels):
            raise TypeError("closure_channels must be a PulleyClosureChannels instance.")
        if self.movable_member_inertia is not None and (
            not isfinite(self.movable_member_inertia)
            or self.movable_member_inertia < 0.0
        ):
            raise ValueError("movable_member_inertia must be finite and non-negative.")
        if not isfinite(self.opening_per_axial_position) or self.opening_per_axial_position == 0.0:
            raise ValueError("opening_per_axial_position must be finite and non-zero.")
        if not isfinite(self.opening_offset):
            raise ValueError("opening_offset must be finite.")
        expected_opening = self.opening_offset + (
            self.opening_per_axial_position * self.axial_position
        )
        if not isclose(
            self.helix_kinematics.opening_travel,
            expected_opening,
            rel_tol=1e-12,
            abs_tol=1e-12,
        ):
            raise ValueError(
                "helix_kinematics opening_travel must match the mounted local coordinate."
            )


@dataclass(frozen=True, slots=True)
class PulleyActuationResult:
    """The complete local axial-force relation returned by an actuator."""

    relation: AffineClosureScalar

    @property
    def bias_force(self) -> float:
        return self.relation.bias

    @property
    def gains(self) -> ClosureGains:
        return self.relation.gains

    def force(self, unknowns: ClosureUnknowns) -> float:
        return self.relation.evaluate(unknowns)


class AxialForceLaw(Protocol):
    """One composable mechanism contributing local pulley axial force."""

    def evaluate(self, state: PulleyActuationState) -> AffineClosureScalar:
        """Return an affine local axial-force contribution."""
