"""The four engaged contact modes; deadzone is intentionally separate."""

from __future__ import annotations

from enum import Enum

from .relative_motion import ContactInterface


class EngagedContactMode(str, Enum):
    """Contact modes valid only after both pulley interfaces are engaged.

    ``DEADZONE`` is deliberately not included. It is the separate fifth system
    state: no wrap equations, no lambda variables, and no belt torque transfer.
    """

    STICK_STICK = "stick_stick"
    PRIMARY_SLIP_SECONDARY_STICK = "primary_slip_secondary_stick"
    PRIMARY_STICK_SECONDARY_SLIP = "primary_stick_secondary_slip"
    BOTH_SLIP = "both_slip"

    @property
    def sticking_interfaces(self) -> tuple[ContactInterface, ...]:
        if self is EngagedContactMode.STICK_STICK:
            return (ContactInterface.PRIMARY, ContactInterface.SECONDARY)
        if self is EngagedContactMode.PRIMARY_SLIP_SECONDARY_STICK:
            return (ContactInterface.SECONDARY,)
        if self is EngagedContactMode.PRIMARY_STICK_SECONDARY_SLIP:
            return (ContactInterface.PRIMARY,)
        return ()

    @property
    def slipping_interfaces(self) -> tuple[ContactInterface, ...]:
        if self is EngagedContactMode.STICK_STICK:
            return ()
        if self is EngagedContactMode.PRIMARY_SLIP_SECONDARY_STICK:
            return (ContactInterface.PRIMARY,)
        if self is EngagedContactMode.PRIMARY_STICK_SECONDARY_SLIP:
            return (ContactInterface.SECONDARY,)
        return (ContactInterface.PRIMARY, ContactInterface.SECONDARY)
