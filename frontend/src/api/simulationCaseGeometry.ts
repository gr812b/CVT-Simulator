import type { SimulationCaseDocument } from './client';

/**
 * Geometry fields used directly by the frontend.
 *
 * The generated composed-simulation schema intentionally treats `assembly`
 * as an opaque CINDER assembly object, so json-schema-to-typescript cannot
 * infer these nested fields. Keep the small UI-facing view here rather than
 * weakening the generated contract with `any`.
 */
export interface SimulationCaseGeometry {
  belt: {
    height_m: number;
    outer_width_m: number;
    inner_width_m: number;
    cord_depth_from_outer_m: number;
  };
  belt_outer_length_m: number;
  primary_outer_radius_at_zero_shift_m: number;
  secondary_outer_radius_at_zero_shift_m: number;
  sheave_half_angle_rad: number;
  deadzone_shift_m: number;
  max_shift_m: number;
}

/**
 * Return the typed geometry view of a CINDER simulation document.
 *
 * Backend validation owns the complete assembly contract. This accessor only
 * tells TypeScript about the subset the current frontend actually reads.
 */
export function simulationCaseGeometry(
  document: SimulationCaseDocument,
): SimulationCaseGeometry {
  return document.assembly.geometry as SimulationCaseGeometry;
}
