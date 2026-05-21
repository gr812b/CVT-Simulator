"""Combined contact and drivetrain dynamics bridge.

This wrapper computes the active contact torques first, then passes the
resolved torques into the drivetrain helper and the secondary torque into the
shift dynamics helper.
"""
from dataclasses import dataclass

from cvt_simulator.components.engine import EngineModel
from cvt_simulator.components.primary_pulley import PrimaryPulley
from cvt_simulator.components.secondary_pulley import SecondaryPulley
from cvt_simulator.components.vehicle_load import LoadModel
from cvt_simulator.core.system_state import SystemState
from cvt_simulator.dynamics.drivetrain_dynamics import DrivetrainDynamics
from cvt_simulator.core.data_types import DrivetrainAccelerationBreakdown
from cvt_simulator.dynamics.shift_dynamics import ShiftDynamics
from cvt_simulator.models.dataTypes import CvtDynamicsBreakdown
from cvt_simulator.slip.contact_torque_solver import ContactTorqueResult, ContactTorqueSolver


@dataclass
class ContactDynamicsBreakdown:
    contact: ContactTorqueResult
    drivetrain: DrivetrainAccelerationBreakdown
    shift: CvtDynamicsBreakdown


class ContactDynamicsModel:
    """Compute contact torques and pass them through drivetrain and shift dynamics."""

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
        self.contact_torque_solver = ContactTorqueSolver(primary_pulley, secondary_pulley)
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

    def get_breakdown(self, state: SystemState) -> ContactDynamicsBreakdown:
        """Return the branch-selected contact result and downstream dynamics."""
        tau_engine = self.engine_model.get_torque(state.ω_p)
        tau_load = self.load_model.get_breakdown(state).net_torque_at_secondary

        contact = self.contact_torque_solver.solve(
            state=state,
            tau_engine=tau_engine,
            tau_load=tau_load,
            I_p=self.drivetrain_dynamics.I_p,
            I_s=self.drivetrain_dynamics.I_s,
            m_b=self.drivetrain_dynamics.m_b,
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

        return ContactDynamicsBreakdown(
            contact=contact,
            drivetrain=drivetrain,
            shift=shift,
        )
