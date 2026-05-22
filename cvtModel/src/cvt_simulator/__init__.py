from .main import simulate_cvt_model
from .sim_utils.simulation_args import SimulationArgs
from .core.data_types import (
    CvtDynamicsBreakdown,
    SecondaryForceBreakdown,
    PrimaryForceBreakdown,
    ContactTorqueResult,
    DrivetrainAccelerationBreakdown,
    ContactDynamicsBreakdown,
)
from .utils.frontend_output import SimulationAnalysisResult, FormattedSimulationResult
from .ramps.ramp_config import PiecewiseRampConfig
from .ramps.piecewise_ramp import PiecewiseRamp
from .constants.car_specs import CarSpecs
from .solvers.solve import solve_all, AllSolverResults

# Backward-compatible aliases for older public names.
SecondaryPulleyDynamicsBreakdown = SecondaryForceBreakdown
PrimaryPulleyDynamicsBreakdown = PrimaryForceBreakdown
SlipBreakdown = ContactTorqueResult
DrivetrainBreakdown = DrivetrainAccelerationBreakdown

__all__ = [
    "simulate_cvt_model",
    "SimulationArgs",
    "CvtDynamicsBreakdown",
    "ContactDynamicsBreakdown",
    "PrimaryForceBreakdown",
    "SecondaryForceBreakdown",
    "SecondaryPulleyDynamicsBreakdown",
    "PrimaryPulleyDynamicsBreakdown",
    "SlipBreakdown",
    "ContactTorqueResult",
    "DrivetrainAccelerationBreakdown",
    "DrivetrainBreakdown",
    "SimulationAnalysisResult",
    "FormattedSimulationResult",
    "PiecewiseRampConfig",
    "PiecewiseRamp",
    "CarSpecs",
    "solve_all",
    "AllSolverResults",
]
