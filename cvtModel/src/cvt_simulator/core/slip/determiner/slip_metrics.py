
from cvt_simulator.constants.tuning import BELT_STICK_SPEED_THRESHOLD
from cvt_simulator.core.data_types import SlipMetricsResult
from cvt_simulator.core.slip.determiner.no_slip_candidate import compute_no_slip_candidate
from cvt_simulator.core.slip.determiner.torque_admissibility import TorqueAdmissibility
from cvt_simulator.geometry.cvt_geometry import CVT_GEOMETRY
from cvt_simulator.sim.system_state import SystemState


class SlipMetrics:
  """
  All this class does is compute the required slip metrics from current state
  
  This includes:
  - Relative contact speeds
  - Slip directions
  - No slip torques
  - Torque admissibility bounds (primary and secondary) upper and lower
  """
  

  def __init__(
      self,
      torque_admissibility_solver: TorqueAdmissibility,
      I_p: float,
      I_s: float,
      m_b: float
    ) -> None:
    self.cvt = CVT_GEOMETRY
    self.torque_admissibility_solver = torque_admissibility_solver
    self.I_p = I_p
    self.I_s = I_s
    self.m_b = m_b

  def get_slip_metrics(
        self, 
        state: SystemState, 
        τ_eng: float,
        τ_load: float
    ) -> SlipMetricsResult:
    """Compute slip metrics for the current state."""

    # Get no slip solution
    no_slip_solution = compute_no_slip_candidate(
        state=state,
        τ_eng=τ_eng,
        τ_load=τ_load,
        I_p=self.I_p,
        I_s=self.I_s,
        m_b=self.m_b,
    )

    # Find bounds on this no slip solution
    torque_admissibility_result = self.torque_admissibility_solver.get_breakdown(
        state=state,
        no_slip=no_slip_solution,
    )

    # Compute relative speeds and slip directions
    primary_relative_speed, secondary_relative_speed = self._relative_contact_speeds(state)
    primary_slip_direction = self._slip_direction(
        relative_speed=primary_relative_speed,
        tau_ns=no_slip_solution.tau_p_ns,
        lower_bound=torque_admissibility_result.primary_tau_p_stick_lower,
        upper_bound=torque_admissibility_result.primary_tau_p_stick_upper,
    )
    secondary_slip_direction = self._slip_direction(
        relative_speed=secondary_relative_speed,
        tau_ns=no_slip_solution.tau_s_ns,
        lower_bound=torque_admissibility_result.secondary_tau_stick_lower,
        upper_bound=torque_admissibility_result.secondary_tau_stick_upper,
    )

    return SlipMetricsResult(
        primary_relative_speed=primary_relative_speed,
        secondary_relative_speed=secondary_relative_speed,
        primary_slip_direction=primary_slip_direction,
        secondary_slip_direction=secondary_slip_direction,
        admissibility=torque_admissibility_result,
        no_slip=no_slip_solution,
    )

  def _relative_contact_speeds(self, state: SystemState) -> tuple[float, float]:
    """Return the contact relative speeds"""
    s = state.s
    primary_relative_speed = self.cvt.primary_effective_radius(s) * state.ω_p - state.v_b
    secondary_relative_speed = state.v_b - self.cvt.secondary_effective_radius(s) * state.ω_s
    return primary_relative_speed, secondary_relative_speed

  def _slip_direction(
      self,
      relative_speed: float,
      tau_ns: float,
      lower_bound: float,
      upper_bound: float,
  ) -> float:
      # When the contact is moving faster than the stick threshold, direction is set by the
      # sign of the relative speed; otherwise it falls back to the torque bounds.
      if abs(relative_speed) > BELT_STICK_SPEED_THRESHOLD:
          # Return sign of relative speed for slip direction
          return 1.0 if relative_speed > 0 else -1.0

      if tau_ns > upper_bound:
          return 1.0
      if tau_ns < lower_bound:
          return -1.0
      return 0.0


