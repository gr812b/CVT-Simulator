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

/**
 * Scale compensation factor for child object positions.
 * Since parent models are scaled down (GLB assumes meters, models are in inches),
 * child positions need to be scaled up by this factor to maintain correct world-space offsets.
 * This is the conversion factor from meters to inches (1 meter ≈ 39.37 inches).
 */
const CHILD_POSITION_SCALE = 39.3701; // meters to inches conversion

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
    getInitialPosition: (constants) => [-constants.center_to_center / 2, 0, 0],
  },
  {
    id: 'primaryMoving',
    modelUrl: primaryMovingModel,
    color: 0xff8844,
    parentId: 'primaryFixed',
    getInitialPosition: (constants) => [0, 0, -constants.max_shift * CHILD_POSITION_SCALE],
  },
  {
    id: 'secondaryFixed',
    modelUrl: secondaryFixedModel,
    color: 0x44ff44,
    getInitialPosition: (constants) => [constants.center_to_center / 2, 0, constants.max_shift],
  },
  {
    id: 'secondaryMoving',
    modelUrl: secondaryMovingModel,
    color: 0x88ff44,
    parentId: 'secondaryFixed',
    getInitialPosition: () => [0, 0, 0 * CHILD_POSITION_SCALE],
  },
];
