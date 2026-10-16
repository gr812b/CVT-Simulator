"""Numerical resolution shared by mechanism-specific contact checks."""

from sys import float_info


def contact_roundoff_tolerance(calculation_scale: float) -> float:
    """CINDER's roundoff convention, scaled by the arithmetic being resolved.

    This is not a physical contact-force threshold. Callers supply a scale in
    the same units as their force or impulse calculation, including any
    amplification from resolving the contact directions.
    """
    return 4096.0 * float_info.epsilon * max(1.0, calculation_scale)
