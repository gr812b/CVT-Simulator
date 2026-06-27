from __future__ import annotations

from .types import (
    AxialForceLaw,
    PulleyActuationResult,
    PulleyActuationState,
)


class PulleyActuator:
    """
    Combine force-producing mechanisms for one pulley.

    Every mechanism returns:

        F_i = bias_i + gain_i * pulley_torque.

    This class sums those local relations without knowing whether it represents
    the primary or secondary pulley.
    """

    def __init__(self, *force_laws: AxialForceLaw) -> None:
        self._force_laws = tuple(force_laws)

    @property
    def force_laws(self) -> tuple[AxialForceLaw, ...]:
        return self._force_laws

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
