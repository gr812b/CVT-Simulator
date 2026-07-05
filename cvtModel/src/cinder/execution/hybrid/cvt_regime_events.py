"""Geometry, engagement, and unilateral-constraint events for CVT regimes.

Event factories encode only boundaries and scalar release indicators that are
physically meaningful for the active operating regime.  They deliberately do
not contain an RHS or duplicate contact mechanics.
"""

from __future__ import annotations

from enum import Enum
from typing import Callable

import numpy as np
from numpy.typing import NDArray

from .cvt_operating_limits import CVTShiftOperatingLimits
from .hybrid import HybridEvent

_BOUNDARY_REARM_TIME_SECONDS = 1.0e-6
_BOUNDARY_REST_POSITION_TOLERANCE = 1.0e-12
_BOUNDARY_REST_SPEED_TOLERANCE = 1.0e-12


class CVTRegimeEvent(str, Enum):
    """Events that change engagement or a unilateral shift constraint."""

    ENGAGEMENT_REACHED = "engagement_reached"
    LOW_RATIO_SEAT_REACHED = "low_ratio_seat_reached"
    LOWER_STOP_REACHED = "lower_stop_reached"
    UPPER_STOP_REACHED = "upper_stop_reached"
    PRIMARY_CLAMP_LOST = "primary_clamp_lost"
    LOW_RATIO_SEAT_RELEASE = "low_ratio_seat_release"
    LOWER_STOP_RELEASE = "lower_stop_release"
    UPPER_STOP_RELEASE = "upper_stop_release"


LowerStopReactionIndicator = Callable[[float, NDArray[np.float64]], float]
LowRatioSeatReactionIndicator = Callable[[float, NDArray[np.float64]], float]
PrimaryClampIndicator = Callable[[float, NDArray[np.float64]], float]
UpperStopReactionIndicator = Callable[[float, NDArray[np.float64]], float]


def build_deadzone_free_boundary_events(
    *,
    limits: CVTShiftOperatingLimits,
) -> tuple[HybridEvent, HybridEvent]:
    """Return the only two geometry boundaries reachable from free deadzone."""

    def engagement_indicator(_time: float, vector: NDArray[np.float64]) -> float:
        displacement = float(vector[3] - limits.engagement_shift)
        shift_speed = float(vector[4])
        # An engaged-to-deadzone transition begins at this boundary while
        # opening. Keep the newly deadzone segment on its valid side until a
        # later genuine closing crossing.
        return displacement - _BOUNDARY_REARM_TIME_SECONDS * max(-shift_speed, 0.0)

    def lower_stop_indicator(_time: float, vector: NDArray[np.float64]) -> float:
        displacement = float(vector[3] - limits.lower_stop_shift)
        shift_speed = float(vector[4])
        if (
            abs(displacement) <= _BOUNDARY_REST_POSITION_TOLERANCE
            and abs(shift_speed) <= _BOUNDARY_REST_SPEED_TOLERANCE
        ):
            return _BOUNDARY_REST_POSITION_TOLERANCE
        return displacement + _BOUNDARY_REARM_TIME_SECONDS * max(shift_speed, 0.0)

    return (
        HybridEvent(
            name=CVTRegimeEvent.ENGAGEMENT_REACHED.value,
            function=engagement_indicator,
            direction=+1.0,
        ),
        HybridEvent(
            name=CVTRegimeEvent.LOWER_STOP_REACHED.value,
            function=lower_stop_indicator,
            direction=-1.0,
        ),
    )


def build_engaged_free_boundary_events(
    *,
    limits: CVTShiftOperatingLimits,
) -> tuple[HybridEvent, HybridEvent]:
    """Return the low-ratio seat and upper-stop arrivals from free engagement.

    Reaching ``s_engage`` is not itself a disengagement decision.  The event
    first enters the engaged low-ratio seat.  That seat then releases to
    deadzone only when the *primary actuator's own* clamp force crosses below
    zero.
    """

    def low_ratio_seat_indicator(_time: float, vector: NDArray[np.float64]) -> float:
        displacement = float(vector[3] - limits.engagement_shift)
        shift_speed = float(vector[4])
        if (
            abs(displacement) <= _BOUNDARY_REST_POSITION_TOLERANCE
            and abs(shift_speed) <= _BOUNDARY_REST_SPEED_TOLERANCE
        ):
            # A low-seat release begins at rest and accelerates inward.
            return _BOUNDARY_REST_POSITION_TOLERANCE
        return displacement + _BOUNDARY_REARM_TIME_SECONDS * max(shift_speed, 0.0)

    def upper_stop_indicator(_time: float, vector: NDArray[np.float64]) -> float:
        displacement = float(limits.upper_stop_shift - vector[3])
        shift_speed = float(vector[4])
        if (
            abs(displacement) <= _BOUNDARY_REST_POSITION_TOLERANCE
            and abs(shift_speed) <= _BOUNDARY_REST_SPEED_TOLERANCE
        ):
            return _BOUNDARY_REST_POSITION_TOLERANCE
        return displacement + _BOUNDARY_REARM_TIME_SECONDS * max(-shift_speed, 0.0)

    return (
        HybridEvent(
            name=CVTRegimeEvent.LOW_RATIO_SEAT_REACHED.value,
            function=low_ratio_seat_indicator,
            direction=-1.0,
        ),
        HybridEvent(
            name=CVTRegimeEvent.UPPER_STOP_REACHED.value,
            function=upper_stop_indicator,
            direction=-1.0,
        ),
    )


def build_low_ratio_seat_events(
    *,
    primary_clamping_force: PrimaryClampIndicator,
    closing_reaction: LowRatioSeatReactionIndicator,
) -> tuple[HybridEvent, HybridEvent]:
    """Return the two distinct exits from an engaged low-ratio seat.

    ``PRIMARY_CLAMP_LOST`` is the engagement/disengagement criterion: the
    primary's own signed actuator force crosses from closing to opening.
    ``LOW_RATIO_SEAT_RELEASE`` instead means the unilateral seat would need to
    pull; its successor is free *engaged* motion, not deadzone.
    """

    return (
        HybridEvent(
            name=CVTRegimeEvent.PRIMARY_CLAMP_LOST.value,
            function=lambda time, vector: float(primary_clamping_force(time, vector)),
            direction=-1.0,
        ),
        HybridEvent(
            name=CVTRegimeEvent.LOW_RATIO_SEAT_RELEASE.value,
            function=lambda time, vector: float(closing_reaction(time, vector)),
            direction=-1.0,
        ),
    )


def build_lower_stop_release_event(
    *,
    closing_reaction: LowerStopReactionIndicator,
) -> HybridEvent:
    """Release the lower mechanical stop when its reaction becomes tensile."""

    return HybridEvent(
        name=CVTRegimeEvent.LOWER_STOP_RELEASE.value,
        function=lambda time, vector: float(closing_reaction(time, vector)),
        direction=-1.0,
    )


def build_upper_stop_release_event(
    *,
    opening_reaction: UpperStopReactionIndicator,
) -> HybridEvent:
    """Release the upper mechanical stop when its reaction becomes tensile."""

    return HybridEvent(
        name=CVTRegimeEvent.UPPER_STOP_RELEASE.value,
        function=lambda time, vector: float(opening_reaction(time, vector)),
        direction=-1.0,
    )
