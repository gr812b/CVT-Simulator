"""Stable external conventions and quantity descriptions for CINDER.

CINDER's mechanics use SI values.  This module is the intentionally small
public metadata layer consumed by saved documents, API adapters, study
projections, and generic user interfaces.  Nothing in ``cinder.model`` or
``cinder.execution`` imports it.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

PUBLIC_CONTRACT_VERSION = 1


@dataclass(frozen=True, slots=True)
class PublicFieldDescriptor:
    """Stable metadata for one scalar, table column, or report signal.

    ``key`` is a programmatic result/signal key.  ``unit`` is the canonical
    unit carried on the wire; it is always SI for physical values emitted by
    CINDER.  ``dimension`` lets a caller select a display unit without parsing
    a key suffix or recreating a CVT-specific conversion registry.
    """

    key: str
    label: str
    unit: str
    dimension: str
    description: str = ""

    def as_dict(self) -> dict[str, str]:
        return {
            "key": self.key,
            "label": self.label,
            "unit": self.unit,
            "canonical_unit": self.unit,
            "dimension": self.dimension,
            "description": self.description,
        }


@dataclass(frozen=True, slots=True)
class PublicConventions:
    """Readable conventions frozen for public CINDER consumers."""

    contract_version: int = PUBLIC_CONTRACT_VERSION
    canonical_unit_system: str = "SI"
    ratio_definition: str = (
        "effective secondary radius divided by effective primary radius"
    )
    ratio_direction: str = (
        "ratio greater than one is a reduction; increasing global shift reduces the ratio"
    )
    shift_coordinate: str = "global shift increases primary closure and primary radius"
    clamping_force_sign: str = "positive local axial force closes the mounted pulley"
    torque_sign: str = (
        "positive shaft torque acts in the forward modeled rotation direction"
    )
    report_grid: str = (
        "high-level simulation results use a 10 ms uniform reporting grid by default; "
        "raw adaptive trace remains available"
    )

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


# Exact descriptions for recurring cross-study quantities.  Unknown keys stay
# legal: callers still receive deterministic labels, units, and dimensions.
# Tuple layout: label, unit, dimension, description.
_EXACT: dict[str, tuple[str, str, str, str]] = {
    "ratio": (
        "CVT ratio",
        "1",
        "dimensionless",
        "Effective secondary radius divided by effective primary radius.",
    ),
    "ratio_span": (
        "Ratio span",
        "1",
        "dimensionless",
        "Maximum CVT ratio divided by minimum CVT ratio.",
    ),
    "feasible_mask": (
        "Geometrically feasible",
        "bool",
        "boolean",
        "True where the sampled geometry is physically valid.",
    ),
    "implied_belt_outer_length_m": (
        "Implied belt outer length",
        "m",
        "length",
        "Belt length implied by a radius-plane point.",
    ),
    "ratio_change_per_m_shift": (
        "Ratio change per shift travel",
        "1/m",
        "inverse_length",
        "Geometric dR/ds.",
    ),
    "total_clamping_force_N": (
        "Total clamping force",
        "N",
        "force",
        "Resolved mounted-actuator clamping force.",
    ),
    "total_bias_force_N": (
        "Total clamping bias force",
        "N",
        "force",
        "Actuator force with affine closure unknowns set to zero.",
    ),
    "time_s": ("Time", "s", "time", "Elapsed simulation time."),
    "friction_coefficient": (
        "Friction coefficient",
        "1",
        "dimensionless",
        "Belt--pulley friction coefficient.",
    ),
    "rolling_resistance_coefficient": (
        "Rolling resistance coefficient",
        "1",
        "dimensionless",
        "Road rolling-resistance coefficient.",
    ),
    "drag_coefficient": (
        "Drag coefficient",
        "1",
        "dimensionless",
        "Aerodynamic drag coefficient.",
    ),
    "reduction_ratio": (
        "Final-drive reduction ratio",
        "1",
        "dimensionless",
        "Secondary angular speed divided by wheel angular speed.",
    ),
    "optimizer_tolerance": (
        "Optimizer tolerance",
        "1",
        "dimensionless",
        "Nonlinear contact solver tolerance.",
    ),
    "relative_tolerance": (
        "Relative tolerance",
        "1",
        "dimensionless",
        "Adaptive integration relative tolerance.",
    ),
    "absolute_tolerance": (
        "Absolute tolerance",
        "1",
        "dimensionless",
        "Adaptive integration absolute tolerance.",
    ),
    "stick_exit_static_margin": (
        "Stick exit static margin",
        "1",
        "dimensionless",
        "Static traction reserve required to remain sticking.",
    ),
    "restick_static_margin": (
        "Restick static margin",
        "1",
        "dimensionless",
        "Static traction reserve required to reattach a contact.",
    ),
}

# Ordered longest-first so a compound unit wins over a suffix such as ``_N``.
# Tuple layout: suffix, unit, dimension.
_SUFFIX_METADATA: tuple[tuple[str, str, str], ...] = (
    ("_kg_per_m3", "kg/m³", "density"),
    ("_kg_m2", "kg·m²", "rotational_inertia"),
    ("_N_per_rad_per_s2", "N/(rad/s²)", "force_per_angular_acceleration"),
    ("_N_per_m_per_s2", "N/(m/s²)", "mass"),
    ("_N_per_Nm", "N/(N·m)", "inverse_length"),
    ("_Nm_per_rad", "N·m/rad", "torsional_stiffness"),
    ("_N_per_m", "N/m", "linear_stiffness"),
    ("_rad_per_s2", "rad/s²", "angular_acceleration"),
    ("_m_per_s2", "m/s²", "acceleration"),
    ("_rad_per_s", "rad/s", "angular_speed"),
    ("_m_per_s", "m/s", "speed"),
    ("_per_m", "1/m", "inverse_length"),
    ("_dimensionless", "1", "dimensionless"),
    ("_Nm", "N·m", "torque"),
    ("_N", "N", "force"),
    ("_W", "W", "power"),
    ("_J", "J", "energy"),
    ("_kg", "kg", "mass"),
    ("_m2", "m²", "area"),
    ("_m", "m", "length"),
    ("_rad", "rad", "angle"),
    ("_s", "s", "time"),
)


def public_conventions() -> PublicConventions:
    """Return CINDER's stable external conventions."""

    return PublicConventions()


def describe_public_field(
    key: str,
    *,
    unit: str | None = None,
    label: str | None = None,
    dimension: str | None = None,
) -> PublicFieldDescriptor:
    """Describe one public value without a frontend-owned CVT registry.

    Existing report signals may already carry a label and SI unit.  Static
    study columns are intentionally compact unit-bearing keys, so this helper
    fills the same metadata for either source.
    """

    if not isinstance(key, str) or not key.strip():
        raise ValueError("key must be a non-empty string.")
    if label is not None and not label.strip():
        raise ValueError("label must be non-empty when supplied.")
    if unit is not None and not unit.strip():
        raise ValueError("unit must be non-empty when supplied.")
    if dimension is not None and not dimension.strip():
        raise ValueError("dimension must be non-empty when supplied.")

    exact = _EXACT.get(key)
    if exact is not None:
        inferred_label, inferred_unit, inferred_dimension, description = exact
    else:
        inferred_label = _humanize(key)
        inferred_unit, inferred_dimension = _infer_metadata(key)
        description = ""

    return PublicFieldDescriptor(
        key=key,
        label=label or inferred_label,
        unit=unit or inferred_unit,
        dimension=dimension or inferred_dimension,
        description=description,
    )


def _infer_metadata(key: str) -> tuple[str, str]:
    for suffix, unit, dimension in _SUFFIX_METADATA:
        if key.endswith(suffix):
            return unit, dimension
    if key.endswith("_mask"):
        return "bool", "boolean"
    if "ratio" in key or "lambda" in key or "margin" in key:
        return "1", "dimensionless"
    return "1", "dimensionless"


def _humanize(key: str) -> str:
    # Preserve the stable key while offering ordinary wording.  Products are
    # free to override labels but never have to parse a unit suffix themselves.
    text = key.replace(".", " ").replace("_", " ")
    for suffix, _unit, _dimension in _SUFFIX_METADATA:
        plain = suffix[1:].replace("_", " ")
        if text.endswith(" " + plain):
            text = text[: -(len(plain) + 1)]
            break
    return " ".join(word.capitalize() for word in text.split())
