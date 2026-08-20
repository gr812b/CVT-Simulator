"""State-fixed and lambda-trial quantities for CINDER's 8x8 closure rows."""

from __future__ import annotations

from dataclasses import dataclass, field
from math import exp, expm1, isfinite, sin

from cinder.model.system.evaluator import DynamicsSnapshot
from cinder.model.cvt.contact import ContactTractionUtilization

_SMALL_ARGUMENT = 1.0e-4


@dataclass(frozen=True, slots=True)
class TrialContactTerms:
    """Regular fixed-lambda factors shared by traction and tension-loop rows.

    The normal-resultant formulation deliberately carries no ``1 / lambda``
    factors. For each wrap, it stores the regular functions

        Phi_-(z) = [1 - exp(-z)] / z,
        Psi_-(z) = [z - 1 + exp(-z)] / z^2,

    evaluated continuously at ``z = lambda phi / sin(beta) = 0``. This makes a clamped,
    zero-traction state well-defined:

        lambda = 0, tau = 0, N > 0.
    """

    primary_lambda: float
    secondary_lambda: float

    primary_exp_neg: float
    secondary_exp_neg: float

    primary_phi_minus: float
    primary_psi_minus: float
    secondary_phi_minus: float
    secondary_psi_minus: float

    def __post_init__(self) -> None:
        for name, value in (
            ("primary_lambda", self.primary_lambda),
            ("secondary_lambda", self.secondary_lambda),
            ("primary_exp_neg", self.primary_exp_neg),
            ("secondary_exp_neg", self.secondary_exp_neg),
            ("primary_phi_minus", self.primary_phi_minus),
            ("primary_psi_minus", self.primary_psi_minus),
            ("secondary_phi_minus", self.secondary_phi_minus),
            ("secondary_psi_minus", self.secondary_psi_minus),
        ):
            if not isfinite(value):
                raise ValueError(f"{name} must be finite.")

        for name, value in (
            ("primary_phi_minus", self.primary_phi_minus),
            ("secondary_phi_minus", self.secondary_phi_minus),
        ):
            if value == 0.0:
                raise ValueError(f"{name} must be non-zero.")


@dataclass(frozen=True, slots=True)
class TrialEquationContext:
    """Everything fixed for one trial signed ``(lambda_p, lambda_s)`` pair."""

    snapshot: DynamicsSnapshot
    traction_utilization: ContactTractionUtilization
    contact_terms: TrialContactTerms = field(init=False)

    def __post_init__(self) -> None:
        if not isinstance(self.snapshot, DynamicsSnapshot):
            raise TypeError("snapshot must be a DynamicsSnapshot instance.")
        if not isinstance(self.traction_utilization, ContactTractionUtilization):
            raise TypeError(
                "traction_utilization must be a ContactTractionUtilization instance."
            )

        object.__setattr__(
            self,
            "contact_terms",
            _build_trial_contact_terms(
                snapshot=self.snapshot,
                traction_utilization=self.traction_utilization,
            ),
        )


def _build_trial_contact_terms(
    *,
    snapshot: DynamicsSnapshot,
    traction_utilization: ContactTractionUtilization,
) -> TrialContactTerms:
    """Build finite wrap-map factors for one lambda pair."""

    lambda_primary = traction_utilization.primary_lambda
    lambda_secondary = traction_utilization.secondary_lambda

    sin_beta = sin(snapshot.sheave_half_angle)
    if not isfinite(sin_beta) or sin_beta <= 0.0:
        raise ValueError("sheave_half_angle must produce a positive finite sine.")

    # lambda is the physical signed Coulomb utilization in dF_t = lambda dN.
    # The V-groove radial projection therefore appears explicitly as sin(beta)
    # in the wrap ODE: dT/dtheta + (lambda/sin(beta)) T = ... .
    z_primary = (
        lambda_primary * snapshot.geometry.primary_wrap_angle / sin_beta
    )
    z_secondary = (
        lambda_secondary * snapshot.geometry.secondary_wrap_angle / sin_beta
    )

    return TrialContactTerms(
        primary_lambda=lambda_primary,
        secondary_lambda=lambda_secondary,
        primary_exp_neg=exp(-z_primary),
        secondary_exp_neg=exp(-z_secondary),
        primary_phi_minus=_phi_minus(z_primary),
        primary_psi_minus=_psi_minus(z_primary),
        secondary_phi_minus=_phi_minus(z_secondary),
        secondary_psi_minus=_psi_minus(z_secondary),
    )


def _phi_minus(z: float) -> float:
    """Return ``[1 - exp(-z)] / z`` with its continuous zero limit."""

    if abs(z) < _SMALL_ARGUMENT:
        return 1.0 - z / 2.0 + z**2 / 6.0 - z**3 / 24.0 + z**4 / 120.0
    return -expm1(-z) / z


def _psi_minus(z: float) -> float:
    """Return ``[z - 1 + exp(-z)] / z^2`` with its zero limit."""

    if abs(z) < _SMALL_ARGUMENT:
        return 0.5 - z / 6.0 + z**2 / 24.0 - z**3 / 120.0 + z**4 / 720.0
    return (z + expm1(-z)) / z**2
