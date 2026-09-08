import * as THREE from 'three';
import { GLTFLoader } from 'three/examples/jsm/loaders/GLTFLoader.js';
import { DRACOLoader } from 'three/examples/jsm/loaders/DRACOLoader.js';
import type { Model3DConfig } from '@utils/sceneTypes';
import type { Scene3DController } from '@utils/Scene3DController';
import type { SceneGeometry } from './sceneSpec';
import { CVT_MODEL_CONFIGS } from './modelConfigs';
import { createBeltMesh } from './beltGeometry';

const GHOST_OPACITY = 0.22;

export async function loadCVTModels(geometry: SceneGeometry): Promise<Model3DConfig[]> {
  const loader = new GLTFLoader();
  const draco = new DRACOLoader();
  draco.setDecoderPath('https://www.gstatic.com/draco/versioned/decoders/1.5.6/');
  loader.setDRACOLoader(draco);
  const models: Model3DConfig[] = [];

  for (const config of CVT_MODEL_CONFIGS) {
    try {
      const object = await new Promise<THREE.Object3D>((resolve, reject) => loader.load(
        config.modelUrl,
        (gltf) => resolve(gltf.scene),
        undefined,
        reject,
      ));
      object.traverse((child) => {
        if (!(child instanceof THREE.Mesh)) return;
        child.material = new THREE.MeshPhysicalMaterial({
          color: config.color,
          metalness: 0.6,
          roughness: 0.3,
          clearcoat: 0.3,
          clearcoatRoughness: 0.2,
          reflectivity: 0.5,
          envMapIntensity: 1,
          flatShading: false,
          side: THREE.DoubleSide,
        });
        child.castShadow = true;
        child.receiveShadow = true;
        child.geometry.computeVertexNormals();
      });
      models.push({
        id: config.id,
        parentId: config.parentId,
        object3D: object,
        position: config.getInitialPosition(geometry),
        rotation: config.rotation,
      });
    } catch (error) {
      console.error(`Failed to load ${config.id}`, error);
    }
  }
  return models;
}

/** Toggle a translucent "ghosted" view of the pulley CAD without touching the belt. */
export function setCVTModelsTransparent(
  controller: Scene3DController,
  transparent: boolean,
): void {
  CVT_MODEL_CONFIGS.forEach((config) => {
    const model = controller.getModel(config.id);
    if (!model) return;
    model.object3D.traverse((object) => {
      if (!(object instanceof THREE.Mesh)) return;
      const materials = Array.isArray(object.material) ? object.material : [object.material];
      materials.forEach((material) => {
        material.transparent = transparent;
        material.opacity = transparent ? GHOST_OPACITY : 1;
        material.depthWrite = !transparent;
        material.needsUpdate = true;
      });
    });
  });
}

export function setupSceneLighting(controller: Scene3DController): () => void {
  const lights: THREE.Light[] = [
    new THREE.HemisphereLight(0xffffff, 0x444444, 0.8),
    new THREE.AmbientLight(0xffffff, 0.5),
    new THREE.DirectionalLight(0xffffff, 0.8),
    new THREE.DirectionalLight(0xffffff, 0.4),
    new THREE.DirectionalLight(0xffffff, 0.4),
  ];
  (lights[2] as THREE.DirectionalLight).position.set(5, 10, 5);
  (lights[3] as THREE.DirectionalLight).position.set(-5, 5, -5);
  (lights[4] as THREE.DirectionalLight).position.set(0, 5, -10);
  lights.forEach((light) => controller.addObject(light));
  return () => lights.forEach((light) => controller.removeObject(light));
}

export function setupSceneGrid(controller: Scene3DController): () => void {
  const grid = new THREE.GridHelper(20, 20, 0x444444, 0x222222);
  controller.addObject(grid);
  return () => controller.removeObject(grid);
}

export function setupAxisHelpers(controller: Scene3DController): () => void {
  const axes = new THREE.AxesHelper(10);
  controller.addObject(axes);
  return () => controller.removeObject(axes);
}

export function setupVerticalGrid(controller: Scene3DController): () => void {
  const grid = new THREE.GridHelper(20, 20, 0xffffff, 0x888888);
  grid.rotation.x = Math.PI / 2;
  controller.addObject(grid);
  return () => controller.removeObject(grid);
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
      mesh.geometry.dispose();
      if (Array.isArray(mesh.material)) mesh.material.forEach((material) => material.dispose());
      else mesh.material.dispose();
    },
  };
}
