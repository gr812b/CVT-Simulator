"""Mode-dependent event construction for the engaged CVT contact adapter."""

from __future__ import annotations

from enum import Enum
from typing import Callable

import numpy as np
from numpy.typing import NDArray

from cinder.model.cvt.contact import ContactInterface, ContactRegime, SlipDirection

from .cvt_contact import CVTContactEvaluation
from .hybrid import HybridEvent


class CVTContactEvent(str, Enum):
    """Named events understood by the engaged CVT transition resolver."""

    PRIMARY_STATIC_CAPACITY = "primary_static_capacity"
    SECONDARY_STATIC_CAPACITY = "secondary_static_capacity"
    PRIMARY_RESTICK = "primary_restick"
    SECONDARY_RESTICK = "secondary_restick"
    PRIMARY_NORMAL_FLOOR = "primary_normal_floor"
    SECONDARY_NORMAL_FLOOR = "secondary_normal_floor"
    LOWER_SHIFT_STOP = "lower_shift_stop"
    UPPER_SHIFT_STOP = "upper_shift_stop"


def build_cvt_contact_events(
    *,
    regime: ContactRegime,
    evaluate: Callable[[float, NDArray[np.float64]], CVTContactEvaluation],
    traction_law,
    switching_settings,
    relative_speed_tolerance: float = 1.0e-7,
    relative_acceleration_tolerance: float = 1.0e-8,
    minimum_shift: float | None = None,
    maximum_shift: float | None = None,
    include_shift_boundary_events: bool = True,
    include_primary_normal_floor: bool = True,
    include_secondary_normal_floor: bool = True,
) -> tuple[HybridEvent, ...]:
    """Build only the events meaningful to the active engaged contact regime.

    ``include_shift_boundary_events`` preserves the existing engaged-only
    adapter behavior.  The operating-regime adapter disables those two legacy
    guards and supplies its own geometry events, because upper-stop arrival is
    now a real constrained continuation rather than a terminal failure.
    """

    if relative_speed_tolerance <= 0.0:
        raise ValueError("relative_speed_tolerance must be strictly positive.")
    if relative_acceleration_tolerance <= 0.0:
        raise ValueError("relative_acceleration_tolerance must be strictly positive.")

    events: list[HybridEvent] = []
    if include_primary_normal_floor:
        events.append(
            HybridEvent(
                name=CVTContactEvent.PRIMARY_NORMAL_FLOOR.value,
                function=lambda time, vector: evaluate(time, vector).normal_primary
                - switching_settings.normal_resultant_floor,
                direction=-1.0,
            )
        )
    if include_secondary_normal_floor:
        events.append(
            HybridEvent(
                name=CVTContactEvent.SECONDARY_NORMAL_FLOOR.value,
                function=lambda time, vector: evaluate(time, vector).normal_secondary
                - switching_settings.normal_resultant_floor,
                direction=-1.0,
            )
        )
    if include_shift_boundary_events:
        if minimum_shift is None or maximum_shift is None:
            raise ValueError(
                "minimum_shift and maximum_shift are required when "
                "include_shift_boundary_events is true."
            )
        events.extend(
            (
                HybridEvent(
                    name=CVTContactEvent.LOWER_SHIFT_STOP.value,
                    function=lambda time, vector: float(vector[3] - minimum_shift),
                    direction=-1.0,
                ),
                HybridEvent(
                    name=CVTContactEvent.UPPER_SHIFT_STOP.value,
                    function=lambda time, vector: float(maximum_shift - vector[3]),
                    direction=-1.0,
                ),
            )
        )

    for interface in regime.mode.sticking_interfaces:
        event = (
            CVTContactEvent.PRIMARY_STATIC_CAPACITY
            if interface is ContactInterface.PRIMARY
            else CVTContactEvent.SECONDARY_STATIC_CAPACITY
        )
        events.append(
            HybridEvent(
                name=event.value,
                function=lambda time, vector, interface=interface: evaluate(
                    time, vector
                ).static_margin_at(
                    interface,
                    traction_law=traction_law,
                )
                - switching_settings.stick_exit_static_margin,
                direction=-1.0,
            )
        )

    for interface in regime.mode.slipping_interfaces:
        restick_event = (
            CVTContactEvent.PRIMARY_RESTICK
            if interface is ContactInterface.PRIMARY
            else CVTContactEvent.SECONDARY_RESTICK
        )
        direction_sign = _slip_direction_sign(regime.slip_direction_at(interface))

        # A finite-speed transition into stick would silently leave a nonzero
        # v_rel in a branch whose acceleration constraint merely preserves it.
        # Therefore the terminal re-stick event is the exact crossing v_rel=0.
        def restick_indicator(
            time: float,
            vector: NDArray[np.float64],
            *,
            interface: ContactInterface = interface,
            direction_sign: float = direction_sign,
        ) -> float:
            evaluation = evaluate(time, vector)
            relative_speed = evaluation.relative_motion.relative_speed_at(interface)
            relative_acceleration = evaluation.relative_motion.relative_acceleration_at(
                interface
            )
            # A kinetic trajectory can only touch v_rel = 0 and return in the
            # same Coulomb direction.  That is not a physical re-stick or a
            # slip-direction reversal.  Re-arm the event at the exact root so
            # a segmented integrator does not create a no-op transition.
            if (
                abs(relative_speed) <= relative_speed_tolerance
                and direction_sign * relative_acceleration
                > relative_acceleration_tolerance
            ):
                return relative_speed_tolerance
            return direction_sign * relative_speed

        events.append(
            HybridEvent(
                name=restick_event.value,
                function=restick_indicator,
                direction=-1.0,
            )
        )

    return tuple(events)


def _slip_direction_sign(direction: SlipDirection) -> float:
    if direction is SlipDirection.BELT_LEADS_PULLEY:
        return 1.0
    if direction is SlipDirection.PULLEY_LEADS_BELT:
        return -1.0
    raise ValueError("A kinetic event requires a determinate slip direction.")
