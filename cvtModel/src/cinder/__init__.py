"""CINDER: mechanics-first dynamic modelling for belt CVTs."""

from importlib.metadata import PackageNotFoundError, version as _distribution_version

try:
    __version__ = _distribution_version("cinder-cvt")
except PackageNotFoundError:
    # Source trees are expected to be installed (normally editable) before use.
    __version__ = "0+unknown"

from .core import StateBlock, StateLayout, StatePatch
from .execution.hybrid import ComposedCVTHybridSystem, ComposedCVTMode, integrate_hybrid
from .model.system import (
    BeltContactSpec,
    CVTAssemblySpec,
    CVTShaftBoundaryValues,
    CVTState,
    CVTStateDerivative,
    HelicalPulleyCoupling,
    MechanicalCVTPlant,
    PulleyPairSpec,
    PulleySpec,
    ShaftBoundaryValue,
)
from .model.boundaries import (
    ConstantGradeRoadProfile,
    EngineTorquePoint,
    FixedFinalDrive,
    FixedShaftBoundary,
    FullThrottleEngineBoundary,
    FullThrottleTorqueCurve,
    LockedFinalDriveShaftBoundary,
    RoadLoadModel,
    ShaftBoundary,
    ShaftBoundaryContext,
    TanhLongitudinalTire,
    TireCoupledShaftBoundary,
    TorqueCurveSpec,
    VehicleInertia,
    VehicleRoadLoadSpec,
)
from .hosts import NoHost, SecondaryShaftAngleHost, TireVehicleHost

__all__ = [
    "BeltContactSpec",
    "ComposedCVTHybridSystem",
    "ComposedCVTMode",
    "CVTAssemblySpec",
    "CVTShaftBoundaryValues",
    "CVTState",
    "CVTStateDerivative",
    "FixedShaftBoundary",
    "FullThrottleEngineBoundary",
    "HelicalPulleyCoupling",
    "integrate_hybrid",
    "SecondaryShaftAngleHost",
    "LockedFinalDriveShaftBoundary",
    "MechanicalCVTPlant",
    "PulleyPairSpec",
    "PulleySpec",
    "ShaftBoundary",
    "ShaftBoundaryContext",
    "ShaftBoundaryValue",
    "StateBlock",
    "StateLayout",
    "StatePatch",
    "NoHost",
    "TanhLongitudinalTire",
    "TireVehicleHost",
    "TireCoupledShaftBoundary",
    "ConstantGradeRoadProfile",
    "EngineTorquePoint",
    "FixedFinalDrive",
    "FullThrottleTorqueCurve",
    "RoadLoadModel",
    "TorqueCurveSpec",
    "VehicleInertia",
    "VehicleRoadLoadSpec",
    "__version__",
]
