"""State-fixed and lambda-trial context for CINDER's current closure rows."""

from __future__ import annotations

from dataclasses import dataclass, field
from math import expm1, isfinite, tan

from .snapshot import DynamicsSnapshot
from .state import TrialFrictionUtilization


@dataclass(frozen=True, slots=True)
class TrialContactTerms:
    """Trial-lambda quantities shared by the two lambda-dependent rows.

    The values in this object are fixed for one pair ``(lambda_p, lambda_s)``
    and one state snapshot. They intentionally contain no solved closure
    unknowns. Caching them here means the shift row and closed-loop endpoint
    row use the exact same trial contact factors.

    Exact zero utilization is excluded for this first matrix layer because the
    current analytical equations contain explicit ``1 / lambda`` factors. The
    later lambda-root layer will decide how to treat the removable/degenerate
    zero-traction limit without hiding it inside a row builder.
    """

    primary_inverse_lambda: float
    secondary_inverse_lambda: float

    primary_shift_torque_coefficient: float
    secondary_shift_torque_coefficient: float

    endpoint_span_coefficient: float

    def __post_init__(self) -> None:
        for name, value in (
            ("primary_inverse_lambda", self.primary_inverse_lambda),
            ("secondary_inverse_lambda", self.secondary_inverse_lambda),
            (
                "primary_shift_torque_coefficient",
                self.primary_shift_torque_coefficient,
            ),
            (
                "secondary_shift_torque_coefficient",
                self.secondary_shift_torque_coefficient,
            ),
            ("endpoint_span_coefficient", self.endpoint_span_coefficient),
        ):
            if not isfinite(value):
                raise ValueError(f"{name} must be finite.")


@dataclass(frozen=True, slots=True)
class TrialEquationContext:
    """Everything needed by one trial-lambda evaluation of rows 1 and 6.

    ``DynamicsSnapshot`` contains all state-fixed mechanics. This context adds
    only the trial friction utilizations and the contact terms derived from
    them. The four rows that do not depend on lambda never need this object.
    """

    snapshot: DynamicsSnapshot
    friction_utilization: TrialFrictionUtilization
    contact_terms: TrialContactTerms = field(init=False)

    def __post_init__(self) -> None:
        if not isinstance(self.snapshot, DynamicsSnapshot):
            raise TypeError("snapshot must be a DynamicsSnapshot instance.")
        if not isinstance(self.friction_utilization, TrialFrictionUtilization):
            raise TypeError(
                "friction_utilization must be a TrialFrictionUtilization instance."
            )

        object.__setattr__(
            self,
            "contact_terms",
            _build_trial_contact_terms(
                snapshot=self.snapshot,
                friction_utilization=self.friction_utilization,
            ),
        )


def _build_trial_contact_terms(
    *,
    snapshot: DynamicsSnapshot,
    friction_utilization: TrialFrictionUtilization,
) -> TrialContactTerms:
    """Build stable shared contact factors for one lambda pair."""

    lambda_primary = friction_utilization.primary_lambda
    lambda_secondary = friction_utilization.secondary_lambda

    if lambda_primary == 0.0 or lambda_secondary == 0.0:
        raise ValueError(
            "Trial lambda values must be non-zero while the closure rows "
            "contain explicit 1/lambda factors."
        )

    primary_radius = snapshot.geometry.primary.effective
    secondary_radius = snapshot.geometry.secondary.effective
    primary_wrap = snapshot.geometry.primary_wrap_angle
    secondary_wrap = snapshot.geometry.secondary_wrap_angle

    tangent = tan(snapshot.sheave_half_angle)
    if not isfinite(tangent) or tangent <= 0.0:
        raise ValueError("sheave_half_angle must produce a positive finite tangent.")

    primary_exponent = lambda_primary * primary_wrap
    secondary_exponent = lambda_secondary * secondary_wrap

    # Endpoint compatibility uses the common slack-span tension:
    #
    #   1 / (1 - exp(x_p)) - 1 / (1 - exp(x_s))
    #     = -1 / expm1(x_p) + 1 / expm1(x_s).
    #
    # The secondary term has the opposite sign because its local wrap
    # coordinate is reversed relative to global belt travel. Using expm1
    # avoids avoidable cancellation away from the explicitly excluded
    # lambda = 0 limit.
    endpoint_span_coefficient = (
        -1.0 / expm1(primary_exponent)
        + 1.0 / expm1(secondary_exponent)
    )

    return TrialContactTerms(
        primary_inverse_lambda=1.0 / lambda_primary,
        secondary_inverse_lambda=1.0 / lambda_secondary,
        primary_shift_torque_coefficient=(
            1.0 / (2.0 * lambda_primary * primary_radius * tangent)
        ),
        secondary_shift_torque_coefficient=(
            1.0 / (2.0 * lambda_secondary * secondary_radius * tangent)
        ),
        endpoint_span_coefficient=endpoint_span_coefficient,
    )
