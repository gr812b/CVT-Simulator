"""CINDER: mechanics-first dynamic modelling for belt CVTs.

Core model, execution, results, and static studies remain independent of
transport concerns.  Use :mod:`cinder.contracts` for the optional stable
external boundary: versioned assembly documents, component catalogs,
preflight validation, and JSON-safe result projection.
"""

__version__ = "0.1.0"

from .results import (
    DEFAULT_REPORT_TIME_STEP_SECONDS,
    CVTIntegrationResult,
    CVTIntegrationTrace,
    CVTResultBuilder,
    NumericSignal,
    ReportingGrid,
    ReportingSettings,
)
from .model.system import (
    BeltContactSpec,
    CVTAssemblySpec,
    CVTDynamicsModel,
    CVTDynamicState,
    CVTSimulationCase,
    HelicalPulleyCoupling,
    OperatingScenario,
    PulleyPairSpec,
    PulleySpec,
)

__all__ = [
    "BeltContactSpec",
    "DEFAULT_REPORT_TIME_STEP_SECONDS",
    "CVTIntegrationResult",
    "CVTIntegrationTrace",
    "CVTResultBuilder",
    "CVTAssemblySpec",
    "CVTDynamicsModel",
    "CVTDynamicState",
    "CVTSimulationCase",
    "HelicalPulleyCoupling",
    "OperatingScenario",
    "NumericSignal",
    "ReportingGrid",
    "ReportingSettings",
    "PulleyPairSpec",
    "PulleySpec",
    "__version__",
]
