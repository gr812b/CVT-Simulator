"""Wire contracts for engineering projections. Generated into TypeScript via OpenAPI.

These describe the existing engineering service output; no mechanics live here.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import ConfigDict, with_config
from typing_extensions import NotRequired, TypedDict

RampKind = Literal["progressive"] | Literal["constant"]

PackagingZoneSubject = Literal["flyweight"] | Literal["ramp"]

PackagingZoneRule = Literal["forbid"] | Literal["contain"]


@with_config(ConfigDict(extra="allow"))
class FixedPivotArchitecture(TypedDict):
    pivot_axial_position_m: float
    pivot_radius_m: float
    arm_length_m: float
    roller_radius_m: float
    required_travel_m: float
    number_of_flyweights: int
    arm_mass_per_flyweight_kg: float
    ramp_axial_direction: Literal[-1] | Literal[1]
    roller_side_sign: Literal[-1] | Literal[1]
    max_tip_mass_per_flyweight_kg: float


@with_config(ConfigDict(extra="allow"))
class PackagingZone(TypedDict):
    id: str
    label: str
    subject: PackagingZoneSubject
    rule: PackagingZoneRule
    polygon_m: list[tuple[float, float]]
    clearance_m: float


@with_config(ConfigDict(extra="allow"))
class FixedPivotRamp(TypedDict):
    kind: RampKind
    initial_flyweight_angle_deg: float
    linear_angle_deg: float
    circular_start_angle_deg: float
    circular_end_angle_deg: float
    constant_length_m: float
    linear_length_m: float
    blend_length_m: float
    circular_length_m: float


@with_config(ConfigDict(extra="allow"))
class PrimaryDesignOperating(TypedDict):
    tip_mass_per_flyweight_kg: float
    shaft_speed_rad_s: float
    shift_speed_m_s: float
    shift_acceleration_m_s2: float


@with_config(ConfigDict(extra="allow"))
class PrimaryDesignDefaultsUiLimits(TypedDict):
    tip_mass_per_flyweight_kg: tuple[float, float]
    shaft_speed_rad_s: tuple[float, float]


@with_config(ConfigDict(extra="allow"))
class PrimaryDesignDefaults(TypedDict):
    architecture: FixedPivotArchitecture
    ramp: FixedPivotRamp
    packaging_zones: list[PackagingZone]
    operating: PrimaryDesignOperating
    ui_limits: PrimaryDesignDefaultsUiLimits


@with_config(ConfigDict(extra="allow"))
class SampledFieldSet(TypedDict):
    axis_key: str
    axis_unit: str
    axis_values: list[float]
    units: dict[str, str]
    fields: dict[str, list[float | bool | None]]


@with_config(ConfigDict(extra="allow"))
class DoubleContactFailureGeometryContactsItem(TypedDict):
    label: Literal["C1"] | Literal["C2"]
    contact_coordinate_m: float
    x_m: float
    r_m: float


@with_config(ConfigDict(extra="allow"))
class DoubleContactFailureGeometry(TypedDict):
    kind: Literal["double_contact"]
    arm_angle_deg: float
    roller_center_x_m: float
    roller_center_r_m: float
    contacts: list[DoubleContactFailureGeometryContactsItem]


@with_config(ConfigDict(extra="allow"))
class DesignFailure(TypedDict):
    code: str
    message: str
    shift_m: float | None
    geometry: NotRequired[DoubleContactFailureGeometry]


@with_config(ConfigDict(extra="allow"))
class DesignWarning(TypedDict):
    code: str
    message: str
    shift_m: float | None
    detail: NotRequired[str]


@with_config(ConfigDict(extra="allow"))
class ConcreteDesignAnalysisValidity(TypedDict):
    valid: bool
    failure: DesignFailure | None
    warnings: list[DesignWarning]


@with_config(ConfigDict(extra="allow"))
class ConcreteDesignAnalysisRampSurfaceOpen(TypedDict):
    x_m: list[float]
    r_m: list[float]


@with_config(ConfigDict(extra="allow"))
class ConcreteDesignAnalysisSummary(TypedDict):
    max_arm_angle_deg: float | None
    q90_margin_deg: float | None
    minimum_ramp_endpoint_margin_m: float | None
    contact_valid_fraction: float
    runtime_map_compiled: bool


@with_config(ConfigDict(extra="allow"))
class ConcreteDesignAnalysis(TypedDict):
    analysis_id: str
    validity: ConcreteDesignAnalysisValidity
    architecture: FixedPivotArchitecture
    ramp: FixedPivotRamp
    requested_travel_m: float
    contact_valid_travel_m: float
    geometry: SampledFieldSet
    ramp_surface_open: ConcreteDesignAnalysisRampSurfaceOpen
    summary: ConcreteDesignAnalysisSummary


@with_config(ConfigDict(extra="allow"))
class ConcreteDesignResponse(TypedDict):
    analysis_id: str
    operating: PrimaryDesignOperating
    loads: SampledFieldSet


@with_config(ConfigDict(extra="allow"))
class WorkspacePolygon(TypedDict):
    x_m: list[float]
    r_m: list[float]


@with_config(ConfigDict(extra="allow"))
class ArchitectureFinding(TypedDict):
    severity: Literal["error"] | Literal["warning"] | Literal["info"]
    code: str
    message: str


@with_config(ConfigDict(extra="allow"))
class PackagingZoneDiagnostic(TypedDict):
    zone_id: str
    label: str
    subject: PackagingZoneSubject
    rule: PackagingZoneRule
    status: Literal["pass"] | Literal["restricts"] | Literal["blocks"]
    retained_fraction: float


@with_config(ConfigDict(extra="allow"))
class ArchitectureAnalysisValidity(TypedDict):
    valid: bool
    findings: list[ArchitectureFinding]


@with_config(ConfigDict(extra="allow"))
class ArchitectureAnalysisLimits(TypedDict):
    q_min_deg: float
    q_max_deg: float


@with_config(ConfigDict(extra="allow"))
class ArchitectureAnalysisWorkspaceOpenRollerArc(TypedDict):
    x_m: list[float]
    r_m: list[float]


@with_config(ConfigDict(extra="allow"))
class ArchitectureAnalysisWorkspaceFullShiftRollerArc(TypedDict):
    x_m: list[float]
    r_m: list[float]


@with_config(ConfigDict(extra="allow"))
class ArchitectureAnalysisWorkspace(TypedDict):
    roller_center: list[WorkspacePolygon]
    potential_ramp_surface: list[WorkspacePolygon]
    packaging_feasible_ramp_surface: list[WorkspacePolygon]
    open_roller_arc: ArchitectureAnalysisWorkspaceOpenRollerArc
    full_shift_roller_arc: ArchitectureAnalysisWorkspaceFullShiftRollerArc


@with_config(ConfigDict(extra="allow"))
class ArchitectureAnalysisBoundariesQMinFlatRamp(TypedDict):
    x_m: list[float]
    r_m: list[float]


@with_config(ConfigDict(extra="allow"))
class ArchitectureAnalysisBoundariesQMaxFlatRamp(TypedDict):
    x_m: list[float]
    r_m: list[float]


@with_config(ConfigDict(extra="allow"))
class ArchitectureAnalysisBoundariesPivotTravel(TypedDict):
    x_m: list[float]
    r_m: list[float]


@with_config(ConfigDict(extra="allow"))
class ArchitectureAnalysisBoundaries(TypedDict):
    q_min_flat_ramp: ArchitectureAnalysisBoundariesQMinFlatRamp
    q_max_flat_ramp: ArchitectureAnalysisBoundariesQMaxFlatRamp
    pivot_travel: ArchitectureAnalysisBoundariesPivotTravel


@with_config(ConfigDict(extra="allow"))
class ArchitectureAnalysisViewport(TypedDict):
    x_min_m: float
    x_max_m: float
    r_min_m: float
    r_max_m: float


@with_config(ConfigDict(extra="allow"))
class ArchitectureAnalysisSummary(TypedDict):
    admissible_pose_fraction: float
    ramp_workspace_fraction: float
    zone_count: int
    ramp_zone_count: int
    flyweight_zone_count: int
    shift_sample_count: int
    q_sample_count: int


@with_config(ConfigDict(extra="allow"))
class ArchitectureAnalysis(TypedDict):
    architecture: FixedPivotArchitecture
    zones: list[PackagingZone]
    validity: ArchitectureAnalysisValidity
    limits: ArchitectureAnalysisLimits
    workspace: ArchitectureAnalysisWorkspace
    boundaries: ArchitectureAnalysisBoundaries
    zone_diagnostics: list[PackagingZoneDiagnostic]
    viewport: ArchitectureAnalysisViewport
    summary: ArchitectureAnalysisSummary


@with_config(ConfigDict(extra="allow"))
class PathDomainStationProjection(TypedDict):
    station: int
    viable_state_count: int
    q_min_deg: float | None
    q_max_deg: float | None
    active_q_min_deg: float | None
    active_q_max_deg: float | None


@with_config(ConfigDict(extra="allow"))
class HistoryCertifiedRampPathRollerCenter(TypedDict):
    x_m: list[float]
    r_m: list[float]


@with_config(ConfigDict(extra="allow"))
class HistoryCertifiedRampPathRampSurface(TypedDict):
    x_m: list[float]
    r_m: list[float]


@with_config(ConfigDict(extra="allow"))
class HistoryCertifiedRampPathCapability(TypedDict):
    arm_force_per_omega2: list[float]
    tip_force_per_omega2_per_kg: list[float]
    max_tip_total_force_per_omega2: list[float]


@with_config(ConfigDict(extra="allow"))
class HistoryCertifiedRampPathHistory(TypedDict):
    max_contact_root_count: int
    multiple_root_shift_count: int
    trace_shift_m: list[float]
    trace_parameter_m: list[float]
    trace_q_deg: list[float]


@with_config(ConfigDict(extra="allow"))
class HistoryCertifiedRampPath(TypedDict):
    state_indices: list[int]
    shift_m: list[float]
    q_deg: list[float]
    ramp_tangent_deg: list[float]
    roller_center: HistoryCertifiedRampPathRollerCenter
    ramp_surface: HistoryCertifiedRampPathRampSurface
    capability: HistoryCertifiedRampPathCapability
    history: HistoryCertifiedRampPathHistory


@with_config(ConfigDict(extra="allow"))
class PrimaryPathDomainAnalysisValidity(TypedDict):
    valid: bool
    findings: list[ArchitectureFinding]


@with_config(ConfigDict(extra="allow"))
class PrimaryPathDomainAnalysisGraph(TypedDict):
    shift_station_count: int
    q_sample_count: int
    alpha_sample_count: int
    state_count: int
    local_transition_template_count: int
    layer_edge_counts: list[int]
    viable_layer_edge_counts: list[int]
    viable_node_counts: list[int]
    station_projection: list[PathDomainStationProjection]


@with_config(ConfigDict(extra="allow"))
class PrimaryPathDomainAnalysisHistory(TypedDict):
    candidate_complete_path_count: int
    certified_representative_path_count: int
    history_rejection_count: int
    rejections: list[dict[str, Any]]
    selection_rule: str


@with_config(ConfigDict(extra="allow"))
class PrimaryPathDomainAnalysisDomainProjectionRampSurfacePoints(TypedDict):
    x_m: list[float]
    r_m: list[float]
    station: list[int]
    q_deg: list[float]
    ramp_tangent_deg: list[float]


@with_config(ConfigDict(extra="allow"))
class PrimaryPathDomainAnalysisDomainProjection(TypedDict):
    meaning: str
    ramp_surface_points: PrimaryPathDomainAnalysisDomainProjectionRampSurfacePoints
    visual_radius_m: float
    point_count: int


@with_config(ConfigDict(extra="allow"))
class PrimaryPathDomainAnalysisCapabilityUnits(TypedDict):
    arm_force_per_omega2: str
    tip_force_per_omega2_per_kg: str
    max_tip_total_force_per_omega2: str


@with_config(ConfigDict(extra="allow"))
class PrimaryPathDomainAnalysisCapabilityStationsItem(TypedDict):
    station: int
    shift_m: float
    shift_fraction: float
    active_state_count: int
    arm_force_per_omega2_min: float | None
    arm_force_per_omega2_max: float | None
    tip_force_per_omega2_per_kg_min: float | None
    tip_force_per_omega2_per_kg_max: float | None
    max_tip_total_force_per_omega2_min: float | None
    max_tip_total_force_per_omega2_max: float | None


@with_config(ConfigDict(extra="allow"))
class PrimaryPathDomainAnalysisCapability(TypedDict):
    definition: str
    units: PrimaryPathDomainAnalysisCapabilityUnits
    max_tip_mass_per_flyweight_kg: float
    stations: list[PrimaryPathDomainAnalysisCapabilityStationsItem]


@with_config(ConfigDict(extra="allow"))
class PrimaryPathDomainAnalysisNumerics(TypedDict):
    edge_audit_sample_count: int
    history_trace_sample_count: int


@with_config(ConfigDict(extra="allow"))
class PrimaryPathDomainAnalysis(TypedDict):
    domain_id: str
    architecture: FixedPivotArchitecture
    zones: list[PackagingZone]
    validity: PrimaryPathDomainAnalysisValidity
    graph: PrimaryPathDomainAnalysisGraph
    history: PrimaryPathDomainAnalysisHistory
    representative_paths: list[HistoryCertifiedRampPath]
    domain_projection: PrimaryPathDomainAnalysisDomainProjection
    capability: PrimaryPathDomainAnalysisCapability
    deferred_checks: list[str]
    numerics: PrimaryPathDomainAnalysisNumerics


@with_config(ConfigDict(extra="allow"))
class ForceRequirement(TypedDict):
    id: str
    shift_m: float
    force_N: float
    shaft_speed_rad_s: float
    tolerance_N: float


@with_config(ConfigDict(extra="allow"))
class ConditionedRampSolutionSolutionForceN(TypedDict):
    shaft_speed_rad_s: float
    values: list[float]


@with_config(ConfigDict(extra="allow"))
class ConditionedRampSolutionSolution(TypedDict):
    tip_mass_min_kg: float
    tip_mass_max_kg: float
    example_tip_mass_kg: float
    force_N: ConditionedRampSolutionSolutionForceN


class ConditionedRampSolution(HistoryCertifiedRampPath):
    solution: ConditionedRampSolutionSolution


@with_config(ConfigDict(extra="allow"))
class ConditionedPathDomainAnalysisValidity(TypedDict):
    valid: bool
    findings: list[dict[str, Any]]


@with_config(ConfigDict(extra="allow"))
class ConditionedPathDomainAnalysisRequirementsItem(TypedDict):
    id: str
    shift_m: float
    force_N: float
    shaft_speed_rad_s: float
    tolerance_N: float
    individually_attainable: bool


@with_config(ConfigDict(extra="allow"))
class ConditionedPathDomainAnalysisMass(TypedDict):
    maximum_tip_mass_per_flyweight_kg: float
    mass_sample_count: int
    mass_resolution_kg: float
    surviving_mass_min_kg: float | None
    surviving_mass_max_kg: float | None


@with_config(ConfigDict(extra="allow"))
class ConditionedPathDomainAnalysisGraph(TypedDict):
    viable_layer_edge_counts: list[int]
    viable_node_counts: list[int]
    station_projection: list[PathDomainStationProjection]


@with_config(ConfigDict(extra="allow"))
class ConditionedPathDomainAnalysisDomainProjectionRampSurfacePoints(TypedDict):
    x_m: list[float]
    r_m: list[float]
    station: list[int]
    q_deg: list[float]
    ramp_tangent_deg: list[float]


@with_config(ConfigDict(extra="allow"))
class ConditionedPathDomainAnalysisDomainProjection(TypedDict):
    meaning: str
    ramp_surface_points: ConditionedPathDomainAnalysisDomainProjectionRampSurfacePoints
    visual_radius_m: float
    point_count: int


@with_config(ConfigDict(extra="allow"))
class ConditionedPathDomainAnalysisForceCapability(TypedDict):
    reference_shaft_speed_rad_s: float
    full: AbsoluteForceCapability
    conditioned: AbsoluteForceCapability


@with_config(ConfigDict(extra="allow"))
class ConditionedPathDomainAnalysisSummary(TypedDict):
    requirement_count: int
    jointly_feasible: bool
    conditioned_domain_point_count: int
    representative_solution_count: int


@with_config(ConfigDict(extra="allow"))
class ConditionedPathDomainAnalysis(TypedDict):
    domain_id: str
    validity: ConditionedPathDomainAnalysisValidity
    requirements: list[ConditionedPathDomainAnalysisRequirementsItem]
    mass: ConditionedPathDomainAnalysisMass
    graph: ConditionedPathDomainAnalysisGraph
    domain_projection: ConditionedPathDomainAnalysisDomainProjection
    force_capability: ConditionedPathDomainAnalysisForceCapability
    representative_solutions: list[ConditionedRampSolution]
    summary: ConditionedPathDomainAnalysisSummary


@with_config(ConfigDict(extra="allow"))
class AbsoluteForceCapabilityStationsItem(TypedDict):
    station: int
    shift_m: float
    active_state_count: int
    force_min_N: float | None
    force_max_N: float | None
    force_intervals_N: list[tuple[float, float]]
    mass_min_kg: float | None
    mass_max_kg: float | None


@with_config(ConfigDict(extra="allow"))
class AbsoluteForceCapability(TypedDict):
    shaft_speed_rad_s: float
    max_tip_mass_per_flyweight_kg: float
    stations: list[AbsoluteForceCapabilityStationsItem]


@with_config(ConfigDict(extra="allow"))
class InverseDesignTargetPoint(TypedDict):
    shift_m: float
    force_N: float


@with_config(ConfigDict(extra="allow"))
class InverseRampSolutionRollerCenter(TypedDict):
    x_m: list[float]
    r_m: list[float]


@with_config(ConfigDict(extra="allow"))
class InverseRampSolutionRampSurface(TypedDict):
    x_m: list[float]
    r_m: list[float]


@with_config(ConfigDict(extra="allow"))
class InverseRampSolutionForce(TypedDict):
    target_N: list[float]
    recovered_N: list[float]


@with_config(ConfigDict(extra="allow"))
class InverseRampSolutionMetrics(TypedDict):
    rms_force_error_N: float
    max_force_error_N: float
    q_margin_deg: float
    ramp_tangent_margin_deg: float
    minimum_offset_factor: float
    minimum_roller_direction_margin: float
    minimum_packaging_margin_m: float | None
    robustness_score: float


@with_config(ConfigDict(extra="allow"))
class InverseRampSolutionHistory(TypedDict):
    valid: bool
    max_contact_root_count: NotRequired[float]
    multiple_root_shift_count: NotRequired[float]


@with_config(ConfigDict(extra="allow"))
class InverseRampSolution(TypedDict):
    tip_mass_per_flyweight_kg: float
    initial_q_deg: float
    shift_m: list[float]
    q_deg: list[float]
    q_prime_rad_per_m: list[float]
    q_second_rad_per_m2: list[float]
    ramp_tangent_deg: list[float]
    roller_center: InverseRampSolutionRollerCenter
    ramp_surface: InverseRampSolutionRampSurface
    force: InverseRampSolutionForce
    metrics: InverseRampSolutionMetrics
    history: InverseRampSolutionHistory


@with_config(ConfigDict(extra="allow"))
class InverseDesignAnalysisTarget(TypedDict):
    shaft_speed_rad_s: float
    shift_m: list[float]
    force_N: list[float]
    input_points: list[InverseDesignTargetPoint]


@with_config(ConfigDict(extra="allow"))
class InverseDesignAnalysisDiagnosticsItem(TypedDict):
    severity: str
    code: str
    message: str
    count: NotRequired[float]
    shift_m: NotRequired[float | None]


@with_config(ConfigDict(extra="allow"))
class InverseDesignAnalysisSummary(TypedDict):
    method: str
    candidate_pair_count: int
    geometry_candidate_count: int
    certified_solution_count: int
    best_rms_error_N: float | None
    best_max_error_N: float | None
    target_integrated_force_Nm: float
    maximum_integrated_force_Nm: float
    capacity_q_min_deg: float
    capacity_q_max_deg: float
    fixed_tip_mass_per_flyweight_kg: float | None
    max_tip_mass_per_flyweight_kg: float
    force_definition: str


@with_config(ConfigDict(extra="allow"))
class InverseDesignAnalysis(TypedDict):
    target: InverseDesignAnalysisTarget
    solutions: list[InverseRampSolution]
    diagnostics: list[InverseDesignAnalysisDiagnosticsItem]
    summary: InverseDesignAnalysisSummary


@with_config(ConfigDict(extra="allow"))
class ArchitectureShapePointRampRollerCenter(TypedDict):
    x_m: list[float]
    r_m: list[float]


@with_config(ConfigDict(extra="allow"))
class ArchitectureShapePointRampRampSurface(TypedDict):
    x_m: list[float]
    r_m: list[float]


@with_config(ConfigDict(extra="allow"))
class ArchitectureShapePointRamp(TypedDict):
    shift_m: list[float]
    q_deg: list[float]
    ramp_tangent_deg: list[float]
    roller_center: ArchitectureShapePointRampRollerCenter
    ramp_surface: ArchitectureShapePointRampRampSurface


@with_config(ConfigDict(extra="allow"))
class ArchitectureShapePoint(TypedDict):
    architecture: str
    path_index: int
    state_indices: list[int]
    mass_mix_fraction: float
    tip_to_arm_mass_ratio: float
    c1: float
    c2: float
    c3: float
    mean_specific_gain: float
    shift_fraction: list[float]
    specific_gain: list[float]
    normalized_shape: list[float]
    ramp: ArchitectureShapePointRamp


@with_config(ConfigDict(extra="allow"))
class ArchitectureComparisonWitness(TypedDict):
    source_architecture: str
    nearest_architecture: str
    shape_distance: float
    max_pointwise_shape_gap: float
    gap_shift_fraction: float
    source: ArchitectureShapePoint
    nearest: ArchitectureShapePoint


@with_config(ConfigDict(extra="allow"))
class ArchitectureComparisonAnalysisDefinition(TypedDict):
    mass_agnostic: bool
    specific_gain: str
    shape_normalization: str
    sampling_note: str


@with_config(ConfigDict(extra="allow"))
class ArchitectureComparisonAnalysisArchitectureAFootprintPointsItem(TypedDict):
    path_index: int
    mass_mix_fraction: float
    c1: float
    c2: float
    c3: float
    mean_specific_gain: float


@with_config(ConfigDict(extra="allow"))
class ArchitectureComparisonAnalysisArchitectureAFootprint(TypedDict):
    points: list[ArchitectureComparisonAnalysisArchitectureAFootprintPointsItem]
    hull_c1_c2: list[list[float]]


@with_config(ConfigDict(extra="allow"))
class ArchitectureComparisonAnalysisArchitectureASpecificLeverageEnvelope(TypedDict):
    shift_fraction: list[float]
    min: list[float]
    max: list[float]
    median: list[float]


@with_config(ConfigDict(extra="allow"))
class ArchitectureComparisonAnalysisArchitectureA(TypedDict):
    domain_id: str
    certified_path_count: int
    shape_sample_count: int
    footprint: ArchitectureComparisonAnalysisArchitectureAFootprint
    specific_leverage_envelope: ArchitectureComparisonAnalysisArchitectureASpecificLeverageEnvelope


@with_config(ConfigDict(extra="allow"))
class ArchitectureComparisonAnalysisArchitectureBFootprintPointsItem(TypedDict):
    path_index: int
    mass_mix_fraction: float
    c1: float
    c2: float
    c3: float
    mean_specific_gain: float


@with_config(ConfigDict(extra="allow"))
class ArchitectureComparisonAnalysisArchitectureBFootprint(TypedDict):
    points: list[ArchitectureComparisonAnalysisArchitectureBFootprintPointsItem]
    hull_c1_c2: list[list[float]]


@with_config(ConfigDict(extra="allow"))
class ArchitectureComparisonAnalysisArchitectureBSpecificLeverageEnvelope(TypedDict):
    shift_fraction: list[float]
    min: list[float]
    max: list[float]
    median: list[float]


@with_config(ConfigDict(extra="allow"))
class ArchitectureComparisonAnalysisArchitectureB(TypedDict):
    domain_id: str
    certified_path_count: int
    shape_sample_count: int
    footprint: ArchitectureComparisonAnalysisArchitectureBFootprint
    specific_leverage_envelope: ArchitectureComparisonAnalysisArchitectureBSpecificLeverageEnvelope


@with_config(ConfigDict(extra="allow"))
class ArchitectureComparisonAnalysisWitnesses(TypedDict):
    a_not_b: list[ArchitectureComparisonWitness]
    b_not_a: list[ArchitectureComparisonWitness]


@with_config(ConfigDict(extra="allow"))
class ArchitectureComparisonAnalysisSummary(TypedDict):
    atlas_path_count_requested: float
    mass_mix_count: int
    a_to_b_median_shape_distance: float | None
    a_to_b_max_shape_distance: float | None
    b_to_a_median_shape_distance: float | None
    b_to_a_max_shape_distance: float | None


@with_config(ConfigDict(extra="allow"))
class ArchitectureComparisonAnalysis(TypedDict):
    definition: ArchitectureComparisonAnalysisDefinition
    architecture_a: ArchitectureComparisonAnalysisArchitectureA
    architecture_b: ArchitectureComparisonAnalysisArchitectureB
    witnesses: ArchitectureComparisonAnalysisWitnesses
    summary: ArchitectureComparisonAnalysisSummary


@with_config(ConfigDict(extra="allow"))
class ForceShapeTargetPoint(TypedDict):
    shift_fraction: float
    relative_force: float


@with_config(ConfigDict(extra="allow"))
class ArchitectureTargetMatchRampRollerCenter(TypedDict):
    x_m: list[float]
    r_m: list[float]


@with_config(ConfigDict(extra="allow"))
class ArchitectureTargetMatchRampRampSurface(TypedDict):
    x_m: list[float]
    r_m: list[float]


@with_config(ConfigDict(extra="allow"))
class ArchitectureTargetMatchRamp(TypedDict):
    shift_m: list[float]
    q_deg: list[float]
    ramp_tangent_deg: list[float]
    roller_center: ArchitectureTargetMatchRampRollerCenter
    ramp_surface: ArchitectureTargetMatchRampRampSurface


@with_config(ConfigDict(extra="allow"))
class ArchitectureTargetMatch(TypedDict):
    architecture: Literal["A"] | Literal["B"] | str
    rms_shape_error: float
    max_shape_error: float
    max_error_shift_fraction: float
    mass_mix_fraction: float
    tip_to_arm_mass_ratio: float
    shift_fraction: list[float]
    normalized_shape: list[float]
    sampled_candidate_count: int
    ramp: ArchitectureTargetMatchRamp


@with_config(ConfigDict(extra="allow"))
class ArchitectureTargetComparisonAnalysisDefinition(TypedDict):
    mass_scale_agnostic: bool
    normalization: str
    distance: str
    sampling_note: str


@with_config(ConfigDict(extra="allow"))
class ArchitectureTargetComparisonAnalysisTarget(TypedDict):
    shift_fraction: list[float]
    normalized_shape: list[float]
    input_points: list[ForceShapeTargetPoint]


@with_config(ConfigDict(extra="allow"))
class ArchitectureTargetComparisonAnalysisSummary(TypedDict):
    a_rms_shape_error: float | None
    b_rms_shape_error: float | None
    a_max_shape_error: float | None
    b_max_shape_error: float | None


@with_config(ConfigDict(extra="allow"))
class ArchitectureTargetComparisonAnalysis(TypedDict):
    definition: ArchitectureTargetComparisonAnalysisDefinition
    target: ArchitectureTargetComparisonAnalysisTarget
    architecture_a: ArchitectureTargetMatch | None
    architecture_b: ArchitectureTargetMatch | None
    summary: ArchitectureTargetComparisonAnalysisSummary
