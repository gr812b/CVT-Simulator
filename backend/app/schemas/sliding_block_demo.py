"""Read-only geometry and CINDER poses for the sliding-block sample."""

from pydantic import BaseModel, ConfigDict

Point = tuple[float, float]  # radial, axial, metres


class SlidingBlockDemoFrame(BaseModel):
    model_config = ConfigDict(frozen=True)

    closure_m: float
    datum_m: Point
    com_m: Point
    fixed_contact_m: Point
    # Entire conformal face, not a uniquely located pressure resultant.
    moving_contact_span_m: tuple[Point, Point]
    fixed_normal: Point
    moving_normal: Point
    fixed_reaction_N: float
    moving_reaction_N: float
    closing_force_N: float
    belt_section_m: list[Point]


class SlidingBlockDemoResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    sample_id: str
    cinder_version: str
    name: str
    description: str
    simulation_ready: bool
    rpm: float
    travel_m: float
    total_mass_kg: float
    block_count: int
    block_width_m: float
    block_outline_m: list[Point]
    cup_section_m: list[Point]
    cup_track_m: list[Point]
    moving_section_m: list[Point]
    moving_track_m: list[Point]
    fixed_section_m: list[Point]
    shaft_radius_m: float
    shaft_limits_m: Point  # axial endpoints, metres
    frames: list[SlidingBlockDemoFrame]
