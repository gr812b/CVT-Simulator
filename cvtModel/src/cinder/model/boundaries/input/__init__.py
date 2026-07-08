"""Input-shaft boundaries such as engines, motors, or dynos."""

from .attachment import InputBoundary, InputBoundaryEvaluation
from .engine import EngineTorquePoint, FullThrottleTorqueCurve, TorqueCurveSpec

# Historical name kept as an import alias while callers migrate.
InputTorqueBoundary = InputBoundary

__all__ = [
    "EngineTorquePoint",
    "FullThrottleTorqueCurve",
    "InputBoundary",
    "InputBoundaryEvaluation",
    "InputTorqueBoundary",
    "TorqueCurveSpec",
]
