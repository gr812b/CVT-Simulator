import * as THREE from 'three';
import { GLTFLoader } from 'three/examples/jsm/loaders/GLTFLoader.js';
import { DRACOLoader } from 'three/examples/jsm/loaders/DRACOLoader.js';
import type { Model3DConfig } from '@types';
import type { ConstantsResponse } from '@utils/api';
import type { Scene3DController } from '@utils/Scene3DController';
import { CVT_MODEL_CONFIGS } from './modelConfigs';

/**
 * Load all CVT models from configuration with proper materials and shadows.
 */
export const loadCVTModels = async (
  constants: ConstantsResponse
): Promise<Model3DConfig[]> => {
  const loader = new GLTFLoader();

  // Configure Draco decoder for compressed models
  const dracoLoader = new DRACOLoader();
  dracoLoader.setDecoderPath('https://www.gstatic.com/draco/versioned/decoders/1.5.6/');
  loader.setDRACOLoader(dracoLoader);

  const models: Model3DConfig[] = [];

  // Load all models sequentially
  for (const config of CVT_MODEL_CONFIGS) {
    try {
      const gltf = await new Promise<THREE.Object3D>((resolve, reject) => {
        loader.load(
          config.modelUrl,
          (gltf) => resolve(gltf.scene),
          undefined,
          reject
        );
      });

      // Apply CAD-like material for clean, professional appearance
      gltf.traverse((child) => {
        if (child instanceof THREE.Mesh) {
          child.material = new THREE.MeshPhysicalMaterial({
            color: config.color,
            metalness: 0.6,
            roughness: 0.3,
            clearcoat: 0.3,
            clearcoatRoughness: 0.2,
            reflectivity: 0.5,
            envMapIntensity: 1.0,
            flatShading: false,
            side: THREE.DoubleSide, // Render both sides in case normals are flipped
          });
          child.castShadow = true;
          child.receiveShadow = true;

          // Ensure geometry has proper normals
          if (child.geometry) {
            child.geometry.computeVertexNormals();
          }
        }
      });

      models.push({
        id: config.id,
        parentId: config.parentId,
        object3D: gltf,
        position: config.getInitialPosition(constants),
        rotation: config.rotation,
      });
    } catch (error) {
      console.error(`Error loading model ${config.id}:`, error);
    }
  }

  return models;
};

/**
 * Setup scene lighting for CAD-style visualization.
 * Returns cleanup function to remove all lights.
 */
export const setupSceneLighting = (sceneController: Scene3DController): (() => void) => {
  // Add hemisphere light for ambient fill
  const hemiLight = new THREE.HemisphereLight(0xffffff, 0x444444, 0.8);
  sceneController.addObject(hemiLight);

  // Add ambient light for overall brightness
  const ambientLight = new THREE.AmbientLight(0xffffff, 0.5);
  sceneController.addObject(ambientLight);

  // Add directional lights from multiple angles
  const dirLight1 = new THREE.DirectionalLight(0xffffff, 0.8);
  dirLight1.position.set(5, 10, 5);
  sceneController.addObject(dirLight1);

  const dirLight2 = new THREE.DirectionalLight(0xffffff, 0.4);
  dirLight2.position.set(-5, 5, -5);
  sceneController.addObject(dirLight2);

  const dirLight3 = new THREE.DirectionalLight(0xffffff, 0.4);
  dirLight3.position.set(0, 5, -10);
  sceneController.addObject(dirLight3);

  // Return cleanup function
  return () => {
    sceneController.removeObject(hemiLight);
    sceneController.removeObject(ambientLight);
    sceneController.removeObject(dirLight1);
    sceneController.removeObject(dirLight2);
    sceneController.removeObject(dirLight3);
  };
};

/**
 * Setup grid helper for spatial reference.
 * Returns cleanup function to remove the grid.
 */
export const setupSceneGrid = (sceneController: Scene3DController): (() => void) => {
  const gridSize = 20; // 20 inch x 20 inch grid
  const divisions = 20; // 20 divisions = 1 inch per division
  const gridHelper = new THREE.GridHelper(gridSize, divisions, 0x444444, 0x222222);
  gridHelper.position.y = 0; // Grid at ground level

  sceneController.addObject(gridHelper);

  // Return cleanup function
  return () => {
    sceneController.removeObject(gridHelper);
  };
};
