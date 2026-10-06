import type { components } from '@api/generated/backend';

export type ResolvedSceneGeometry = components['schemas']['SceneGeometry'];
export type ScenePreview = components['schemas']['ScenePreview'];
export type SceneFrame = ScenePreview['frames'][number];
const METRES_TO_INCHES = 39.3700787402;

/** Renderer-local units only. All mechanical dimensions are resolved upstream. */
export interface SceneGeometry {
  mechanisms: ResolvedSceneGeometry['mechanisms'];
  beltOuterWidth: number;
  beltInnerWidth: number;
  beltHeight: number;
  cordDepth: number;
  halfAngle: number;
  centreDistance: number;
  primaryMinRadius: number;
  primaryMaxRadius: number;
  secondaryMinRadius: number;
  secondaryMaxRadius: number;
  maxShift: number;
  deadzoneShift: number;
}

export function sceneGeometry(value: ResolvedSceneGeometry): SceneGeometry {
  return {
    mechanisms: value.mechanisms,
    beltOuterWidth: sceneDistance(value.belt_outer_width_m),
    beltInnerWidth: sceneDistance(value.belt_inner_width_m),
    beltHeight: sceneDistance(value.belt_height_m),
    cordDepth: sceneDistance(value.cord_depth_from_outer_m),
    halfAngle: value.sheave_half_angle_rad,
    centreDistance: sceneDistance(value.center_distance_m),
    primaryMinRadius: sceneDistance(value.primary_outer_radius_min_m),
    primaryMaxRadius: sceneDistance(value.primary_outer_radius_max_m),
    secondaryMinRadius: sceneDistance(value.secondary_outer_radius_min_m),
    secondaryMaxRadius: sceneDistance(value.secondary_outer_radius_max_m),
    maxShift: sceneDistance(value.max_shift_m),
    deadzoneShift: sceneDistance(value.deadzone_shift_m),
  };
}
export function sceneDistance(valueM: number): number {
  return valueM * METRES_TO_INCHES;
}

export function sceneConfiguration(
  orbitOnly = false,
): Omit<import('@utils/sceneTypes').Scene3DConfig, 'container'> {
  return {
    camera: {
      type: 'perspective',
      fov: 42,
      position: [3, 9, 16],
      lookAt: [0, 0, 0],
    },
    enableControls: true,
    transparentBackground: true,
    orbitOnly,
    renderOnDemand: orbitOnly,
  };
}
