import * as THREE from 'three';
import type { Model3DConfig, ModelTransform } from '@utils/sceneTypes';

/**
 * Represents a 3D model with hierarchical transformations.
 * Models can be nested to create parent-child relationships where
 * child transformations are relative to their parent.
 */
export class Model3D {
  public readonly id: string;
  public readonly object3D: THREE.Object3D;
  private parent: Model3D | null = null;
  private children: Model3D[] = [];

  constructor(config: Model3DConfig) {
    this.id = config.id;
    this.object3D = config.object3D;

    // Set initial transform
    if (config.position) {
      this.object3D.position.set(...config.position);
    }
    if (config.rotation) {
      this.object3D.rotation.set(...config.rotation);
    }
    if (config.scale) {
      this.object3D.scale.set(...config.scale);
    }
  }

  /**
   * Set the parent of this model.
   * Automatically handles Three.js scene graph hierarchy.
   */
  setParent(parent: Model3D | null): void {
    // Remove from old parent
    if (this.parent) {
      this.parent.removeChild(this);
    }

    // Set new parent
    this.parent = parent;

    if (parent) {
      parent.addChild(this);
      parent.object3D.add(this.object3D);
    }
  }

  /**
   * Get the parent model
   */
  getParent(): Model3D | null {
    return this.parent;
  }

  /**
   * Add a child model
   */
  private addChild(child: Model3D): void {
    if (!this.children.includes(child)) {
      this.children.push(child);
    }
  }

  /**
   * Remove a child model
   */
  private removeChild(child: Model3D): void {
    const index = this.children.indexOf(child);
    if (index !== -1) {
      this.children.splice(index, 1);
      this.object3D.remove(child.object3D);
    }
  }

  /**
   * Get all children
   */
  getChildren(): readonly Model3D[] {
    return this.children;
  }

  /**
   * Update the transform of this model.
   * Transformations are relative to the parent (if any).
   */
  updateTransform(transform: ModelTransform): void {
    if (transform.position) {
      this.object3D.position.set(...transform.position);
    }
    if (transform.rotation) {
      this.object3D.rotation.set(...transform.rotation);
    }
    if (transform.scale) {
      this.object3D.scale.set(...transform.scale);
    }
  }

  /**
   * Get current position in local space (relative to parent)
   */
  getLocalPosition(): THREE.Vector3 {
    return this.object3D.position.clone();
  }

  /**
   * Get current position in world space
   */
  getWorldPosition(): THREE.Vector3 {
    const worldPos = new THREE.Vector3();
    this.object3D.getWorldPosition(worldPos);
    return worldPos;
  }

  /**
   * Get current rotation in local space
   */
  getLocalRotation(): THREE.Euler {
    return this.object3D.rotation.clone();
  }

  /**
   * Get current rotation in world space
   */
  getWorldRotation(): THREE.Euler {
    const worldQuat = new THREE.Quaternion();
    this.object3D.getWorldQuaternion(worldQuat);
    return new THREE.Euler().setFromQuaternion(worldQuat);
  }

  /**
   * Set position in local space
   */
  setLocalPosition(x: number, y: number, z: number): void {
    this.object3D.position.set(x, y, z);
  }

  /**
   * Set rotation in local space (radians)
   */
  setLocalRotation(x: number, y: number, z: number): void {
    this.object3D.rotation.set(x, y, z);
  }

  /**
   * Set scale
   */
  setScale(x: number, y: number, z: number): void {
    this.object3D.scale.set(x, y, z);
  }

  /**
   * Rotate around local axes
   */
  rotateLocal(axis: 'x' | 'y' | 'z', angle: number): void {
    switch (axis) {
      case 'x':
        this.object3D.rotateX(angle);
        break;
      case 'y':
        this.object3D.rotateY(angle);
        break;
      case 'z':
        this.object3D.rotateZ(angle);
        break;
    }
  }

  /**
   * Translate in local space
   */
  translateLocal(x: number, y: number, z: number): void {
    this.object3D.translateX(x);
    this.object3D.translateY(y);
    this.object3D.translateZ(z);
  }

  /**
   * Clean up resources
   */
  dispose(): void {
    // Remove from parent
    if (this.parent) {
      this.parent.removeChild(this);
      this.parent = null;
    }

    // Recursively dispose children
    [...this.children].forEach((child) => {
      child.dispose();
    });
    this.children = [];

    // Traverse and dispose geometries and materials
    this.object3D.traverse((obj) => {
      if (obj instanceof THREE.Mesh) {
        obj.geometry?.dispose();
        if (obj.material) {
          if (Array.isArray(obj.material)) {
            obj.material.forEach((mat) => mat.dispose());
          } else {
            obj.material.dispose();
          }
        }
      }
    });
  }
}
