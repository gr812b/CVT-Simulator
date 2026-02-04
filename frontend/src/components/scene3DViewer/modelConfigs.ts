import type { ConstantsResponse } from '@utils/api';
import type { UnitOptions } from '@utils/conversion';
import primaryFixedModel from '@assets/models/prim_fixed.glb?url';
import primaryMovingModel from '@assets/models/prim_moving.glb?url';
import secondaryFixedModel from '@assets/models/sec_fixed.glb?url';
import secondaryMovingModel from '@assets/models/sec_moving.glb?url';

/**
 * The distance unit used throughout the 3D scene.
 * All distance values will be converted to this unit for rendering.
 */
export const SCENE_DISTANCE_UNIT: UnitOptions['distance'] = 'in';
export const SCENE_ANGLE_UNIT: UnitOptions['angle'] = 'rad';

const primaryOffset = 0.6;
const secondaryOffset = 0.56;

/**
 * Configuration for each CVT model component
 */
export interface CVTModelConfig {
  id: string;
  modelUrl: string;
  color: number;
  parentId?: string;
  /** Function that calculates initial position based on constants */
  getInitialPosition: (constants: ConstantsResponse) => [number, number, number];
  /** Optional initial rotation [x, y, z] in radians */
  rotation?: [number, number, number];
}

/**
 * Centralized configuration for all CVT 3D models.
 * Defines model files, colors, parent relationships, and positioning logic.
 */
export const CVT_MODEL_CONFIGS: CVTModelConfig[] = [
  {
    id: 'primaryFixed',
    modelUrl: primaryFixedModel,
    color: 0xff4444,
    getInitialPosition: (constants) => [-constants.center_to_center / 2, 0, -primaryOffset - constants.max_shift / 2],
    rotation: [0, Math.PI, 0], // Flip 180° around Y-axis to face the other way
  },
  {
    id: 'primaryMoving',
    modelUrl: primaryMovingModel,
    color: 0xff8844,
    parentId: 'primaryFixed',
    getInitialPosition: (constants) => [0, 0, -primaryOffset - constants.max_shift],
  },
  {
    id: 'secondaryFixed',
    modelUrl: secondaryFixedModel,
    color: 0x44ff44,
    // Offset by initial_sheave_displacement in -Z direction
    getInitialPosition: (constants) => [constants.center_to_center / 2, 0, secondaryOffset - constants.initial_sheave_displacement/2],
  },
  {
    id: 'secondaryMoving',
    modelUrl: secondaryMovingModel,
    color: 0x88ff44,
    parentId: 'secondaryFixed',
    getInitialPosition: () => [0, 0, -secondaryOffset],
  },
];
