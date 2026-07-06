"""Stable public conventions and numeric-column descriptions for CINDER.

The mechanics model remains SI internally.  This module is intentionally a
small boundary layer for callers that need stable keys, units, and human-facing
labels without coupling to CINDER's internal class layout.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

PUBLIC_CONTRACT_VERSION = 1


@dataclass(frozen=True, slots=True)
class PublicFieldDescriptor:
    """Stable metadata for one public scalar, table column, or signal."""

    key: str
    label: str
    unit: str
    description: str = ""

    def as_dict(self) -> dict[str, str]:
        return {
            "key": self.key,
            "label": self.label,
            "unit": self.unit,
            "description": self.description,
        }


@dataclass(frozen=True, slots=True)
class PublicConventions:
    """Readable conventions intentionally frozen for external consumers."""

    contract_version: int = PUBLIC_CONTRACT_VERSION
    canonical_unit_system: str = "SI"
    ratio_definition: str = "effective secondary radius divided by effective primary radius"
    ratio_direction: str = "ratio greater than one is a reduction; increasing global shift reduces the ratio"
    shift_coordinate: str = "global shift increases primary closure and primary radius"
    clamping_force_sign: str = "positive local axial force closes the mounted pulley"
    torque_sign: str = "positive shaft torque acts in the forward modeled rotation direction"
    report_grid: str = "high-level simulation results use a 10 ms uniform reporting grid by default; raw adaptive trace remains available"

    def as_dict(self) -> dict[str, Any]:
        return {
            "contract_version": self.contract_version,
            "canonical_unit_system": self.canonical_unit_system,
            "ratio": {
                "definition": "R = r_secondary_effective / r_primary_effective",
                "direction": self.ratio_direction,
            },
            "shift_coordinate": self.shift_coordinate,
            "clamping_force_sign": self.clamping_force_sign,
            "torque_sign": self.torque_sign,
            "report_grid": self.report_grid,
        }


# Exact descriptions for the recurring cross-study quantities.  Unknown keys
# remain legal: callers still receive a deterministic label and inferred unit.
_EXACT: dict[str, tuple[str, str, str]] = {
    "ratio": ("CVT ratio", "1", "Effective secondary radius divided by effective primary radius."),
    "ratio_span": ("Ratio span", "1", "Maximum CVT ratio divided by minimum CVT ratio."),
    "feasible_mask": ("Geometrically feasible", "bool", "True where the sampled geometry is physically valid."),
    "implied_belt_outer_length_m": ("Implied belt outer length", "m", "Belt length implied by a radius-plane point."),
    "ratio_change_per_m_shift": ("Ratio change per shift travel", "1/m", "Geometric dR/ds."),
    "ratio_change_per_mm_shift": ("Ratio change per millimetre of shift", "1/mm", "Geometric ratio change for one millimetre of global shift."),
    "total_clamping_force_N": ("Total clamping force", "N", "Resolved mounted-actuator clamping force."),
    "total_bias_force_N": ("Total clamping bias force", "N", "Actuator force with affine closure unknowns set to zero."),
}

_SUFFIX_UNITS: tuple[tuple[str, str], ...] = (
    ("_N_per_rad_per_s2", "N/(rad/s²)"),
    ("_N_per_m_per_s2", "N/(m/s²)"),
    ("_N_per_Nm", "N/(N·m)"),
    ("_kg_m2", "kg·m²"),
    ("_rad_per_s2", "rad/s²"),
    ("_m_per_s2", "m/s²"),
    ("_rad_per_s", "rad/s"),
    ("_m_per_s", "m/s"),
    ("_per_mm", "1/mm"),
    ("_per_m", "1/m"),
    ("_dimensionless", "1"),
    ("_Nm", "N·m"),
    ("_rpm", "rpm"),
    ("_N", "N"),
    ("_W", "W"),
    ("_J", "J"),
    ("_kg", "kg"),
    ("_mm", "mm"),
    ("_m", "m"),
    ("_rad", "rad"),
    ("_s", "s"),
)


def public_conventions() -> PublicConventions:
    """Return CINDER's stable external conventions."""

    return PublicConventions()


def describe_public_field(key: str, *, unit: str | None = None, label: str | None = None) -> PublicFieldDescriptor:
    """Describe one public numeric key without requiring a frontend registry.

    Existing report signals already carry explicit label/unit values.  Static
    study columns are intentionally compact unit-bearing keys, so this helper
    supplies metadata for them when projecting values to JSON.
    """

    if not isinstance(key, str) or not key.strip():
        raise ValueError("key must be a non-empty string.")
    if label is not None and not label.strip():
        raise ValueError("label must be non-empty when supplied.")
    if unit is not None and not unit.strip():
        raise ValueError("unit must be non-empty when supplied.")

    exact = _EXACT.get(key)
    inferred_label, inferred_unit, description = (
        exact if exact is not None else (_humanize(key), _infer_unit(key), "")
    )
    return PublicFieldDescriptor(
        key=key,
        label=label or inferred_label,
        unit=unit or inferred_unit,
        description=description,
    )


def _infer_unit(key: str) -> str:
    for suffix, unit in _SUFFIX_UNITS:
        if key.endswith(suffix):
            return unit
    if key.endswith("_mask"):
        return "bool"
    if "ratio" in key or "lambda" in key or "margin" in key:
        return "1"
    return "1"


def _humanize(key: str) -> str:
    # Preserve the actual stable key while offering an intentionally ordinary
    # label.  UIs are free to override this with product wording.
    text = key.replace(".", " ").replace("_", " ")
    for suffix, _unit in _SUFFIX_UNITS:
        plain = suffix[1:].replace("_", " ")
        if text.endswith(" " + plain):
            text = text[: -(len(plain) + 1)]
            break
    return " ".join(word.capitalize() for word in text.split())
