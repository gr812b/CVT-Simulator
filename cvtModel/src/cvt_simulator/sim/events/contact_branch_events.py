"""Contact branch transition events.

This module defines event functions and transition mapping for the accepted
contact branch. It does not resolve contact torques. It only asks whether the
current accepted contact branch should change.

Expected contact_model API:

    metrics = contact_model.get_slip_metrics(state)

where metrics contains:
    primary_relative_speed
    secondary_relative_speed
    no_slip.tau_p_ns
    no_slip.tau_s_ns
    admissibility.primary_tau_p_stick_lower
    admissibility.primary_tau_p_stick_upper
    admissibility.secondary_tau_stick_lower
    admissibility.secondary_tau_stick_upper
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from cvt_simulator.core.data_types import SlipBranch, SlipMetricsResult
from cvt_simulator.core.dynamics.contact_dynamics_model import ContactDynamicsModel
from cvt_simulator.sim.system_state import SystemState
from cvt_simulator.constants.tuning import BELT_STICK_SPEED_THRESHOLD
thres = 0.1

CONTACT_SLIP_ENTER_SPEED = 0.5 * thres
CONTACT_SLIP_EXIT_SPEED = 1.1 * thres

CONTACT_TORQUE_ENTER_MARGIN = 0.01
CONTACT_TORQUE_EXIT_MARGIN = 0.01


@dataclass(frozen=True)
class NamedContactEvent:
    name: str
    fn: Callable


def _inside_interval_margin(
    value: float,
    lower: float,
    upper: float,
    margin: float,
) -> float:
    """Positive when safely inside interval, negative when outside.

    The margin shrinks the usable interval:
        [lower, upper] -> [lower + margin, upper - margin]
    """
    lower_margin = abs(lower) * margin
    upper_margin = abs(upper) * margin

    return min(
        value - (lower + lower_margin),
        (upper - upper_margin) - value,
    )


def _outside_interval_margin(
    value: float,
    lower: float,
    upper: float,
    margin: float,
) -> float:
    """Positive when safely inside expanded interval, negative when outside.

    Used for slip entry. The margin expands the allowed interval before
    declaring slip:
        [lower, upper] -> [lower - margin, upper + margin]
    """
    lower_margin = abs(lower) * margin
    upper_margin = abs(upper) * margin

    return min(
        value - (lower - lower_margin),
        (upper + upper_margin) - value,
    )


def _primary_entry_value(metrics: SlipMetricsResult) -> float:
    """Positive while primary can remain stuck, negative when it should enter slip."""
    speed_margin = CONTACT_SLIP_ENTER_SPEED - abs(metrics.primary_relative_speed)

    torque_margin = _outside_interval_margin(
        value=metrics.no_slip.tau_p_ns,
        lower=metrics.admissibility.primary_tau_p_stick_lower,
        upper=metrics.admissibility.primary_tau_p_stick_upper,
        margin=CONTACT_TORQUE_ENTER_MARGIN,
    )

    # Entry condition is OR:
    #   speed too large OR torque outside bounds.
    # Therefore the event value is the minimum margin.
    return min(speed_margin, torque_margin)


def _secondary_entry_value(metrics: SlipMetricsResult) -> float:
    """Positive while secondary can remain stuck, negative when it should enter slip."""
    speed_margin = CONTACT_SLIP_ENTER_SPEED - abs(metrics.secondary_relative_speed)

    torque_margin = _outside_interval_margin(
        value=metrics.no_slip.tau_s_ns,
        lower=metrics.admissibility.secondary_tau_stick_lower,
        upper=metrics.admissibility.secondary_tau_stick_upper,
        margin=CONTACT_TORQUE_ENTER_MARGIN,
    )

    return min(speed_margin, torque_margin)


def _primary_exit_value(metrics: SlipMetricsResult) -> float:
    """Positive while primary should keep slipping, negative when it may reattach."""
    speed_excess = abs(metrics.primary_relative_speed) - CONTACT_SLIP_EXIT_SPEED

    torque_outside = -_inside_interval_margin(
        value=metrics.no_slip.tau_p_ns,
        lower=metrics.admissibility.primary_tau_p_stick_lower,
        upper=metrics.admissibility.primary_tau_p_stick_upper,
        margin=CONTACT_TORQUE_EXIT_MARGIN,
    )

    # Exit condition is AND:
    #   speed small AND torque safely admissible.
    # Therefore the event value is the maximum violation.
    return max(speed_excess, torque_outside)


def _secondary_exit_value(metrics: SlipMetricsResult) -> float:
    """Positive while secondary should keep slipping, negative when it may reattach."""
    speed_excess = abs(metrics.secondary_relative_speed) - CONTACT_SLIP_EXIT_SPEED

    torque_outside = -_inside_interval_margin(
        value=metrics.no_slip.tau_s_ns,
        lower=metrics.admissibility.secondary_tau_stick_lower,
        upper=metrics.admissibility.secondary_tau_stick_upper,
        margin=CONTACT_TORQUE_EXIT_MARGIN,
    )

    return max(speed_excess, torque_outside)


def _make_event(contact_model: ContactDynamicsModel, value_fn: Callable, direction: int):
    def event(t, y):
        state = SystemState.from_array(y)
        metrics = contact_model.get_slip_metrics(state)
        return value_fn(metrics)

    event.terminal = True
    event.direction = direction
    return event


def get_contact_branch_events(
    contact_branch: SlipBranch,
    contact_model: ContactDynamicsModel,
) -> tuple[list[Callable], list[str]]:
    """Return active contact transition events for the current contact branch."""

    primary_entry = _make_event(
        contact_model,
        _primary_entry_value,
        direction=-1,
    )
    secondary_entry = _make_event(
        contact_model,
        _secondary_entry_value,
        direction=-1,
    )
    primary_exit = _make_event(
        contact_model,
        _primary_exit_value,
        direction=-1,
    )
    secondary_exit = _make_event(
        contact_model,
        _secondary_exit_value,
        direction=-1,
    )

    if contact_branch is SlipBranch.NO_SLIP:
        return (
            [primary_entry, secondary_entry],
            ["primary_slip_entry_event", "secondary_slip_entry_event"],
        )

    if contact_branch is SlipBranch.PRIMARY_SLIP:
        return (
            [primary_exit, secondary_entry],
            ["primary_slip_exit_event", "secondary_slip_entry_event"],
        )

    if contact_branch is SlipBranch.SECONDARY_SLIP:
        return (
            [secondary_exit, primary_entry],
            ["secondary_slip_exit_event", "primary_slip_entry_event"],
        )

    if contact_branch is SlipBranch.BOTH_SLIP:
        return (
            [primary_exit, secondary_exit],
            ["primary_slip_exit_event", "secondary_slip_exit_event"],
        )

    raise ValueError(f"Unknown contact branch: {contact_branch}")


def next_contact_branch(
    current_branch: SlipBranch,
    fired_event_names: list[str],
) -> SlipBranch:
    """Map current branch plus fired contact event(s) to the next branch."""

    fired = set(fired_event_names)

    primary_enters = "primary_slip_entry_event" in fired
    secondary_enters = "secondary_slip_entry_event" in fired
    primary_exits = "primary_slip_exit_event" in fired
    secondary_exits = "secondary_slip_exit_event" in fired

    if current_branch is SlipBranch.NO_SLIP:
        if primary_enters and secondary_enters:
            return SlipBranch.BOTH_SLIP
        if primary_enters:
            return SlipBranch.PRIMARY_SLIP
        if secondary_enters:
            return SlipBranch.SECONDARY_SLIP
        return SlipBranch.NO_SLIP

    if current_branch is SlipBranch.PRIMARY_SLIP:
        if primary_exits and secondary_enters:
            return SlipBranch.SECONDARY_SLIP
        if secondary_enters:
            return SlipBranch.BOTH_SLIP
        if primary_exits:
            return SlipBranch.NO_SLIP
        return SlipBranch.PRIMARY_SLIP

    if current_branch is SlipBranch.SECONDARY_SLIP:
        if secondary_exits and primary_enters:
            return SlipBranch.PRIMARY_SLIP
        if primary_enters:
            return SlipBranch.BOTH_SLIP
        if secondary_exits:
            return SlipBranch.NO_SLIP
        return SlipBranch.SECONDARY_SLIP

    if current_branch is SlipBranch.BOTH_SLIP:
        if primary_exits and secondary_exits:
            return SlipBranch.NO_SLIP
        if primary_exits:
            return SlipBranch.SECONDARY_SLIP
        if secondary_exits:
            return SlipBranch.PRIMARY_SLIP
        return SlipBranch.BOTH_SLIP

    raise ValueError(f"Unknown contact branch: {current_branch}")