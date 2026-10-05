"""Small renderer inputs, resolved by CINDER without running a simulation."""

from .common import ApiModel


class MechanismPose(ApiModel):
    shift_m: float
    primary_roller_m: tuple[float, float] | None
    primary_ramp_shift_m: float
    secondary_axial_position_m: float
    secondary_angle_rad: float


class FlyweightScene(ApiModel):
    count: int
    pivot_m: tuple[float, float]
    roller_radius_m: float
    roller_side_sign: int
    ramp_points_m: list[tuple[float, float]]


class MechanismScene(ApiModel):
    primary: FlyweightScene | None
    primary_has_spring: bool
    secondary_has_spring: bool
    secondary_helix_points_m: list[tuple[float, float, float]]
    poses: list[MechanismPose]


class SceneGeometry(ApiModel):
    mechanisms: MechanismScene | None = None
    belt_outer_width_m: float
    belt_inner_width_m: float
    belt_height_m: float
    cord_depth_from_outer_m: float
    sheave_half_angle_rad: float
    center_distance_m: float
    primary_outer_radius_min_m: float
    primary_outer_radius_max_m: float
    secondary_outer_radius_min_m: float
    secondary_outer_radius_max_m: float
    deadzone_shift_m: float
    max_shift_m: float


class SceneFrame(ApiModel):
    shift_m: float
    primary_outer_radius_m: float
    secondary_outer_radius_m: float
    belt_axial_position_m: float
    belt_path_m: list[tuple[float, float]]
    belt_regions: list[str]


class ScenePreview(ApiModel):
    geometry: SceneGeometry
    frames: list[SceneFrame]
