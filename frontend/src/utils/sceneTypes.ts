import type * as THREE from 'three';

export interface ModelTransform {
  position?: [number, number, number];
  rotation?: [number, number, number];
  scale?: [number, number, number];
}

export interface Model3DConfig extends ModelTransform {
  id: string;
  object3D: THREE.Object3D;
  parentId?: string;
}

export interface CameraConfig {
  type: 'perspective' | 'orthographic';
  position: [number, number, number];
  lookAt: [number, number, number];
  fov?: number;
  near?: number;
  far?: number;
}

export interface Scene3DConfig {
  container: HTMLElement;
  camera: CameraConfig;
  enableControls?: boolean;
  backgroundColor?: string | number;
  antialias?: boolean;
  pixelRatio?: number;
}
