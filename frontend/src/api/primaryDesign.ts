import { ApiClientError } from './client';

export type RampKind = 'progressive' | 'constant';

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
}

export interface FixedPivotRamp {
  kind: RampKind;
  anchor_axial_from_pivot_m: number;
  anchor_radial_from_pivot_m: number;
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
