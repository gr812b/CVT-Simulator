"""Signed body balances from the same inspected closure used by reporting.

Axial forces are positive toward groove closure on each movable sheave.
Rotational balances use each shaft's positive rotation. No differentiation of
sampled trajectories or extra closure solves is needed here.
"""

from collections.abc import Callable
from math import cos
from typing import TYPE_CHECKING

import numpy as np
from numpy.typing import NDArray

from cinder.model.cvt.closure import ClosureUnknowns

if TYPE_CHECKING:
    from .inspection import CVTStateInspection


def reporting_unknowns(inspection: "CVTStateInspection") -> ClosureUnknowns:
    """Resolve dynamic actuator terms in engaged *and* deadzone reports."""
    if inspection.closure_unknowns is not None:
        return inspection.closure_unknowns
    deadzone = inspection.deadzone
    assert deadzone is not None
    derivative = deadzone.state_derivative
    return ClosureUnknowns(
        primary_angular_acceleration=derivative.primary_angular_acceleration,
        secondary_angular_acceleration=derivative.secondary_angular_acceleration,
        belt_acceleration=derivative.belt_acceleration,
        shift_acceleration=derivative.shift_acceleration,
        secondary_torque=(
            -deadzone.snapshot.inertias.belt.mass
            * deadzone.snapshot.belt_secondary_lock_radius
            * derivative.belt_acceleration
        ),
    )


def add_balance_signals(
    add: Callable[[str, str, str, str, NDArray[np.float64]], None],
    inspections: tuple["CVTStateInspection", ...],
) -> None:
    """Materialize forces, recovered stops and the shaft torque equations.

    Secondary axial loads are unavailable during deadzone: its belt lock does not
    solve a normal resultant. Its *rotation* balance does include the exact belt
    transport inertia required by that lock. Stop channels are zero only where
    the corresponding unconstrained body balance is actually solved.
    """
    rows = [_balance_row(item) for item in inspections]
    for side in ("primary", "secondary"):
        for suffix, label, unit in (
            ("mechanism_force", "actuator force excluding axial spring", "N"),
            ("axial_spring_force", "axial spring force", "N"),
            ("belt_axial_force", "belt axial force", "N"),
            ("stop_force", "travel-stop force", "N"),
            ("axial_inertia_force", "translating mass × axial acceleration", "N"),
            ("belt_torque", "belt torque", "N m"),
            ("coupling_torque", "mechanism coupling torque", "N m"),
            ("inertia_torque", "effective shaft inertia × angular acceleration", "N m"),
            ("angular_acceleration", "angular acceleration", "rad/s^2"),
        ):
            key = f"balance.{side}.{suffix}"
            add(
                key,
                f"{side.title()} {label}",
                unit,
                "balance",
                np.array([row.get(key, np.nan) for row in rows]),
            )


def _balance_row(item: "CVTStateInspection") -> dict[str, float]:
    u = reporting_unknowns(item)
    result = {}
    contact = item.contact
    snapshot = (contact or item.deadzone).snapshot
    for side in ("primary", "secondary"):
        prefix = f"balance.{side}"
        acceleration = getattr(u, f"{side}_angular_acceleration")
        belt_torque = getattr(u, f"{side}_torque")
        if contact:
            torque = getattr(snapshot, f"{side}_pulley").shaft_torque
            rigid_inertia = 0.0  # Already included in the composed pulley element.
            inertia = getattr(snapshot.axial_translation_inertias, side)
            belt_axial = (
                -0.5
                * cos(snapshot.sheave_half_angle)
                * getattr(u, f"{side}_normal_resultant")
            )
            stop = (
                -(contact.upper_stop_reaction or 0.0)
                if side == "primary"
                else -(contact.low_ratio_seat_reaction or 0.0)
            )
        else:
            torque = getattr(snapshot, f"{side}_mechanism").shaft_torque
            if side == "primary":
                rigid_inertia = snapshot.primary_rigid_rotational_inertia
                inertia = snapshot.primary_axial_inertia
                belt_axial = 0.0
                stop = item.deadzone.stop_reaction or 0.0
            else:
                # Keep belt inertia in belt_torque, not in the pulley inertia too.
                rigid_inertia = snapshot.secondary_rigid_belt_locked_inertia - (
                    snapshot.inertias.belt.mass * snapshot.belt_secondary_lock_radius**2
                )
                inertia = None
        gain = getattr(torque.gains, f"{side}_angular_acceleration")
        result[f"{prefix}.angular_acceleration"] = acceleration
        result[f"{prefix}.belt_torque"] = belt_torque
        result[f"{prefix}.inertia_torque"] = (rigid_inertia - gain) * acceleration
        result[f"{prefix}.coupling_torque"] = torque.evaluate(u) - gain * acceleration
        actuator = getattr(item, f"{side}_actuation")
        if actuator is not None:
            components = actuator.resolve_contributions(u)
            spring = components.get("axial_spring", 0.0)
            result[f"{prefix}.axial_spring_force"] = spring
            result[f"{prefix}.mechanism_force"] = actuator.resolve_total(u) - spring
        if inertia is not None:
            result[f"{prefix}.belt_axial_force"] = belt_axial
            result[f"{prefix}.stop_force"] = stop
            result[f"{prefix}.axial_inertia_force"] = (
                inertia.local_shift_acceleration_gain * u.shift_acceleration
                + inertia.local_known_inertial_force(shift_speed=item.state.shift_speed)
            )
    return result
