# cinder/actuation/pulley_actuator.py

from cinder.actuation.types import (
    AxialForceLaw,
    PulleyActuationResult,
    PulleyActuationState,
)


class PulleyActuator:
    """
    Combines local force-producing mechanisms for one pulley.

    The returned relation is:

        axial_force = bias_force + torque_gain * pulley_torque
    """

    def __init__(self, *force_laws: AxialForceLaw) -> None:
        self._force_laws = force_laws

    def evaluate(
        self,
        state: PulleyActuationState,
    ) -> PulleyActuationResult:
        total_bias_force = 0.0
        total_torque_gain = 0.0

        for force_law in self._force_laws:
            contribution = force_law.force_relation(state)

            total_bias_force += contribution.bias_force
            total_torque_gain += contribution.torque_gain

        return PulleyActuationResult(
            bias_force=total_bias_force,
            torque_gain=total_torque_gain,
        )