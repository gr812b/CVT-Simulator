"""Source-constrained reconstruction of Ballew's primary-speed PI controller."""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite, pi
from typing import Any, Mapping, Sequence

import numpy as np
from numpy.typing import NDArray

from cinder.core import StateBlock
from cinder.execution.hybrid.hybrid import HybridEvent, HybridTransition
from cinder.model.cvt.actuation import PulleyActuationContext
from cinder.model.cvt.closure import AffineClosureScalar
from cinder.model.system import CVTShaftBoundaryValues, CVTState

from .constants import PUBLISHED, RECONSTRUCTED_CONTROLLER_FEED_FORWARD_FORCE_N

RPM_PER_RAD_PER_S = 60.0 / (2.0 * pi)


@dataclass(slots=True)
class ControllerIntegralBridge:
    error_integral_rpm_s: float = 0.0

    def set(self, value: float) -> None:
        value = float(value)
        if not isfinite(value):
            raise ValueError("controller integral state must be finite.")
        self.error_integral_rpm_s = value


@dataclass(frozen=True, slots=True)
class BallewPIControllerAxialForce:
    bridge: ControllerIntegralBridge
    target_rpm: float = PUBLISHED.initial_input_rpm
    proportional_gain: float = PUBLISHED.proportional_gain
    integral_gain: float = PUBLISHED.integral_gain
    feed_forward_force_n: float = RECONSTRUCTED_CONTROLLER_FEED_FORWARD_FORCE_N

    def force_from_state(
        self, *, primary_rpm: float, error_integral_rpm_s: float
    ) -> float:
        error_rpm = float(primary_rpm) - self.target_rpm
        return (
            self.feed_forward_force_n
            + self.proportional_gain * error_rpm
            + self.integral_gain * float(error_integral_rpm_s)
        )

    def evaluate(self, context: PulleyActuationContext) -> AffineClosureScalar:
        primary_rpm = context.shaft_speed * RPM_PER_RAD_PER_S
        force = self.force_from_state(
            primary_rpm=primary_rpm,
            error_integral_rpm_s=self.bridge.error_integral_rpm_s,
        )
        if not isfinite(force):
            raise FloatingPointError("Ballew PI controller produced non-finite clamp force.")
        return AffineClosureScalar(bias=force)


@dataclass(frozen=True, slots=True)
class BallewControllerHost:
    """Host state = secondary shaft angle + controller error integral."""

    bridge: ControllerIntegralBridge
    target_rpm: float = PUBLISHED.initial_input_rpm
    block_name: str = "host"

    @property
    def state_block(self) -> StateBlock:
        return StateBlock(self.block_name, 2)

    def initial_state(
        self,
        *,
        secondary_shaft_angle: float = 0.0,
        error_integral_rpm_s: float = 0.0,
    ) -> NDArray[np.float64]:
        self.bridge.set(error_integral_rpm_s)
        return np.asarray([secondary_shaft_angle, error_integral_rpm_s], dtype=float)

    def _sync_bridge(self, host_state: NDArray[np.float64]) -> None:
        self.bridge.set(float(host_state[1]))

    def context(
        self, *, time: float, cvt_state: CVTState, host_state: NDArray[np.float64]
    ) -> Mapping[str, Any]:
        del time, cvt_state
        self._sync_bridge(host_state)
        return {"secondary_shaft_angle": float(host_state[0])}

    def rhs(
        self,
        *,
        time: float,
        cvt_state: CVTState,
        host_state: NDArray[np.float64],
        shaft_boundaries: CVTShaftBoundaryValues,
    ) -> NDArray[np.float64]:
        del time, shaft_boundaries
        self._sync_bridge(host_state)
        primary_rpm = cvt_state.primary_angular_speed * RPM_PER_RAD_PER_S
        error_rpm = primary_rpm - self.target_rpm
        return np.asarray([cvt_state.secondary_angular_speed, error_rpm], dtype=float)

    def events(
        self,
        *,
        time: float,
        cvt_state: CVTState,
        host_state: NDArray[np.float64],
        shaft_boundaries: CVTShaftBoundaryValues,
    ) -> Sequence[HybridEvent]:
        del time, cvt_state, shaft_boundaries
        self._sync_bridge(host_state)
        return ()

    def transition(
        self,
        *,
        time: float,
        cvt_state: CVTState,
        host_state: NDArray[np.float64],
        shaft_boundaries: CVTShaftBoundaryValues,
        fired_event_names: tuple[str, ...],
    ) -> HybridTransition[Any] | None:
        del time, cvt_state, shaft_boundaries, fired_event_names
        self._sync_bridge(host_state)
        return None
