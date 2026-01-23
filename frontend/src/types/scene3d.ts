import type * as THREE from 'three';

/**
 * Configuration for a 3D model in the scene
 */
export interface Model3DConfig {
  /** Unique identifier for the model */
  id: string;
  /** Optional parent model ID for hierarchical relationships */
  parentId?: string;
  /** Initial position [x, y, z] relative to parent (or world if no parent) */
  position?: [number, number, number];
  /** Initial rotation [x, y, z] in radians relative to parent */
  rotation?: [number, number, number];
  /** Initial scale [x, y, z] */
  scale?: [number, number, number];
  /** Three.js object to render (mesh, group, etc.) */
  object3D: THREE.Object3D;
}

/**
 * Transform update for a model during replay
 */
export interface ModelTransform {
  /** Position update [x, y, z] */
  position?: [number, number, number];
  /** Rotation update [x, y, z] in radians */
  rotation?: [number, number, number];
  /** Scale update [x, y, z] */
  scale?: [number, number, number];
}

/**
 * Camera configuration for the 3D scene
 */
export interface CameraConfig {
  /** Camera type */
  type: 'perspective' | 'orthographic';
  /** Field of view for perspective camera (degrees) */
  fov?: number;
  /** Camera position [x, y, z] */
  position: [number, number, number];
  /** Point to look at [x, y, z] */
  lookAt: [number, number, number];
  /** Near clipping plane */
  near?: number;
  /** Far clipping plane */
  far?: number;
}

/**
 * Scene configuration
 */
export interface Scene3DConfig {
  /** Canvas element or container to render into */
  container: HTMLElement;
  /** Camera configuration */
  camera: CameraConfig;
  /** Enable orbit controls */
  enableControls?: boolean;
  /** Background color (hex string or THREE.Color) */
  backgroundColor?: string | number;
  /** Enable antialiasing */
  antialias?: boolean;
  /** Pixel ratio (defaults to window.devicePixelRatio) */
  pixelRatio?: number;
}
