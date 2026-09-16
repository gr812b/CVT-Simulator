import { ApiClientError } from './client';

export type RampKind = 'progressive' | 'constant';
export type PackagingZoneSubject = 'flyweight' | 'ramp';
export type PackagingZoneRule = 'forbid' | 'contain';

export interface FixedPivotArchitecture {
  pivot_axial_position_m: number;
  pivot_radius_m: number;
  arm_length_m: number;
  roller_radius_m: number;
  required_travel_m: number;
  number_of_flyweights: number;
  arm_mass_per_flyweight_kg: number;
  ramp_axial_direction: -1 | 1;
  roller_side_sign: -1 | 1;
  max_tip_mass_per_flyweight_kg: number;
}

export interface PackagingZone {
  id: string;
  label: string;
  subject: PackagingZoneSubject;
  rule: PackagingZoneRule;
  polygon_m: Array<[number, number]>;
  clearance_m: number;
}

export interface FixedPivotRamp {
  kind: RampKind;
  initial_flyweight_angle_deg: number;
  linear_angle_deg: number;
  circular_start_angle_deg: number;
  circular_end_angle_deg: number;
  constant_length_m: number;
  linear_length_m: number;
  blend_length_m: number;
  circular_length_m: number;
}

export interface PrimaryDesignOperating {
  tip_mass_per_flyweight_kg: number;
  shaft_speed_rad_s: number;
  shift_speed_m_s: number;
  shift_acceleration_m_s2: number;
}

export interface PrimaryDesignDefaults {
  architecture: FixedPivotArchitecture;
  ramp: FixedPivotRamp;
  packaging_zones: PackagingZone[];
  operating: PrimaryDesignOperating;
  ui_limits: {
    tip_mass_per_flyweight_kg: [number, number];
    shaft_speed_rad_s: [number, number];
  };
}

export interface SampledFieldSet {
  axis_key: string;
  axis_unit: string;
  axis_values: number[];
  units: Record<string, string>;
  fields: Record<string, Array<number | boolean | null>>;
}

export interface DoubleContactFailureGeometry {
  kind: 'double_contact';
  arm_angle_deg: number;
  roller_center_x_m: number;
  roller_center_r_m: number;
  contacts: Array<{
    label: 'C1' | 'C2';
    contact_coordinate_m: number;
    x_m: number;
    r_m: number;
  }>;
}

export interface DesignFailure {
  code: string;
  message: string;
  shift_m: number | null;
  geometry?: DoubleContactFailureGeometry;
}

export interface DesignWarning {
  code: string;
  message: string;
  shift_m: number | null;
  detail?: string;
}

export interface ConcreteDesignAnalysis {
  analysis_id: string;
  validity: {
    valid: boolean;
    failure: DesignFailure | null;
    warnings: DesignWarning[];
  };
  architecture: FixedPivotArchitecture;
  ramp: FixedPivotRamp;
  requested_travel_m: number;
  contact_valid_travel_m: number;
  geometry: SampledFieldSet;
  ramp_surface_open: {
    x_m: number[];
    r_m: number[];
  };
  summary: {
    max_arm_angle_deg: number | null;
    q90_margin_deg: number | null;
    minimum_ramp_endpoint_margin_m: number | null;
    contact_valid_fraction: number;
    runtime_map_compiled: boolean;
  };
}

export interface ConcreteDesignResponse {
  analysis_id: string;
  operating: PrimaryDesignOperating;
  loads: SampledFieldSet;
}

export interface WorkspacePolygon {
  x_m: number[];
  r_m: number[];
}

export interface ArchitectureFinding {
  severity: 'error' | 'warning' | 'info';
  code: string;
  message: string;
}

export interface PackagingZoneDiagnostic {
  zone_id: string;
  label: string;
  subject: PackagingZoneSubject;
  rule: PackagingZoneRule;
  status: 'pass' | 'restricts' | 'blocks';
  retained_fraction: number;
}

export interface ArchitectureAnalysis {
  architecture: FixedPivotArchitecture;
  zones: PackagingZone[];
  validity: {
    valid: boolean;
    findings: ArchitectureFinding[];
  };
  limits: {
    q_min_deg: number;
    q_max_deg: number;
  };
  workspace: {
    roller_center: WorkspacePolygon[];
    potential_ramp_surface: WorkspacePolygon[];
    packaging_feasible_ramp_surface: WorkspacePolygon[];
    open_roller_arc: { x_m: number[]; r_m: number[] };
    full_shift_roller_arc: { x_m: number[]; r_m: number[] };
  };
  boundaries: {
    q_min_flat_ramp: { x_m: number[]; r_m: number[] };
    q_max_flat_ramp: { x_m: number[]; r_m: number[] };
    pivot_travel: { x_m: number[]; r_m: number[] };
  };
  zone_diagnostics: PackagingZoneDiagnostic[];
  viewport: {
    x_min_m: number;
    x_max_m: number;
    r_min_m: number;
    r_max_m: number;
  };
  summary: {
    admissible_pose_fraction: number;
    ramp_workspace_fraction: number;
    zone_count: number;
    ramp_zone_count: number;
    flyweight_zone_count: number;
    shift_sample_count: number;
    q_sample_count: number;
  };
}


export interface PathDomainStationProjection {
  station: number;
  viable_state_count: number;
  q_min_deg: number | null;
  q_max_deg: number | null;
  active_q_min_deg: number | null;
  active_q_max_deg: number | null;
}

export interface HistoryCertifiedRampPath {
  state_indices: number[];
  shift_m: number[];
  q_deg: number[];
  ramp_tangent_deg: number[];
  roller_center: { x_m: number[]; r_m: number[] };
  ramp_surface: { x_m: number[]; r_m: number[] };
  capability: {
    arm_force_per_omega2: number[];
    tip_force_per_omega2_per_kg: number[];
    max_tip_total_force_per_omega2: number[];
  };
  history: {
    max_contact_root_count: number;
    multiple_root_shift_count: number;
    trace_shift_m: number[];
    trace_parameter_m: number[];
    trace_q_deg: number[];
  };
}

export interface PrimaryPathDomainAnalysis {
  domain_id: string;
  architecture: FixedPivotArchitecture;
  zones: PackagingZone[];
  validity: { valid: boolean; findings: ArchitectureFinding[] };
  graph: {
    shift_station_count: number;
    q_sample_count: number;
    alpha_sample_count: number;
    state_count: number;
    local_transition_template_count: number;
    layer_edge_counts: number[];
    viable_layer_edge_counts: number[];
    viable_node_counts: number[];
    station_projection: PathDomainStationProjection[];
  };
  history: {
    candidate_complete_path_count: number;
    certified_representative_path_count: number;
    history_rejection_count: number;
    rejections: Array<Record<string, unknown>>;
    selection_rule: string;
  };
  representative_paths: HistoryCertifiedRampPath[];
  domain_projection: {
    meaning: string;
    ramp_surface_points: {
      x_m: number[];
      r_m: number[];
      station: number[];
      q_deg: number[];
      ramp_tangent_deg: number[];
    };
    visual_radius_m: number;
    point_count: number;
  };
  capability: {
    definition: string;
    units: {
      arm_force_per_omega2: string;
      tip_force_per_omega2_per_kg: string;
      max_tip_total_force_per_omega2: string;
    };
    max_tip_mass_per_flyweight_kg: number;
    stations: Array<{
      station: number;
      shift_m: number;
      shift_fraction: number;
      active_state_count: number;
      arm_force_per_omega2_min: number | null;
      arm_force_per_omega2_max: number | null;
      tip_force_per_omega2_per_kg_min: number | null;
      tip_force_per_omega2_per_kg_max: number | null;
      max_tip_total_force_per_omega2_min: number | null;
      max_tip_total_force_per_omega2_max: number | null;
    }>;
  };
  deferred_checks: string[];
  numerics: {
    edge_audit_sample_count: number;
    history_trace_sample_count: number;
  };
}


export interface ForceRequirement {
  id: string;
  shift_m: number;
  force_N: number;
  shaft_speed_rad_s: number;
  tolerance_N: number;
}

export interface ConditionedRampSolution extends HistoryCertifiedRampPath {
  solution: {
    tip_mass_min_kg: number;
    tip_mass_max_kg: number;
    example_tip_mass_kg: number;
    force_N: {
      shaft_speed_rad_s: number;
      values: number[];
    };
  };
}

export interface ConditionedPathDomainAnalysis {
  domain_id: string;
  validity: { valid: boolean; findings: Array<Record<string, unknown>> };
  requirements: Array<ForceRequirement & { individually_attainable: boolean }>;
  mass: {
    maximum_tip_mass_per_flyweight_kg: number;
    mass_sample_count: number;
    mass_resolution_kg: number;
    surviving_mass_min_kg: number | null;
    surviving_mass_max_kg: number | null;
  };
  graph: {
    viable_layer_edge_counts: number[];
    viable_node_counts: number[];
    station_projection: PathDomainStationProjection[];
  };
  domain_projection: PrimaryPathDomainAnalysis['domain_projection'];
  force_capability: {
    reference_shaft_speed_rad_s: number;
    full: AbsoluteForceCapability;
    conditioned: AbsoluteForceCapability;
  };
  representative_solutions: ConditionedRampSolution[];
  summary: {
    requirement_count: number;
    jointly_feasible: boolean;
    conditioned_domain_point_count: number;
    representative_solution_count: number;
  };
}

export interface AbsoluteForceCapability {
  shaft_speed_rad_s: number;
  max_tip_mass_per_flyweight_kg: number;
  stations: Array<{
    station: number;
    shift_m: number;
    active_state_count: number;
    force_min_N: number | null;
    force_max_N: number | null;
    mass_min_kg: number | null;
    mass_max_kg: number | null;
  }>;
}

const baseUrl = (import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000').replace(/\/+$/, '');
const PREFIX = '/api/v1/engineering/fixed-pivot-primary';

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const headers = new Headers(init?.headers);
  if (init?.body !== undefined) headers.set('Content-Type', 'application/json');
  const response = await fetch(`${baseUrl}${PREFIX}${path}`, { ...init, headers });
  const text = await response.text();
  const payload = text ? JSON.parse(text) as unknown : null;
  if (!response.ok) {
    const message = extractMessage(payload) ?? 'The primary design service rejected the request.';
    throw new ApiClientError(message, response.status, payload);
  }
  return payload as T;
}

function extractMessage(payload: unknown): string | null {
  if (typeof payload !== 'object' || payload === null || !('error' in payload)) return null;
  const error = (payload as { error?: unknown }).error;
  if (typeof error !== 'object' || error === null || !('message' in error)) return null;
  const message = (error as { message?: unknown }).message;
  return typeof message === 'string' ? message : null;
}

export function getPrimaryDesignDefaults(): Promise<PrimaryDesignDefaults> {
  return request<PrimaryDesignDefaults>('/defaults');
}

export function analyzePrimaryArchitecture(
  architecture: FixedPivotArchitecture,
  zones: PackagingZone[],
  reachSampleCount = 361,
  shiftSampleCount = 41,
): Promise<ArchitectureAnalysis> {
  return request<ArchitectureAnalysis>('/architecture/analyze', {
    method: 'POST',
    body: JSON.stringify({
      architecture,
      zones,
      reach_sample_count: reachSampleCount,
      shift_sample_count: shiftSampleCount,
    }),
  });
}

export function analyzeConcretePrimaryDesign(
  architecture: FixedPivotArchitecture,
  ramp: FixedPivotRamp,
  sampleCount = 161,
): Promise<ConcreteDesignAnalysis> {
  return request<ConcreteDesignAnalysis>('/concrete/analyze', {
    method: 'POST',
    body: JSON.stringify({ architecture, ramp, sample_count: sampleCount }),
  });
}

export function evaluateConcretePrimaryDesign(
  analysisId: string,
  operating: PrimaryDesignOperating,
): Promise<ConcreteDesignResponse> {
  return request<ConcreteDesignResponse>('/concrete/response', {
    method: 'POST',
    body: JSON.stringify({ analysis_id: analysisId, ...operating }),
  });
}


export function analyzePrimaryPathDomain(
  architecture: FixedPivotArchitecture,
  zones: PackagingZone[],
  options: Partial<{
    shift_station_count: number;
    q_sample_count: number;
    alpha_sample_count: number;
    representative_path_count: number;
    edge_audit_sample_count: number;
    history_trace_sample_count: number;
  }> = {},
): Promise<PrimaryPathDomainAnalysis> {
  return request<PrimaryPathDomainAnalysis>('/architecture/path-domain', {
    method: 'POST',
    body: JSON.stringify({ architecture, zones, ...options }),
  });
}


export function conditionPrimaryPathDomain(
  domainId: string,
  requirements: ForceRequirement[],
  maxTipMassPerFlyweightKg: number,
  options: Partial<{ mass_sample_count: number; representative_solution_count: number; reference_shaft_speed_rad_s: number }> = {},
): Promise<ConditionedPathDomainAnalysis> {
  return request<ConditionedPathDomainAnalysis>('/architecture/path-domain/condition', {
    method: 'POST',
    body: JSON.stringify({
      domain_id: domainId,
      requirements,
      max_tip_mass_per_flyweight_kg: maxTipMassPerFlyweightKg,
      ...options,
    }),
  });
}
