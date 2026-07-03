"""Geometry and unilateral-constraint events for CVT operating regimes.

These functions intentionally do not contain an RHS.  They encode which
boundaries are meaningful in each regime; the eventual deadzone and
stop-constrained RHS implementations supply any release-tendency callbacks.
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
    """Events that change engagement or unilateral shift constraint."""

    ENGAGEMENT_REACHED = "engagement_reached"
    DISENGAGEMENT_REACHED = "disengagement_reached"
    LOWER_STOP_REACHED = "lower_stop_reached"
    UPPER_STOP_REACHED = "upper_stop_reached"
    LOWER_STOP_RELEASE = "lower_stop_release"
    UPPER_STOP_RELEASE = "upper_stop_release"


LowerStopReactionIndicator = Callable[[float, NDArray[np.float64]], float]
UpperStopReactionIndicator = Callable[[float, NDArray[np.float64]], float]


def build_deadzone_free_boundary_events(
    *,
    limits: CVTShiftOperatingLimits,
) -> tuple[HybridEvent, HybridEvent]:
    """Return the only two boundaries reachable from free deadzone travel.

    Each boundary indicator includes a one-sided re-arm guard.  A segment can
    begin exactly at the engagement boundary immediately after an engaged-to-
    deadzone transition; that state is moving *away* from engagement and must
    not fire an artificial zero-time re-engagement event.  The guard is zero
    during a genuine incoming crossing, so the physical event location remains
    the exact geometry boundary.
    """

    def engagement_indicator(_time: float, vector: NDArray[np.float64]) -> float:
        displacement = float(vector[3] - limits.engagement_shift)
        shift_speed = float(vector[4])
        # At the exact boundary while opening, stay on the deadzone side until
        # a later reversal produces a genuine closing crossing.
        return displacement - _BOUNDARY_REARM_TIME_SECONDS * max(-shift_speed, 0.0)

    def lower_stop_indicator(_time: float, vector: NDArray[np.float64]) -> float:
        displacement = float(vector[3] - limits.lower_stop_shift)
        shift_speed = float(vector[4])
        if (
            abs(displacement) <= _BOUNDARY_REST_POSITION_TOLERANCE
            and abs(shift_speed) <= _BOUNDARY_REST_SPEED_TOLERANCE
        ):
            # A lower-stop release begins at rest but accelerates inward. Keep
            # its newly free segment on the admissible side of the arrival
            # event until it has actually moved away.
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
    """Return the only two geometric boundaries reachable from free engagement.

    The same one-sided guards prevent immediate re-firing after an engagement
    entry or upper-stop release while preserving exact boundary location for
    incoming crossings.
    """

    def disengagement_indicator(_time: float, vector: NDArray[np.float64]) -> float:
        displacement = float(vector[3] - limits.engagement_shift)
        shift_speed = float(vector[4])
        # At the boundary after a closing engagement transition, the next valid
        # disengagement must occur only after motion reverses and crosses down.
        return displacement + _BOUNDARY_REARM_TIME_SECONDS * max(shift_speed, 0.0)

    def upper_stop_indicator(_time: float, vector: NDArray[np.float64]) -> float:
        displacement = float(limits.upper_stop_shift - vector[3])
        shift_speed = float(vector[4])
        if (
            abs(displacement) <= _BOUNDARY_REST_POSITION_TOLERANCE
            and abs(shift_speed) <= _BOUNDARY_REST_SPEED_TOLERANCE
        ):
            # A released upper stop starts at rest and accelerates inward. Keep
            # the free branch armed for a future outward return, not its own
            # start instant.
            return _BOUNDARY_REST_POSITION_TOLERANCE
        return displacement + _BOUNDARY_REARM_TIME_SECONDS * max(-shift_speed, 0.0)

    return (
        HybridEvent(
            name=CVTRegimeEvent.DISENGAGEMENT_REACHED.value,
            function=disengagement_indicator,
            direction=-1.0,
        ),
        HybridEvent(
            name=CVTRegimeEvent.UPPER_STOP_REACHED.value,
            function=upper_stop_indicator,
            direction=-1.0,
        ),
    )


def build_lower_stop_release_event(
    *,
    closing_reaction: LowerStopReactionIndicator,
) -> HybridEvent:
    """Release a lower stop when its unilateral reaction becomes tensile.

    The deadzone lower-stop RHS recovers the physical closing-direction
    reaction ``R_low >= 0``. A metal stop may push the primary closed but
    cannot pull it open, so release occurs when ``R_low`` crosses downward
    through zero. This uses the actual unilateral reaction rather than a
    free-acceleration proxy.
    """

    return HybridEvent(
        name=CVTRegimeEvent.LOWER_STOP_RELEASE.value,
        function=lambda time, vector: float(closing_reaction(time, vector)),
        direction=-1.0,
    )


def build_upper_stop_release_event(
    *,
    opening_reaction: UpperStopReactionIndicator,
) -> HybridEvent:
    """Release an upper stop when its unilateral reaction becomes tensile.

    The constrained closure recovers the physical high-stop reaction

        R_high >= 0.

    A metal stop may push in the opening direction but cannot pull.  It is
    therefore released when ``R_high`` crosses downward through zero.  Using
    the recovered reaction directly avoids constructing a separate free-shift
    solve solely to decide whether the constraint remains admissible.
    """

    return HybridEvent(
        name=CVTRegimeEvent.UPPER_STOP_RELEASE.value,
        function=lambda time, vector: float(opening_reaction(time, vector)),
        direction=-1.0,
    )
