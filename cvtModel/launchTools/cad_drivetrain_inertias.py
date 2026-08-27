"""CAD drivetrain inertia source-of-truth for the Baja default.

Values in this module are transcribed from the user-supplied workbook
``Drivetrain Inertias.xlsx`` (2026-08-27).  The workbook itself warns that its
effective-mass columns are highly simplified, so CINDER uses only the raw CAD
moments of inertia and the speed-multiplier chain here.

Reference speed:
    CV05 / wheel-side output speed = 1

The workbook therefore implies:
    secondary-CVT speed / output speed = 13.44

The route model uses the raw component MOIs and performs its own exact
reflection into the secondary boundary.
"""

from __future__ import annotations

from dataclasses import dataclass

# ---------------------------------------------------------------------------
# Raw CAD values from the workbook
# ---------------------------------------------------------------------------

PCVT_TOTAL_MOI_KG_M2 = 0.00491861
SCVT_TOTAL_MOI_KG_M2 = 0.00484016

SECONDARY_TO_OUTPUT_RATIO = 13.44
PRIMARY_TO_OUTPUT_REFERENCE_RATIO = 6.72

RGS1_MOI_KG_M2 = 0.00005430
RGS1_SPEED_MULT = 13.44

RGS2_MOI_KG_M2 = 0.00018140
RGS2_SPEED_MULT = 3.733333333

RGS3_MOI_KG_M2 = 0.00005854
RGS3_SPEED_MULT = 3.733333333

DC03_MOI_KG_M2 = 0.00000508
DC03_SPEED_MULT = 3.733333333

DC01_MOI_KG_M2 = 0.00001498
DC01_SPEED_MULT = 3.733333333

RGS4_MOI_KG_M2 = 0.00093855
RGS4_SPEED_MULT = 1.0

CV05_MOI_KG_M2 = 0.00054824
CV05_SPEED_MULT = 1.0

CV01_MOI_KG_M2 = 0.00031261
CV01_COUNT = 2
CV01_SPEED_MULT = 1.0

BR02_MOI_KG_M2 = 0.001043
BR02_SPEED_MULT = 1.0

CV_AXLE_MOI_KG_M2 = 0.00505749
CV_AXLE_COUNT = 2
CV_AXLE_SPEED_MULT = 1.0

WHEEL_HUB_MOI_KG_M2 = 0.02203285
WHEEL_HUB_COUNT = 4
WHEEL_HUB_SPEED_MULT = 1.0

WHEEL_MOI_KG_M2 = 0.27695436
WHEEL_COUNT = 4
WHEEL_SPEED_MULT = 1.0

TOTAL_WHEEL_ROTATIONAL_INERTIA_KG_M2 = (
    WHEEL_MOI_KG_M2 * WHEEL_COUNT
)

# ---------------------------------------------------------------------------
# Secondary-CVT split required by the helix model
# ---------------------------------------------------------------------------

# The supplied workbook gives the complete SCVT rotational inertia but does not
# split fixed-side and movable-sheave inertia.  CINDER needs the movable part
# separately because it rotates relative to the shaft through the helix.
#
# 0.0025139 kg m^2 is the existing project/CAD movable-sheave estimate already
# used by CINDER.  It is retained only as the decomposition of the CAD total,
# NOT added on top of the workbook total.  The fixed-side remainder is solved
# so that:
#
#   fixed + movable == SCVT_TOTAL_MOI_KG_M2
#
# If a separately measured movable-sheave CAD value becomes available, replace
# this one number and the total remains constrained by the workbook value.
SCVT_MOVABLE_SHEAVE_MOI_KG_M2 = 0.0025139
SCVT_FIXED_SIDE_MOI_KG_M2 = (
    SCVT_TOTAL_MOI_KG_M2
    - SCVT_MOVABLE_SHEAVE_MOI_KG_M2
)

if SCVT_FIXED_SIDE_MOI_KG_M2 < 0.0:
    raise RuntimeError(
        "Movable SCVT inertia exceeds the supplied total SCVT CAD inertia."
    )

# ---------------------------------------------------------------------------
# Engine equivalent inertia
# ---------------------------------------------------------------------------

# User-supplied flywheel estimate: about 0.025--0.055 kg m^2, plus crankshaft
# and other engine-side rotating parts.  0.050 kg m^2 is used as a central
# total equivalent inertia rather than the old arbitrary 0.100 kg m^2.
#
# Keep the sensitivity range visible for later result robustness checks.
ENGINE_EQUIVALENT_INERTIA_DEFAULT_KG_M2 = 0.050
ENGINE_EQUIVALENT_INERTIA_LOW_KG_M2 = 0.035
ENGINE_EQUIVALENT_INERTIA_HIGH_KG_M2 = 0.070


@dataclass(frozen=True, slots=True)
class CadRotatingComponent:
    name: str
    inertia_kg_m2: float
    speed_multiplier_from_output: float
    count: int = 1

    @property
    def inertia_reflected_to_secondary_kg_m2(self) -> float:
        ratio = (
            self.speed_multiplier_from_output
            / SECONDARY_TO_OUTPUT_RATIO
        )
        return self.count * self.inertia_kg_m2 * ratio**2


DOWNSTREAM_NONWHEEL_COMPONENTS = (
    CadRotatingComponent("RGS1", RGS1_MOI_KG_M2, RGS1_SPEED_MULT),
    CadRotatingComponent("RGS2", RGS2_MOI_KG_M2, RGS2_SPEED_MULT),
    CadRotatingComponent("RGS3", RGS3_MOI_KG_M2, RGS3_SPEED_MULT),
    CadRotatingComponent("DC03", DC03_MOI_KG_M2, DC03_SPEED_MULT),
    CadRotatingComponent("DC01", DC01_MOI_KG_M2, DC01_SPEED_MULT),
    CadRotatingComponent("RGS4", RGS4_MOI_KG_M2, RGS4_SPEED_MULT),
    CadRotatingComponent("CV05", CV05_MOI_KG_M2, CV05_SPEED_MULT),
    CadRotatingComponent(
        "CV01",
        CV01_MOI_KG_M2,
        CV01_SPEED_MULT,
        CV01_COUNT,
    ),
    CadRotatingComponent("BR02", BR02_MOI_KG_M2, BR02_SPEED_MULT),
    CadRotatingComponent(
        "CV Axle",
        CV_AXLE_MOI_KG_M2,
        CV_AXLE_SPEED_MULT,
        CV_AXLE_COUNT,
    ),
    CadRotatingComponent(
        "Wheel Hub",
        WHEEL_HUB_MOI_KG_M2,
        WHEEL_HUB_SPEED_MULT,
        WHEEL_HUB_COUNT,
    ),
)

DOWNSTREAM_NONWHEEL_INERTIA_REFLECTED_TO_SECONDARY_KG_M2 = sum(
    item.inertia_reflected_to_secondary_kg_m2
    for item in DOWNSTREAM_NONWHEEL_COMPONENTS
)


def inertia_manifest() -> dict[str, object]:
    return {
        "source": "Drivetrain Inertias.xlsx",
        "pcvt_total_kg_m2": PCVT_TOTAL_MOI_KG_M2,
        "scvt_total_kg_m2": SCVT_TOTAL_MOI_KG_M2,
        "scvt_movable_kg_m2": SCVT_MOVABLE_SHEAVE_MOI_KG_M2,
        "scvt_fixed_remainder_kg_m2": SCVT_FIXED_SIDE_MOI_KG_M2,
        "secondary_to_output_ratio": SECONDARY_TO_OUTPUT_RATIO,
        "wheel_total_kg_m2": TOTAL_WHEEL_ROTATIONAL_INERTIA_KG_M2,
        "downstream_nonwheel_reflected_to_secondary_kg_m2": (
            DOWNSTREAM_NONWHEEL_INERTIA_REFLECTED_TO_SECONDARY_KG_M2
        ),
        "engine_default_kg_m2": ENGINE_EQUIVALENT_INERTIA_DEFAULT_KG_M2,
        "engine_sensitivity_kg_m2": [
            ENGINE_EQUIVALENT_INERTIA_LOW_KG_M2,
            ENGINE_EQUIVALENT_INERTIA_HIGH_KG_M2,
        ],
        "downstream_nonwheel_components": [
            {
                "name": item.name,
                "raw_moi_kg_m2": item.inertia_kg_m2,
                "count": item.count,
                "speed_multiplier_from_output": (
                    item.speed_multiplier_from_output
                ),
                "reflected_to_secondary_kg_m2": (
                    item.inertia_reflected_to_secondary_kg_m2
                ),
            }
            for item in DOWNSTREAM_NONWHEEL_COMPONENTS
        ],
    }
