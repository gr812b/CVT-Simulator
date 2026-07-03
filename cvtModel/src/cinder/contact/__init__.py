"""Shared engaged-contact definitions, contact laws, and lambda semantics."""

from .lambda_law import (
    ContactTractionLaw,
    SignedLambdaInterval,
    StaticLambdaAssessment,
)
from .mode import EngagedContactMode
from .relative_motion import (
    ContactInterface,
    ContactRelativeMotion,
    SlipDirection,
    evaluate_contact_relative_motion,
    infer_slip_direction,
)
from .slip import KineticSlipSpecification
from .tolerances import ContactKinematicTolerances
from .utilization import ContactTractionUtilization

__all__ = [
    "ContactInterface",
    "ContactKinematicTolerances",
    "ContactRelativeMotion",
    "ContactTractionLaw",
    "ContactTractionUtilization",
    "EngagedContactMode",
    "KineticSlipSpecification",
    "SignedLambdaInterval",
    "SlipDirection",
    "StaticLambdaAssessment",
    "evaluate_contact_relative_motion",
    "infer_slip_direction",
]
