"""Recover an illustrative tip mass from the uniform-arm mass moments."""

from math import isclose, isfinite


def flyweight_tip_mass_kg(component: dict) -> float | None:
    """Return the per-tip mass only when a uniform arm plus end mass fits.

    Scene requests carry the resolved assembly rather than a tune's metadata.
    With total mass M and first moment Q about a length-L arm's pivot, the
    equivalent end mass is 2Q/L - M. Check the second moment as well so arbitrary
    measured mass distributions retain the unscaled illustration. This does
    not alter the assembly's mass, moments, contact radius or solved motion.
    """
    length = component["geometry"]["arm_length_m"]
    mass = component["mass_geometry"]
    total = mass["mass_per_flyweight_kg"]
    first = mass["first_moment_u_kg_m"]
    second = mass["second_moment_u_kg_m2"]
    if not all(isfinite(value) for value in (length, total, first, second)):
        return None
    if length <= 0 or total <= 0:
        return None
    tip = 2 * first / length - total
    tolerance = total * 1e-8
    if tip < -tolerance or tip > total + tolerance:
        return None
    tip = min(total, max(0.0, tip))
    body = total - tip
    if not isclose(second, (body / 3 + tip) * length**2, rel_tol=1e-8, abs_tol=1e-12):
        return None
    if any(
        not isclose(mass.get(key, 0.0), 0.0, abs_tol=1e-12)
        for key in ("first_moment_v_kg_m", "second_moment_v_kg_m2", "product_moment_uv_kg_m2")
    ):
        return None
    return tip
