"""CAD inertia source values used directly by the Baja default.

Only physical inertias consumed by CINDER are transcribed here. Spreadsheet
bookkeeping that is not part of the vehicle/CVT model remains in the source
workbook and is intentionally not duplicated in code.
"""

from __future__ import annotations

# Complete CVT rotating-assembly CAD inertias.
PCVT_TOTAL_MOI_KG_M2 = 0.00491861
SCVT_TOTAL_MOI_KG_M2 = 0.00484016

# Secondary split required by the dynamic helix model. The movable value is the
# current project/CAD decomposition; the fixed-side remainder preserves the
# complete SCVT CAD total without double counting.
SCVT_MOVABLE_SHEAVE_MOI_KG_M2 = 0.0025139
SCVT_FIXED_SIDE_MOI_KG_M2 = (
    SCVT_TOTAL_MOI_KG_M2 - SCVT_MOVABLE_SHEAVE_MOI_KG_M2
)
if SCVT_FIXED_SIDE_MOI_KG_M2 < 0.0:
    raise RuntimeError(
        "Movable SCVT inertia exceeds the supplied total SCVT CAD inertia."
    )

# Four-wheel CAD total.
WHEEL_MOI_KG_M2 = 0.27695436
WHEEL_COUNT = 4
TOTAL_WHEEL_ROTATIONAL_INERTIA_KG_M2 = WHEEL_MOI_KG_M2 * WHEEL_COUNT

# Engine equivalent inertia central estimate and sensitivity bounds.
ENGINE_EQUIVALENT_INERTIA_DEFAULT_KG_M2 = 0.050
ENGINE_EQUIVALENT_INERTIA_LOW_KG_M2 = 0.035
ENGINE_EQUIVALENT_INERTIA_HIGH_KG_M2 = 0.070


def inertia_manifest() -> dict[str, object]:
    """Return the physical inertia values retained by the Baja default."""

    return {
        "source": "Drivetrain Inertias.xlsx",
        "pcvt_total_kg_m2": PCVT_TOTAL_MOI_KG_M2,
        "scvt_total_kg_m2": SCVT_TOTAL_MOI_KG_M2,
        "scvt_movable_kg_m2": SCVT_MOVABLE_SHEAVE_MOI_KG_M2,
        "scvt_fixed_remainder_kg_m2": SCVT_FIXED_SIDE_MOI_KG_M2,
        "wheel_total_kg_m2": TOTAL_WHEEL_ROTATIONAL_INERTIA_KG_M2,
        "engine_default_kg_m2": ENGINE_EQUIVALENT_INERTIA_DEFAULT_KG_M2,
        "engine_sensitivity_kg_m2": [
            ENGINE_EQUIVALENT_INERTIA_LOW_KG_M2,
            ENGINE_EQUIVALENT_INERTIA_HIGH_KG_M2,
        ],
    }
