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
from .cvt_lower_stop import (
    apply_perfectly_inelastic_lower_stop_impact,
    lower_stop_release_value,
)
from .cvt_upper_stop import (
    apply_perfectly_inelastic_upper_stop_impact,
    upper_stop_release_value,
)
from .state import CVTDynamicState, CVTDynamicStateDerivative

__all__ = [
    "lower_stop_release_value",
    "apply_perfectly_inelastic_lower_stop_impact",
    "CVTDynamicState",
    "apply_perfectly_inelastic_upper_stop_impact",
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
    "upper_stop_release_value",
]
