import * as THREE from 'three';
import type { Scene3DController } from '@utils/Scene3DController';
import { sceneAppearance } from '../../styles/theme';
import { createBeltMesh } from './beltGeometry';

const originalAppearance = new WeakMap<
  THREE.Material,
  { opacity: number; transparent: boolean; depthWrite: boolean }
>();

/** Ghost every physical assembly recursively, leaving force arrows and guides opaque. */
export function setCVTModelsTransparent(
  controller: Scene3DController,
  transparent: boolean,
): void {
  const materials = new Set<THREE.Material>();
  const roots = [
    controller.getModel('primaryFixed')?.object3D,
    controller.getModel('secondaryFixed')?.object3D,
    controller.getScene().getObjectByName('cvt-belt'),
  ];
  roots.forEach((root) =>
    root?.traverse((object) => {
      if (object instanceof THREE.Mesh) {
        (Array.isArray(object.material)
          ? object.material
          : [object.material]
        ).forEach((material) => materials.add(material));
      }
    }),
  );
  materials.forEach((material) => {
    let original = originalAppearance.get(material);
    if (!original) {
      original = {
        opacity: material.opacity,
        transparent: material.transparent,
        depthWrite: material.depthWrite,
      };
      originalAppearance.set(material, original);
    }
    material.transparent = transparent || original.transparent;
    material.opacity = transparent
      ? original.opacity * sceneAppearance.ghostOpacity
      : original.opacity;
    material.depthWrite = transparent ? false : original.depthWrite;
    material.needsUpdate = true;
  });
}

export function setupSceneGrid(controller: Scene3DController): () => void {
  const grid = new THREE.GridHelper(
    20,
    20,
    sceneAppearance.grid,
    sceneAppearance.grid,
  );
  controller.addObject(grid);
  return () => {
    controller.removeObject(grid);
    grid.dispose();
  };
}

export function setupAxisHelpers(controller: Scene3DController): () => void {
  const axes = new THREE.AxesHelper(10);
  controller.addObject(axes);
  return () => {
    controller.removeObject(axes);
    axes.dispose();
  };
}

export function setupVerticalGrid(controller: Scene3DController): () => void {
  const grid = new THREE.GridHelper(
    20,
    20,
    sceneAppearance.grid,
    sceneAppearance.grid,
  );
  grid.rotation.x = Math.PI / 2;
  controller.addObject(grid);
  return () => {
    controller.removeObject(grid);
    grid.dispose();
  };
}

export function setupBelt(controller: Scene3DController): {
  beltMesh: THREE.Mesh;
  cleanup: () => void;
} {
  const mesh = createBeltMesh();
  mesh.name = 'cvt-belt';
  mesh.castShadow = true;
  mesh.receiveShadow = true;
  controller.addObject(mesh);
  return {
    beltMesh: mesh,
    cleanup: () => {
      controller.removeObject(mesh);
      mesh.traverse((object) => {
        if (!(object instanceof THREE.Mesh)) return;
        object.geometry.dispose();
        (Array.isArray(object.material)
          ? object.material
          : [object.material]
        ).forEach((material) => material.dispose());
      });
    },
  };
}
