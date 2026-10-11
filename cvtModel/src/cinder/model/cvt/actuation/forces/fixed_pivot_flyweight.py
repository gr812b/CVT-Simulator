"""Dynamic force law for the fixed-pivot flyweight mechanism."""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from sys import float_info

from cinder.model.cvt.closure import ClosureUnknowns

from ..fixed_pivot_flyweight import (
    FixedPivotFlyweightInertiaMap,
    FixedPivotFlyweightMap,
)
from ..types import PulleyActuationContext
from .centrifugal_inertia import CentrifugalInertiaForce

# Match CINDER's existing roundoff guard convention used by impact and
# relative-motion consistency checks. This is a numerical resolution
# multiplier, not a physical force threshold.
_CONTACT_ROUNDOFF_MULTIPLIER = 4096.0


@dataclass(frozen=True, slots=True)
class FixedPivotFlyweightForceSpec:
    """The mechanism-specific ``q_f(x), J_f(x), I_f`` map."""

    mechanism_map: FixedPivotFlyweightMap

    def __post_init__(self) -> None:
        if not isinstance(self.mechanism_map, FixedPivotFlyweightMap):
            raise TypeError("mechanism_map must implement FixedPivotFlyweightMap.")


class FixedPivotFlyweightForce(CentrifugalInertiaForce):
    """Pulley-mounted fixed-pivot flyweight force and shaft coupling.

    For local pulley-closing coordinate ``x`` this element supplies

        F = 1/2 omega^2 J'(x)
            - I q'(x)^2 x_ddot
            - I q'(x) q''(x) x_dot^2,

    and the owning shaft receives the inertial reaction

        -J(x) alpha - J'(x) x_dot omega.

    The host context maps ``x_ddot`` into the shared shift-acceleration column,
    so the same class can be mounted on either pulley without named branches.
    Force, shaft reaction, and kinetic modes use the common inertia evaluator;
    the saved specification, inspection labels, and contact policy stay here.
    """

    _inspection_terms = (
        (
            "fixed_pivot_flyweight_centrifugal",
            "Fixed-pivot flyweight centrifugal drive",
        ),
        (
            "fixed_pivot_flyweight_axial_inertia",
            "Fixed-pivot flyweight reflected axial inertia",
        ),
        (
            "fixed_pivot_flyweight_motion_ratio_curvature",
            "Fixed-pivot flyweight motion-ratio curvature",
        ),
    )

    def __init__(self, spec: FixedPivotFlyweightForceSpec) -> None:
        if not isinstance(spec, FixedPivotFlyweightForceSpec):
            raise TypeError("spec must be a FixedPivotFlyweightForceSpec.")
        self._spec = spec
        super().__init__(FixedPivotFlyweightInertiaMap(spec.mechanism_map))

    @property
    def spec(self) -> FixedPivotFlyweightForceSpec:
        return self._spec

    def has_compressive_contact(
        self,
        *,
        context: PulleyActuationContext,
        unknowns: ClosureUnknowns,
        tolerance: float = 0.0,
    ) -> bool:
        """Return whether the solved ramp force is compressive.

        The affine closure is intentionally not clipped with ``max(0, F)``;
        doing so would hide a change of mechanism topology inside a smooth RHS.
        Callers can use this check as a diagnostic or event admissibility test.
        """

        if not isfinite(tolerance) or tolerance < 0.0:
            raise ValueError("tolerance must be finite and non-negative.")
        return (
            self.compressive_contact_margin(
                context=context,
                unknowns=unknowns,
            )
            >= -tolerance
        )

    def compressive_contact_margin(
        self,
        *,
        context: PulleyActuationContext,
        unknowns: ClosureUnknowns,
    ) -> float:
        """Return signed force carried by the selected roller/ramp branch.

        A force assembled from cancelling affine terms can land a few floating-
        point ulps below zero even when the exact reaction is zero. Snap only
        that arithmetic dust to zero using the same ``4096 * eps * scale``
        convention already used by CINDER's other consistency checks. The
        scale is the sum of absolute evaluated force contributions, so the
        tolerance follows the arithmetic being cancelled rather than imposing
        a fixed physical-force deadband.
        """

        raw_margin = float(self.evaluate(context).evaluate(unknowns))
        contribution_values = tuple(
            float(contribution.relation.evaluate(unknowns))
            for contribution in self.inspect(context)
        )
        calculation_scale = max(
            1.0,
            sum(abs(value) for value in contribution_values),
        )
        roundoff_tolerance = (
            _CONTACT_ROUNDOFF_MULTIPLIER * float_info.epsilon * calculation_scale
        )
        if abs(raw_margin) <= roundoff_tolerance:
            return 0.0
        return raw_margin
