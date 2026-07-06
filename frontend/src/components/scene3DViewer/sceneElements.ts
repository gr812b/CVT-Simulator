import * as THREE from 'three';
import { GLTFLoader } from 'three/examples/jsm/loaders/GLTFLoader.js';
import { DRACOLoader } from 'three/examples/jsm/loaders/DRACOLoader.js';
import type { Model3DConfig } from '@utils/sceneTypes';
import type { Scene3DController } from '@utils/Scene3DController';
import type { SceneGeometry } from './sceneSpec';
import { CVT_MODEL_CONFIGS } from './modelConfigs';
import { calculateBeltPath, createBeltMesh, type BeltPathData } from './beltGeometry';

export async function loadCVTModels(geometry: SceneGeometry): Promise<Model3DConfig[]> {
  const loader = new GLTFLoader(); const draco = new DRACOLoader(); draco.setDecoderPath('https://www.gstatic.com/draco/versioned/decoders/1.5.6/'); loader.setDRACOLoader(draco);
  const models: Model3DConfig[] = [];
  for (const config of CVT_MODEL_CONFIGS) {
    try {
      const object = await new Promise<THREE.Object3D>((resolve, reject) => loader.load(config.modelUrl, (gltf) => resolve(gltf.scene), undefined, reject));
      object.traverse((child) => { if (child instanceof THREE.Mesh) { child.material = new THREE.MeshPhysicalMaterial({ color: config.color, metalness: 0.6, roughness: 0.3, clearcoat: 0.3, clearcoatRoughness: 0.2, reflectivity: 0.5, envMapIntensity: 1, flatShading: false, side: THREE.DoubleSide }); child.castShadow = true; child.receiveShadow = true; child.geometry.computeVertexNormals(); } });
      models.push({ id: config.id, parentId: config.parentId, object3D: object, position: config.getInitialPosition(geometry), rotation: config.rotation });
    } catch (error) { console.error(`Failed to load ${config.id}`, error); }
  }
  return models;
}

export function setupSceneLighting(controller: Scene3DController): () => void {
  const lights: THREE.Light[] = [new THREE.HemisphereLight(0xffffff, 0x444444, 0.8), new THREE.AmbientLight(0xffffff, 0.5), new THREE.DirectionalLight(0xffffff, 0.8), new THREE.DirectionalLight(0xffffff, 0.4), new THREE.DirectionalLight(0xffffff, 0.4)];
  (lights[2] as THREE.DirectionalLight).position.set(5, 10, 5); (lights[3] as THREE.DirectionalLight).position.set(-5, 5, -5); (lights[4] as THREE.DirectionalLight).position.set(0, 5, -10);
  lights.forEach((light) => controller.addObject(light)); return () => lights.forEach((light) => controller.removeObject(light));
}
export function setupSceneGrid(controller: Scene3DController): () => void { const grid = new THREE.GridHelper(20, 20, 0x444444, 0x222222); controller.addObject(grid); return () => controller.removeObject(grid); }
export function setupAxisHelpers(controller: Scene3DController): () => void { const axes = new THREE.AxesHelper(10); controller.addObject(axes); return () => controller.removeObject(axes); }
export function setupVerticalGrid(controller: Scene3DController): () => void { const grid = new THREE.GridHelper(20, 20, 0xffffff, 0x888888); grid.rotation.x = Math.PI / 2; controller.addObject(grid); return () => controller.removeObject(grid); }
export function setupBelt(controller: Scene3DController, geometry: SceneGeometry): { beltMesh: THREE.Mesh; cleanup: () => void } {
  const data: BeltPathData = { primaryRadius: 1.5, primaryPosition: [-geometry.centreDistance / 2, 0, 0], secondaryRadius: 3, secondaryPosition: [geometry.centreDistance / 2, 0, 0] };
  const mesh = createBeltMesh(calculateBeltPath(data), geometry); mesh.castShadow = true; mesh.receiveShadow = true; controller.addObject(mesh);
  return { beltMesh: mesh, cleanup: () => { controller.removeObject(mesh); mesh.geometry.dispose(); if (Array.isArray(mesh.material)) mesh.material.forEach((material) => material.dispose()); else mesh.material.dispose(); } };
}
