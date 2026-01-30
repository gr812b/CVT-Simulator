"""
Base interface for CVT model solvers.

Solvers answer specific questions about operating conditions
(e.g., "at what RPM does X happen?") without running full simulations.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional
from cvt_simulator.utils.simulation_args import SimulationArgs


@dataclass
class SolverResult:
    """
    Result from a solver operation.
    
    Attributes:
        success: Whether the solver found a solution
        value: The primary result value (e.g., RPM, torque, etc.)
        units: Units of the result value
        description: Human-readable description of what was solved
    """
    success: bool
    value: Optional[float]
    units: str
    description: str


class SolverBase(ABC):
    """
    Base class for all CVT solvers.
    
    Solvers take SimulationArgs (same inputs as full simulation)
    and solve for specific conditions analytically or through optimization.
    """
    
    def __init__(self, args: SimulationArgs):
        """
        Initialize solver with simulation parameters.
        
        Args:
            args: Simulation parameters that define the CVT configuration
        """
        self.args = args
    
    @abstractmethod
    def solve(self) -> SolverResult:
        """
        Execute the solver to find the solution.
        
        Returns:
            SolverResult with the solution or failure information
        """
        pass
    
    @property
    @abstractmethod
    def solver_name(self) -> str:
        """Human-readable name of this solver."""
        pass
    
    @property
    @abstractmethod
    def solver_description(self) -> str:
        """Detailed description of what this solver computes."""
        pass
