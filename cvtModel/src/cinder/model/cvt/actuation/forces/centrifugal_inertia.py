"""Common force, shaft reaction, and energy for a centrifugal inertia map."""

from __future__ import annotations

from math import isfinite

from cinder.model.cvt.closure import AffineClosureScalar, ClosureGains

from ..centrifugal_inertia import CentrifugalInertiaMap, CentrifugalInertiaSample
from ..types import (
    ActuationContribution,
    PulleyActuationContext,
    PulleyElementContribution,
    PulleyKineticMode,
)


class CentrifugalInertiaForce:
    """Mount a four-quantity inertia map on either pulley.

    For positive local closing displacement x, the mechanism supplies

        F = 1/2 J' omega^2 - M x_ddot - 1/2 M' x_dot^2,
        T_shaft,reaction = -J alpha - J' x_dot omega.

    The host supplies the affine local acceleration and owning shaft channel.
    Contact admissibility is mechanism-specific: this common evaluator does
    not infer a roller reaction from the sign of the net closing force.
    """

    _inspection_terms = (
        ("centrifugal_inertia_drive", "Centrifugal drive"),
        ("centrifugal_inertia_axial", "Centrifugal mechanism axial inertia"),
        (
            "centrifugal_inertia_mass_gradient",
            "Centrifugal mechanism effective-mass gradient",
        ),
    )

    def __init__(self, inertia_map: CentrifugalInertiaMap) -> None:
        if not isinstance(inertia_map, CentrifugalInertiaMap):
            raise TypeError("inertia_map must implement CentrifugalInertiaMap.")
        lower, upper = inertia_map.axial_position_min, inertia_map.axial_position_max
        if not isfinite(lower) or not isfinite(upper) or lower > upper:
            raise ValueError("The inertia-map interval must be finite and ordered.")
        self._inertia_map = inertia_map

    @property
    def inertia_map(self) -> CentrifugalInertiaMap:
        return self._inertia_map

    def _sample(self, context: PulleyActuationContext) -> CentrifugalInertiaSample:
        sample = self._inertia_map.evaluate(context.axial_position)
        if not isinstance(sample, CentrifugalInertiaSample):
            raise TypeError(
                "inertia_map.evaluate must return CentrifugalInertiaSample."
            )
        return sample

    def evaluate(self, context: PulleyActuationContext) -> AffineClosureScalar:
        """Return the axial force, preserving the host's acceleration gains."""

        return _closing_force(context, self._sample(context))

    def evaluate_element(
        self, context: PulleyActuationContext
    ) -> PulleyElementContribution:
        channels = context.closure_channels
        if channels is None:
            raise ValueError(
                "CentrifugalInertiaForce requires host closure_channels so its "
                "shaft inertia can enter the owning rotational balance."
            )
        sample = self._sample(context)
        return PulleyElementContribution(
            closing_force=_closing_force(context, sample),
            shaft_torque=AffineClosureScalar(
                bias=(
                    -sample.shaft_inertia_gradient
                    * context.axial_speed
                    * context.shaft_speed
                ),
                gains=ClosureGains.from_by_unknown(
                    {channels.shaft_angular_acceleration: -sample.shaft_inertia}
                ),
            ),
        )

    def kinetic_modes(
        self, context: PulleyActuationContext
    ) -> tuple[PulleyKineticMode, ...]:
        """Supply the same J and M to kinetic energy and event projection."""

        sample = self._sample(context)
        return (
            PulleyKineticMode(
                inertia=sample.shaft_inertia, shaft_speed_coefficient=1.0
            ),
            PulleyKineticMode(
                inertia=sample.effective_mass, axial_speed_coefficient=1.0
            ),
        )

    def inspect(
        self, context: PulleyActuationContext
    ) -> tuple[ActuationContribution, ...]:
        drive, inertia, gradient = _force_terms(context, self._sample(context))
        relations = (
            AffineClosureScalar.constant(drive),
            inertia,
            AffineClosureScalar.constant(gradient),
        )
        return tuple(
            ActuationContribution(key=key, label=label, relation=relation)
            for (key, label), relation in zip(self._inspection_terms, relations)
        )


def _force_terms(
    context: PulleyActuationContext, sample: CentrifugalInertiaSample
) -> tuple[float, AffineClosureScalar, float]:
    acceleration = context.axial_acceleration
    if acceleration is None:
        raise ValueError(
            "CentrifugalInertiaForce requires the host local axial-acceleration "
            "relation so effective mass can enter the coupled closure solve."
        )
    return (
        0.5 * context.shaft_speed**2 * sample.shaft_inertia_gradient,
        acceleration.scaled(-sample.effective_mass),
        -0.5 * sample.effective_mass_gradient * context.axial_speed**2,
    )


def _closing_force(
    context: PulleyActuationContext, sample: CentrifugalInertiaSample
) -> AffineClosureScalar:
    drive, inertia, gradient = _force_terms(context, sample)
    return AffineClosureScalar.constant(drive + gradient) + inertia
