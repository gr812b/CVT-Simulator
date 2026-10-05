import * as THREE from 'three';
import type { Scene3DController } from '@utils/Scene3DController';
import { sceneAppearance } from '../../styles/theme';
import { CVT_MODEL_IDS } from './proceduralModels';
import { createBeltMesh } from './beltGeometry';

/** Reveal the working mechanisms through their enclosing sheaves and cam wall. */
export function setCVTModelsTransparent(
  controller: Scene3DController,
  transparent: boolean,
): void {
  [...CVT_MODEL_IDS, 'helix'].forEach((id) => {
    const model = controller.getModel(id);
    if (!model) return;
    model.object3D.children.forEach((object) => {
      if (!(object instanceof THREE.Mesh)) return;
      if (id === 'helix' && object.name !== 'slot-wall') return;
      const materials = Array.isArray(object.material)
        ? object.material
        : [object.material];
      materials.forEach((material) => {
        material.transparent = transparent;
        material.opacity = transparent ? sceneAppearance.ghostOpacity : 1;
        material.depthWrite = !transparent;
        material.needsUpdate = true;
      });
    });
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
