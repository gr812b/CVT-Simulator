"""Torque-reactive secondary assembly."""

from __future__ import annotations

from dataclasses import dataclass

from .forces import (
    AxialSpringForce,
    AxialSpringForceSpec,
    SecondaryHelixForce,
    SecondaryHelixForceSpec,
)
from .types import PulleyActuationResult, PulleyActuationState


@dataclass(frozen=True, slots=True)
class TorqueReactiveSecondarySpec:
    """The standard secondary: local spring plus physical helix."""

    axial_spring: AxialSpringForceSpec
    helix: SecondaryHelixForceSpec


@dataclass(frozen=True, slots=True)
class TorqueReactiveSecondaryEvaluation:
    """
    Complete secondary result at one known-state evaluation.

    ``local_axial_force`` combines the secondary axial spring and helix
    relation. ``dtheta_ds`` and ``d2theta_ds2`` are retained alongside
    it so the secondary rotation row and shift row use the same helix
    kinematics.
    """

    local_axial_force: PulleyActuationResult
    theta: float
    dtheta_ds: float
    d2theta_ds2: float


class TorqueReactiveSecondary:
    """
    Evaluate the coupled local secondary actuation assembly.

    This is intentionally not a generic ``PulleyActuator``: the
    secondary helix contributes both local axial force and the global
    helix kinematics needed by the secondary rotational balance.
    """

    def __init__(
        self,
        *,
        spec: TorqueReactiveSecondarySpec,
        movable_sheave_rotational_inertia: float,
    ) -> None:
        self._spec = spec
        self._axial_spring = AxialSpringForce(spec.axial_spring)
        self._helix = SecondaryHelixForce(
            spec=spec.helix,
            movable_sheave_rotational_inertia=(
                movable_sheave_rotational_inertia
            ),
        )

    @property
    def spec(self) -> TorqueReactiveSecondarySpec:
        return self._spec

    @property
    def movable_sheave_rotational_inertia(self) -> float:
        """Return the one shared I_M used by this secondary."""

        return self._helix.movable_sheave_rotational_inertia

    def evaluate(
        self,
        state: PulleyActuationState,
    ) -> TorqueReactiveSecondaryEvaluation:
        spring_relation = self._axial_spring.evaluate(state)
        helix = self._helix.evaluate(state)

        local_relation = (
            spring_relation
            + helix.local_axial_force
        )

        return TorqueReactiveSecondaryEvaluation(
            local_axial_force=PulleyActuationResult(
                relation=local_relation,
            ),
            theta=helix.theta,
            dtheta_ds=helix.dtheta_ds,
            d2theta_ds2=helix.d2theta_ds2,
        )


def build_torque_reactive_secondary(
    *,
    spec: TorqueReactiveSecondarySpec,
    movable_sheave_rotational_inertia: float,
) -> TorqueReactiveSecondary:
    """
    Build the secondary from one actuation spec and the resolved I_M.

    Pass
    ``resolved_inertias.secondary.movable_sheave_rotational_inertia``
    here. No duplicate I_M belongs in ``SecondaryHelixForceSpec``.
    """

    return TorqueReactiveSecondary(
        spec=spec,
        movable_sheave_rotational_inertia=(
            movable_sheave_rotational_inertia
        ),
    )
