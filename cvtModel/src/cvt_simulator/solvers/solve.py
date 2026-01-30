"""
Main entry point for CVT solvers.

Run solvers to quickly determine specific operating conditions
without executing full simulations.

Example usage:
    from cvt_simulator.solvers.solve import solve_primary_torque_threshold
    from cvt_simulator.utils.simulation_args import SimulationArgs
    
    args = SimulationArgs(
        flyweight_mass=0.9,
        primary_spring_rate=6500.0,
    )
    
    result = solve_primary_torque_threshold(args)
    
    if result.success:
        print(f"Engagement RPM: {result.value:.1f} {result.units}")
    else:
        print(f"Solver failed: {result.description}")
"""

from dataclasses import dataclass
from cvt_simulator.utils.simulation_args import SimulationArgs
from cvt_simulator.solvers.solver_interface import SolverResult
from cvt_simulator.solvers.prim_engagement.primary_cvt_engagement_solver import PrimaryCVTEngagementSolver
from cvt_simulator.solvers.shift_initiation.shift_initiation_solver import ShiftInitiationSolver


@dataclass
class AllSolverResults:
    """Combined results from all CVT solvers."""
    primary_engagement: SolverResult
    shift_initiation: SolverResult

def solve_primary_cvt_engagement(args: SimulationArgs) -> SolverResult:
    solver = PrimaryCVTEngagementSolver(args)
    return solver.solve()


def solve_shift_initiation(args: SimulationArgs) -> SolverResult:
    solver = ShiftInitiationSolver(args)
    return solver.solve()


def solve_all(args: SimulationArgs) -> AllSolverResults:
    return AllSolverResults(
        primary_engagement=solve_primary_cvt_engagement(args),
        shift_initiation=solve_shift_initiation(args),
    )
