"""Combined contact and drivetrain dynamics bridge.

This wrapper computes the active contact torques first, then passes the
resolved torques into the drivetrain helper and the secondary torque into the
shift dynamics helper.
"""

from cvt_simulator.core.components.engine import EngineModel
from cvt_simulator.core.components.primary_pulley import PrimaryPulley
from cvt_simulator.core.components.secondary_pulley import SecondaryPulley
from cvt_simulator.core.components.vehicle_load import LoadModel
from cvt_simulator.constants.car_specs import BELT_CROSS_SECTIONAL_AREA, BELT_LENGTH
from cvt_simulator.constants.constants import RUBBER_DENSITY
from cvt_simulator.sim.system_state import SystemState
from cvt_simulator.core.dynamics.drivetrain_dynamics import DrivetrainDynamics
from cvt_simulator.core.dynamics.shift_dynamics import ShiftDynamics
from cvt_simulator.core.slip.contact_torque_solver import ContactTorqueSolver
from cvt_simulator.core.data_types import ContactDynamicsBreakdown, SlipBranch
from cvt_simulator.geometry.cvt_geometry import CVT_GEOMETRY


class ContactDynamicsModel:
    """Compute contact torques and pass them through drivetrain and shift dynamics."""

    @staticmethod
    def compute_belt_mass() -> float:
        """Compute the effective belt mass from geometry and material density."""
        return BELT_CROSS_SECTIONAL_AREA * RUBBER_DENSITY * BELT_LENGTH

    def __init__(
        self,
        primary_pulley: PrimaryPulley,
        secondary_pulley: SecondaryPulley,
        primary_inertia: float,
        secondary_inertia: float,
        belt_mass: float,
        engine_model: EngineModel,
        load_model: LoadModel,
        cvt_moving_mass: float = 0.5,
    ) -> None:
        self.primary_pulley = primary_pulley
        self.secondary_pulley = secondary_pulley
        self.engine_model = engine_model
        self.load_model = load_model
        self.contact_torque_solver = ContactTorqueSolver(
            primary_pulley,
            secondary_pulley,
            primary_inertia,
            secondary_inertia,
            belt_mass,
        )
        self.drivetrain_dynamics = DrivetrainDynamics(
            primary_inertia=primary_inertia,
            secondary_inertia=secondary_inertia,
            belt_mass=belt_mass,
            engine_model=engine_model,
            load_model=load_model,
        )
        self.shift_dynamics = ShiftDynamics(
            primary_pulley=primary_pulley,
            secondary_pulley=secondary_pulley,
            cvt_moving_mass=cvt_moving_mass,
        )

    def get_breakdown(
        self, state: SystemState, contact_branch: SlipBranch
    ) -> ContactDynamicsBreakdown:
        """Return the branch-selected contact result and downstream dynamics."""
        tau_engine = self.engine_model.get_torque(state.ω_p)
        tau_load = self.load_model.get_breakdown(state).net_torque_at_secondary

        # TODO: Pass the contact branch through here
        contact = self.contact_torque_solver.solve(
            state=state,
            contact_branch=contact_branch,
            tau_engine=tau_engine,
            tau_load=tau_load,
        )
        drivetrain = self.drivetrain_dynamics.compute_accelerations(
            state,
            contact.tau_p,
            contact.tau_s,
        )
        shift = self.shift_dynamics.get_breakdown(
            state,
            contact.tau_s,
        )
        geometry = CVT_GEOMETRY.geometry_from_shift_distance(state.s, state.s_dot)

        return ContactDynamicsBreakdown(
            contact=contact,
            drivetrain=drivetrain,
            shift=shift,
            geometry=geometry,
        )

    # TODO: Temp drilling to avoid extra compute
    def get_slip_metrics(self, state: SystemState):
        tau_engine = self.engine_model.get_torque(state.ω_p)
        tau_load = self.load_model.get_breakdown(state).net_torque_at_secondary

        return self.contact_torque_solver.get_slip_metrics(state, tau_engine, tau_load)
