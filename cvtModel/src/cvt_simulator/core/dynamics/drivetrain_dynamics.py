"""Drivetrain dynamics EOMs.

Compute rotational accelerations for primary and secondary pulleys and
belt transport acceleration from torques using the equations:

    tau_eng - tau_p = I_p * omega_p_dot
    tau_s - tau_load = I_s * omega_s_dot
    m_b * v_b_dot = tau_p / r_p_eff(s) - tau_s / r_s_eff(s)

This module provides a small helper class that accepts inertias and belt
mass and exposes `compute_accelerations(state, tau_p, tau_s)`.
"""
from cvt_simulator.geometry.cvt_geometry import CVT_GEOMETRY
from cvt_simulator.sim.system_state import SystemState
from cvt_simulator.geometry.theoretical_models import TheoreticalModels as tm
from cvt_simulator.core.components.engine import EngineModel
from cvt_simulator.core.components.vehicle_load import LoadModel
from cvt_simulator.core.data_types import (
    DrivetrainAccelerationBreakdown,
)


class DrivetrainDynamics:
    """Compute drivetrain accelerations from torques and state.

    This variant queries the provided `EngineModel` and `LoadModel` to obtain
    `tau_eng` and `tau_load` directly from the current `state`.

    Args:
        primary_inertia: I_p [kg·m²]
        secondary_inertia: I_s [kg·m²]
        belt_mass: m_b [kg]
        engine_model: EngineModel instance to query engine torque
        load_model: LoadModel instance to query external load torque
    """

    def __init__(
        self,
        primary_inertia: float,
        secondary_inertia: float,
        belt_mass: float,
        engine_model: EngineModel,
        load_model: LoadModel,
    ):
        self.I_p = float(primary_inertia)
        self.I_s = float(secondary_inertia)
        self.m_b = float(belt_mass)
        self.engine_model = engine_model
        self.load_model = load_model
        self.cvt = CVT_GEOMETRY

    def compute_accelerations(self, state: SystemState, τ_p: float, τ_s: float) -> DrivetrainAccelerationBreakdown:
        """Compute omega and belt-transport accelerations.

        Args:
            state: Current `SystemState` (used for `s` to get effective radii)
            tau_p: Torque at primary pulley transmitted to belt [N·m]
            tau_s: Torque at secondary pulley transmitted to belt [N·m]

        Returns:
            `DrivetrainAccelerations` containing the three derivatives.
        """
        s = state.s

        # Use breakdowns returned by the engine/load components directly
        engine_bd = self.engine_model.get_breakdown(state.ω_p)
        τ_eng = engine_bd.engine_torque

        load_bd = self.load_model.get_breakdown(state)
        τ_load = load_bd.net_torque_at_secondary

        # Effective pitch radii from geometry
        r_p_eff = self.cvt.primary_effective_radius(s)
        r_s_eff = self.cvt.secondary_effective_radius(s)

        # ω_p_dot = (τ_eng - τ_p) / I_p
        ω_p_dot = (τ_eng - τ_p) / self.I_p

        # ω_s_dot = (τ_s - τ_load) / I_s
        ω_s_dot = (τ_s - τ_load) / self.I_s

        # v_b_dot = (τ_p / r_p_eff - τ_s / r_s_eff) / m_b
        v_b_dot = (τ_p / r_p_eff - τ_s / r_s_eff) / self.m_b

        return DrivetrainAccelerationBreakdown(
            ω_p_dot=ω_p_dot,
            ω_s_dot=ω_s_dot,
            v_b_dot=v_b_dot,
            engine_breakdown=engine_bd,
            external_load_breakdown=load_bd,
            tau_p=τ_p,
            tau_s=τ_s,
        )

