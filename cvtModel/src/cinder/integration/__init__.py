"""Continuous state and generic hybrid integration primitives.

CVT-specific hybrid adapters deliberately remain in their own modules rather
than being imported here: dynamics depends on this package's state definitions,
so eagerly importing the CVT adapter would create an import cycle.
"""

from .hybrid import (
    HybridEvent,
    HybridIntegrationResult,
    HybridIntegratorSettings,
    HybridSegment,
    HybridSystem,
    HybridTransition,
    HybridTransitionRecord,
    integrate_hybrid,
)
from .cvt_shift_limits import EngagedShiftTravelLimits
from .state import CVTDynamicState, CVTDynamicStateDerivative

__all__ = [
    "CVTDynamicState",
    "EngagedShiftTravelLimits",
    "CVTDynamicStateDerivative",
    "HybridEvent",
    "HybridIntegrationResult",
    "HybridIntegratorSettings",
    "HybridSegment",
    "HybridSystem",
    "HybridTransition",
    "HybridTransitionRecord",
    "integrate_hybrid",
]
