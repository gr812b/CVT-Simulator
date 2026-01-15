import { useEffect, useState } from 'react';
import * as THREE from 'three';
import { OBJLoader } from 'three/examples/jsm/loaders/OBJLoader.js';
import type { Model3DConfig } from '@types';
import { useScene3D } from '@hooks/useScene3D';
import { ReplayController, ReplayEventType } from '@utils/ReplayController';
import { getConstants, type ConstantsResponse } from '@utils/api';
import { convertConstants, convertValue, type UnitOptions } from '@utils/conversion';
import styles from './Scene3DViewer.module.scss';
import primaryFixedModel from '@assets/models/primary_fixed.obj?url';
import primaryMovingModel from '@assets/models/primary_moving.obj?url';
import secondaryFixedModel from '@assets/models/secondary_fixed.obj?url';
import secondaryMovingModel from '@assets/models/secondary_moving.obj?url';

// Define the distance unit used throughout this 3D scene
// All distance values will be converted to this unit for rendering
const SCENE_DISTANCE_UNIT: UnitOptions['distance'] = 'in';

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
  const toSceneDistance = (valueInMeters: number): number => {
    return convertValue(valueInMeters, 'distance', SCENE_DISTANCE_UNIT);
  };

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

  // Load .obj models
  useEffect(() => {
    if (!constants) return; // Wait for constants to be loaded

    const loader = new OBJLoader();
    const models: Model3DConfig[] = [];

    // Load primary fixed
    loader.load(
      primaryFixedModel,
      (fixedObject) => {
        // Apply material to all meshes in the loaded object
        fixedObject.traverse((child) => {
          if (child instanceof THREE.Mesh) {
            child.material = new THREE.MeshStandardMaterial({ color: 0xff4444 });
          }
        });

        models.push({
          id: 'primaryFixed',
          object3D: fixedObject,
          position: [0, 0, -constants.center_to_center / 2], // Centered: negative half
        });

        // Load primary moving after fixed is loaded
        loader.load(
          primaryMovingModel,
          (movingObject) => {
            // Apply material to all meshes
            movingObject.traverse((child) => {
              if (child instanceof THREE.Mesh) {
                child.material = new THREE.MeshStandardMaterial({ color: 0xff8844 });
              }
            });

            models.push({
              id: 'primaryMoving',
              parentId: 'primaryFixed', // Attached to primaryFixed so it rotates together
              object3D: movingObject,
              position: [-constants.max_shift, 0, 0], // Start at max_shift (fully open)
            });

            // Load secondary fixed after primary models
            loader.load(
              secondaryFixedModel,
              (secondaryFixedObject) => {
                // Apply material
                secondaryFixedObject.traverse((child) => {
                  if (child instanceof THREE.Mesh) {
                    child.material = new THREE.MeshStandardMaterial({ color: 0x44ff44 });
                  }
                });

                models.push({
                  id: 'secondaryFixed',
                  object3D: secondaryFixedObject,
                  position: [0, 0, constants.center_to_center / 2], // Centered: positive half
                });

                // Load secondary moving after secondary fixed
                loader.load(
                  secondaryMovingModel,
                  (secondaryMovingObject) => {
                    // Apply material
                    secondaryMovingObject.traverse((child) => {
                      if (child instanceof THREE.Mesh) {
                        child.material = new THREE.MeshStandardMaterial({ color: 0x88ff44 });
                      }
                    });

                    models.push({
                      id: 'secondaryMoving',
                      parentId: 'secondaryFixed', // Attached to secondaryFixed
                      object3D: secondaryMovingObject,
                      position: [0, 0, 0], // Start at 0 (fully closed)
                    });

                    setLoadedModels(models);
                  },
                  undefined,
                  (error) => {
                    console.error('Error loading secondary moving model:', error);
                  }
                );
              },
              undefined,
              (error) => {
                console.error('Error loading secondary fixed model:', error);
              }
            );
          },
          undefined,
          (error) => {
            console.error('Error loading primary moving model:', error);
          }
        );
      },
      undefined,
      (error) => {
        console.error('Error loading primary fixed model:', error);
      }
    );
  }, [constants]);

  const { containerRef, sceneController } = useScene3D({
    sceneConfig: {
      camera: {
        type: 'perspective',
        fov: 50,
        position: [3, 2, 3],
        lookAt: [0, 0, 0],
      },
      enableControls: true,
      backgroundColor: 0x1a1a1a,
      antialias: true,
    },
    models: loadedModels,
  });

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
            rotation: [primaryAngularVelocity * event.data.time, 0, 0],
          },
          primaryMoving: {
            // Primary closes as shift increases: max_shift - shift_distance
            position: [constants.max_shift - shiftDistanceScene, 0, 0],
          },
          secondaryFixed: {
            // TODO: Use angular position
            rotation: [secondaryAngularVelocity * event.data.time, 0, 0],
          },
          secondaryMoving: {
            // Secondary opens as shift increases: shift_distance
            position: [shiftDistanceScene, 0, 0],
          },
        });
      }
    });

    return unsubscribe;
  }, [sceneController, replayController, constants]);

  return <div ref={containerRef} className={`${styles.scene3dViewer} ${className ?? ''}`} />;
};
