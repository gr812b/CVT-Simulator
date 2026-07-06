"""Compatibility re-export for execution modules.

The actual state definition belongs to ``cinder.model.system.state``.
"""

from cinder.model.system.state import CVTDynamicState, CVTDynamicStateDerivative

__all__ = ["CVTDynamicState", "CVTDynamicStateDerivative"]
