import type { SimulationCaseDocument } from '@api/client';

const METRES_TO_INCHES = 39.3700787402;

export interface SceneGeometry {
  beltOuterWidth: number;
  beltInnerWidth: number;
  beltHeight: number;
  centreDistance: number;
  maxShift: number;
  deadzoneShift: number;
}

/** Values are direct document dimensions transformed only into scene units. */
export function sceneGeometry(document: SimulationCaseDocument): SceneGeometry {
  const geometry = document.assembly.geometry;
  const scale = METRES_TO_INCHES;
  return {
    beltOuterWidth: geometry.belt.outer_width_m * scale,
    beltInnerWidth: geometry.belt.inner_width_m * scale,
    beltHeight: geometry.belt.height_m * scale,
    // Layout spacing is visual-only: it scales with the submitted belt size.
    centreDistance: Math.max(7, geometry.belt_outer_length_m * scale * 0.30),
    maxShift: geometry.max_shift_m * scale,
    deadzoneShift: geometry.deadzone_shift_m * scale,
  };
}

export function sceneDistance(valueM: number): number { return valueM * METRES_TO_INCHES; }
