"""Shared contact-regime definitions for CINDER's engaged belt interfaces."""

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

__all__ = [
    "ContactInterface",
    "ContactKinematicTolerances",
    "ContactRelativeMotion",
    "EngagedContactMode",
    "KineticSlipSpecification",
    "SlipDirection",
    "evaluate_contact_relative_motion",
    "infer_slip_direction",
]
