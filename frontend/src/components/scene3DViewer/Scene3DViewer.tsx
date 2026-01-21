import { useCallback, useEffect, useState } from 'react';
import * as THREE from 'three';
import { GLTFLoader } from 'three/examples/jsm/loaders/GLTFLoader.js';
import { DRACOLoader } from 'three/examples/jsm/loaders/DRACOLoader.js';
import type { Model3DConfig } from '@types';
import { useScene3D } from '@hooks/useScene3D';
import { ReplayController, ReplayEventType } from '@utils/ReplayController';
import { getConstants, type ConstantsResponse } from '@utils/api';
import { convertConstants, convertValue } from '@utils/conversion';
import styles from './Scene3DViewer.module.scss';
import { CVT_MODEL_CONFIGS, SCENE_DISTANCE_UNIT } from './modelConfigs';

interface Scene3DViewerProps {
  /** Replay controller for animation */
  replayController: ReplayController;
  /** Optional className for styling */
  className?: string;
}

/**
 * 3D viewer component that displays animated models based on simulation data.
 * Coordinates the 3D scene and subscribes to the replay controller.
 * 
 * TODO: When implementing centralized unit management context, update this component
 * to get the source unit configuration from context instead of hardcoding BAJA preset.
 */
export const Scene3DViewer = ({ replayController, className }: Scene3DViewerProps) => {
  const [loadedModels, setLoadedModels] = useState<Model3DConfig[]>([]);
  const [constants, setConstants] = useState<ConstantsResponse | null>(null);

  /**
   * Helper to convert any distance value from BAJA units (meters) to the scene's distance unit.
   * Use this for all distance values used in the 3D scene.
   * 
   * TODO: Replace hardcoded 'm' with value from centralized unit context when available.
   */
  const toSceneDistance = useCallback((valueInMeters: number): number => {
    return convertValue(valueInMeters, 'distance', SCENE_DISTANCE_UNIT);
  }, []);

  // Fetch simulator constants
  useEffect(() => {
    getConstants()
      .then((rawConstants) => {
        // Convert all constants to scene units
        const converted = convertConstants(rawConstants, { distance: SCENE_DISTANCE_UNIT });
        setConstants(converted);
      })
      .catch(console.error);
  }, []);

  // Load .glb models
  useEffect(() => {
    if (!constants) return; // Wait for constants to be loaded

    const loader = new GLTFLoader();
    
    // Configure Draco decoder for compressed models
    const dracoLoader = new DRACOLoader();
    dracoLoader.setDecoderPath('https://www.gstatic.com/draco/versioned/decoders/1.5.6/');
    loader.setDRACOLoader(dracoLoader);
    
    const models: Model3DConfig[] = [];
    let loadIndex = 0;

    // Load models sequentially based on configuration
    const loadNextModel = () => {
      if (loadIndex >= CVT_MODEL_CONFIGS.length) {
        setLoadedModels(models);
        return;
      }

      const config = CVT_MODEL_CONFIGS[loadIndex];
      loader.load(
        config.modelUrl,
        (gltf) => {
          const object = gltf.scene;
          
          // Apply CAD-like material for clean, professional appearance
          object.traverse((child) => {
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
            object3D: object,
            position: config.getInitialPosition(constants),
          });

          loadIndex++;
          loadNextModel();
        },
        undefined,
        (error) => {
          console.error(`Error loading model ${config.id}:`, error);
        }
      );
    };

    loadNextModel();
  }, [constants, toSceneDistance]);

  const { containerRef, sceneController } = useScene3D({
    sceneConfig: {
      camera: {
        type: 'perspective',
        fov: 50,
        position: [3, 2, 3],
        lookAt: [0, 0, 0],
      },
      enableControls: true,
      backgroundColor: 0x2a2a2a,
      antialias: true,
    },
    models: loadedModels,
  });

  // Add additional lighting for better CAD visualization
  useEffect(() => {
    if (!sceneController) return;

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

    return () => {
      sceneController.removeObject(hemiLight);
      sceneController.removeObject(ambientLight);
      sceneController.removeObject(dirLight1);
      sceneController.removeObject(dirLight2);
      sceneController.removeObject(dirLight3);
    };
  }, [sceneController]);

  // Add grid helper (1 inch spacing)
  useEffect(() => {
    if (!sceneController) return;

    const gridSize = 20; // 20 inch x 20 inch grid
    const divisions = 20; // 20 divisions = 1 inch per division
    const gridHelper = new THREE.GridHelper(gridSize, divisions, 0x444444, 0x222222);
    gridHelper.position.y = 0; // Grid at ground level
    
    sceneController.addObject(gridHelper);

    return () => {
      sceneController.removeObject(gridHelper);
    };
  }, [sceneController]);

  // Subscribe to replay controller and update models
  useEffect(() => {
    if (!sceneController || !constants) return;

    const unsubscribe = replayController.on((event) => {
      if (event.type === ReplayEventType.Progress) {
        // Extract angular velocities and shift distance
        const primaryAngularVelocity = event.data.system?.cvt?.primaryPulleyState?.angular_velocity ?? 0;
        const secondaryAngularVelocity = event.data.system?.cvt?.secondaryPulleyState?.angular_velocity ?? 0;
        const shiftDistance = event.data.state?.shift_distance ?? 0;

        // Convert shift distance from BAJA preset units (meters) to scene unit (inches)
        const shiftDistanceScene = toSceneDistance(shiftDistance);

        // Update all models
        sceneController.updateModels({
          primaryFixed: {
            // TODO: Use angular position
            rotation: [0, 0, primaryAngularVelocity * event.data.time],
          },
          primaryMoving: {
            // Primary closes as shift increases: max_shift - shift_distance
            position: [0, 0, -(constants.max_shift - shiftDistanceScene)],
          },
          secondaryFixed: {
            // TODO: Use angular position
            rotation: [0, 0, secondaryAngularVelocity * event.data.time],
          },
          secondaryMoving: {
            // Secondary opens as shift increases: shift_distance
            position: [0, 0, -shiftDistanceScene],
          },
        });
      }
    });

    return unsubscribe;
  }, [sceneController, replayController, constants, toSceneDistance]);

  return <div ref={containerRef} className={`${styles.scene3dViewer} ${className ?? ''}`} />;
};
