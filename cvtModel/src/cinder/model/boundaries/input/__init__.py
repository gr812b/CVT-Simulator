"""Input-shaft boundaries such as engines, motors, or dynos."""

from typing import Protocol

from .engine import EngineTorquePoint, FullThrottleTorqueCurve, TorqueCurveSpec


class InputTorqueBoundary(Protocol):
    """Contract for a source torque applied to the CVT input shaft."""

    def evaluate(self, angular_speed: float) -> float:
        """Return signed shaft torque at one angular speed."""


__all__ = [
    "EngineTorquePoint",
    "FullThrottleTorqueCurve",
    "InputTorqueBoundary",
    "TorqueCurveSpec",
]
