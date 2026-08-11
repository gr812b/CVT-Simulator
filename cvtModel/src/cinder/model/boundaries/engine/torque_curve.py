from __future__ import annotations

from math import isfinite

from scipy.interpolate import PchipInterpolator

from .spec import EngineTorquePoint, TorqueCurveSpec


class FullThrottleTorqueCurve:
    """
    Smooth full-throttle crankshaft torque curve with bounded braking tails.

    Supplied running points are interpolated with PCHIP. The added tail points
    preserve the supplied zero-torque speeds while allowing an externally
    driven engine to apply finite resisting torque below and above them.
    """

    def __init__(
        self,
        spec: TorqueCurveSpec,
    ) -> None:
        self._spec = spec

        extended_points = (
            EngineTorquePoint(angular_speed=0.0, torque=0.0),
            EngineTorquePoint(
                angular_speed=spec.low_speed_braking_peak_speed,
                torque=spec.low_speed_braking_torque,
            ),
            *spec.points,
            EngineTorquePoint(
                angular_speed=spec.high_speed_braking_plateau_start,
                torque=spec.high_speed_braking_torque,
            ),
            EngineTorquePoint(
                angular_speed=spec.high_speed_braking_plateau_end,
                torque=spec.high_speed_braking_torque,
            ),
        )

        self._interpolator = PchipInterpolator(
            [point.angular_speed for point in extended_points],
            [point.torque for point in extended_points],
            extrapolate=False,
        )

    @property
    def spec(self) -> TorqueCurveSpec:
        return self._spec

    @property
    def minimum_speed(self) -> float:
        return self._spec.minimum_speed

    @property
    def maximum_speed(self) -> float:
        return self._spec.maximum_speed

    def torque_at(self, angular_speed: float) -> float:
        """Return full-throttle net crankshaft torque in N m."""

        if not isfinite(angular_speed):
            raise ValueError("angular_speed must be finite.")

        if angular_speed <= 0.0:
            return 0.0

        if angular_speed >= self._spec.high_speed_braking_plateau_end:
            return self._spec.high_speed_braking_torque

        return float(self._interpolator(angular_speed))
