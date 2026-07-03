"""Persistent engaged-contact topology and established slip directions."""

from __future__ import annotations

from dataclasses import dataclass

from .mode import EngagedContactMode
from .relative_motion import ContactInterface, SlipDirection


@dataclass(frozen=True, slots=True)
class ContactRegime:
    """One active engaged-contact regime for a hybrid ODE segment.

    ``mode`` identifies which interfaces are constrained to stick. Every
    slipping interface stores an established kinematic direction.  That
    direction is selected only at an initial classification or a terminal
    contact transition; the RHS never re-infers it from noisy near-zero speed.

    Re-stick is evaluated at the exact event ``v_rel = 0``.  A static-margin
    reserve supplies hysteresis, so no separate re-arm state is needed.
    """

    mode: EngagedContactMode
    primary_slip_direction: SlipDirection | None = None
    secondary_slip_direction: SlipDirection | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.mode, EngagedContactMode):
            raise TypeError("mode must be an EngagedContactMode.")
        self._validate_interface(ContactInterface.PRIMARY, self.primary_slip_direction)
        self._validate_interface(ContactInterface.SECONDARY, self.secondary_slip_direction)

    @classmethod
    def stick_stick(cls) -> "ContactRegime":
        return cls(mode=EngagedContactMode.STICK_STICK)

    @classmethod
    def primary_slip_secondary_stick(
        cls,
        *,
        primary_direction: SlipDirection,
    ) -> "ContactRegime":
        return cls(
            mode=EngagedContactMode.PRIMARY_SLIP_SECONDARY_STICK,
            primary_slip_direction=primary_direction,
        )

    @classmethod
    def primary_stick_secondary_slip(
        cls,
        *,
        secondary_direction: SlipDirection,
    ) -> "ContactRegime":
        return cls(
            mode=EngagedContactMode.PRIMARY_STICK_SECONDARY_SLIP,
            secondary_slip_direction=secondary_direction,
        )

    @classmethod
    def both_slip(
        cls,
        *,
        primary_direction: SlipDirection,
        secondary_direction: SlipDirection,
    ) -> "ContactRegime":
        return cls(
            mode=EngagedContactMode.BOTH_SLIP,
            primary_slip_direction=primary_direction,
            secondary_slip_direction=secondary_direction,
        )

    def slip_direction_at(self, interface: ContactInterface) -> SlipDirection:
        if interface not in self.mode.slipping_interfaces:
            raise ValueError(f"{interface.value} is not slipping in {self.mode.value}.")
        direction = (
            self.primary_slip_direction
            if interface is ContactInterface.PRIMARY
            else self.secondary_slip_direction
        )
        if direction is None:  # Defensive; __post_init__ already rejects this.
            raise RuntimeError("Slipping contact has no stored direction.")
        return direction

    def _validate_interface(
        self,
        interface: ContactInterface,
        direction: SlipDirection | None,
    ) -> None:
        if interface in self.mode.slipping_interfaces:
            if direction is None or direction is SlipDirection.INDETERMINATE:
                raise ValueError(
                    f"{interface.value} slip requires a determinate stored direction."
                )
            return
        if direction is not None:
            raise ValueError(
                f"{interface.value} is sticking in {self.mode.value} and cannot store a slip direction."
            )
