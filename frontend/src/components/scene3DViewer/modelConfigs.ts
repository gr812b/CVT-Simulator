import primaryFixedModel from '@assets/models/prim_fixed.glb?url';
import primaryMovingModel from '@assets/models/prim_moving.glb?url';
import secondaryFixedModel from '@assets/models/sec_fixed.glb?url';
import secondaryMovingModel from '@assets/models/sec_moving.glb?url';
import type { SceneGeometry } from './sceneSpec';

export const primaryOffset = 0.6;
export const secondaryOffset = 0.56;

export interface CVTModelConfig {
  id: string;
  modelUrl: string;
  color: number;
  parentId?: string;
  getInitialPosition: (geometry: SceneGeometry) => [number, number, number];
  rotation?: [number, number, number];
}

export const CVT_MODEL_CONFIGS: CVTModelConfig[] = [
  { id: 'primaryFixed', modelUrl: primaryFixedModel, color: 0xff4444, getInitialPosition: (geometry) => [-geometry.centreDistance / 2, 0, -primaryOffset - geometry.maxShift / 2], rotation: [0, Math.PI, 0] },
  { id: 'primaryMoving', modelUrl: primaryMovingModel, color: 0xff8844, parentId: 'primaryFixed', getInitialPosition: (geometry) => [0, 0, -primaryOffset - geometry.maxShift] },
  { id: 'secondaryFixed', modelUrl: secondaryFixedModel, color: 0x44ff44, getInitialPosition: (geometry) => [geometry.centreDistance / 2, 0, secondaryOffset - geometry.deadzoneShift / 2] },
  { id: 'secondaryMoving', modelUrl: secondaryMovingModel, color: 0x88ff44, parentId: 'secondaryFixed', getInitialPosition: () => [0, 0, -secondaryOffset] },
];
