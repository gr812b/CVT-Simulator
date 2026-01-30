"""
CVT Model Solvers

Quick analytical solvers for determining specific operating conditions
without running full simulations.
"""

from cvt_simulator.solvers.solver_interface import SolverResult
from cvt_simulator.solvers.prim_engagement.primary_cvt_engagement_solver import PrimaryCVTEngagementSolver
from cvt_simulator.solvers.shift_initiation.shift_initiation_solver import ShiftInitiationSolver

__all__ = [
    "SolverResult",
    "PrimaryCVTEngagementSolver",
    "ShiftInitiationSolver",
]
