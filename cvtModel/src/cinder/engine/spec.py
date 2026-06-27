# cinder/engine/spec.py

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite


@dataclass(frozen=True, slots=True)
class EngineTorquePoint:
    """One measured full-throttle crankshaft-torque point in SI units."""

    angular_speed: float
    torque: float

    def __post_init__(self) -> None:
        if not isfinite(self.angular_speed) or self.angular_speed < 0.0:
            raise ValueError(
                "angular_speed must be finite and non-negative."
            )

        if not isfinite(self.torque):
            raise ValueError("torque must be finite.")


@dataclass(frozen=True, slots=True)
class TorqueCurveSpec:
    """
    Full-throttle crankshaft torque curve in SI units.

    The first and final measured points must have zero torque. They define
    the low- and high-speed limits of positive full-throttle drive torque.

    The curve includes two bounded negative-torque tails:

    * below ``minimum_speed``, a low-speed braking bowl that is zero at rest
      and at ``minimum_speed``;
    * above ``maximum_speed``, a smooth transition to a finite overspeed
      braking plateau.
    """

    points: tuple[EngineTorquePoint, ...]

    low_speed_braking_torque: float
    low_speed_braking_peak_speed: float

    high_speed_braking_torque: float
    high_speed_braking_transition_width: float

    def __post_init__(self) -> None:
        points = tuple(self.points)

        if len(points) < 2:
            raise ValueError("At least two torque points are required.")

        for previous, current in zip(points, points[1:]):
            if current.angular_speed <= previous.angular_speed:
                raise ValueError(
                    "Torque points must have strictly increasing "
                    "angular_speed values."
                )

        if points[0].angular_speed <= 0.0:
            raise ValueError(
                "The first torque-point speed must be strictly positive."
            )

        if points[0].torque != 0.0:
            raise ValueError("The first torque point must have zero torque.")

        if points[-1].torque != 0.0:
            raise ValueError("The final torque point must have zero torque.")

        if not isfinite(self.low_speed_braking_torque):
            raise ValueError("low_speed_braking_torque must be finite.")

        if self.low_speed_braking_torque >= 0.0:
            raise ValueError("low_speed_braking_torque must be negative.")

        if (
            not isfinite(self.low_speed_braking_peak_speed)
            or not 0.0 < self.low_speed_braking_peak_speed < points[0].angular_speed
        ):
            raise ValueError(
                "low_speed_braking_peak_speed must lie strictly between "
                "zero and the first torque-point speed."
            )

        if not isfinite(self.high_speed_braking_torque):
            raise ValueError("high_speed_braking_torque must be finite.")

        if self.high_speed_braking_torque >= 0.0:
            raise ValueError("high_speed_braking_torque must be negative.")

        if (
            not isfinite(self.high_speed_braking_transition_width)
            or self.high_speed_braking_transition_width <= 0.0
        ):
            raise ValueError(
                "high_speed_braking_transition_width must be finite and "
                "positive."
            )

        object.__setattr__(self, "points", points)

    @property
    def minimum_speed(self) -> float:
        return self.points[0].angular_speed

    @property
    def maximum_speed(self) -> float:
        return self.points[-1].angular_speed

    @property
    def high_speed_braking_plateau_start(self) -> float:
        return self.maximum_speed + self.high_speed_braking_transition_width

    @property
    def high_speed_braking_plateau_end(self) -> float:
        return (
            self.high_speed_braking_plateau_start
            + self.high_speed_braking_transition_width
        )
