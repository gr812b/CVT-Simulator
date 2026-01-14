import { useEffect, useState } from 'react';
import * as THREE from 'three';
import { OBJLoader } from 'three/examples/jsm/loaders/OBJLoader.js';
import type { Model3DConfig } from '@types';
import { useScene3D } from '@hooks/useScene3D';
import { ReplayController, ReplayEventType } from '@utils/ReplayController';
import styles from './Scene3DViewer.module.scss';
import primaryFixedModel from '@assets/models/primary_fixed.obj?url';
import primaryMovingModel from '@assets/models/primary_moving.obj?url';
import secondaryFixedModel from '@assets/models/secondary_fixed.obj?url';
import secondaryMovingModel from '@assets/models/secondary_moving.obj?url';

// Small constant offset for primary moving position
// TODO: Get this from backend or something
const PRIMARY_MOVING_BASE_OFFSET = -0.2;

// Distance between primary and secondary pulleys
const PULLEY_SPACING = 2.5;

// Small constant offset for secondary moving position
const SECONDARY_MOVING_BASE_OFFSET = -0;

interface Scene3DViewerProps {
  /** Replay controller for animation */
  replayController: ReplayController;
  /** Optional className for styling */
  className?: string;
}

/**
 * 3D viewer component that displays animated models based on simulation data.
 * Coordinates the 3D scene and subscribes to the replay controller.
 */
export const Scene3DViewer = ({ replayController, className }: Scene3DViewerProps) => {
  const [loadedModels, setLoadedModels] = useState<Model3DConfig[]>([]);

  // Load .obj models
  useEffect(() => {
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
          position: [0, 0, 0],
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
              position: [PRIMARY_MOVING_BASE_OFFSET, 0, 0], // Initial offset on X-axis
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
                  position: [0, 0, PULLEY_SPACING], // Offset from primary by PULLEY_SPACING
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
                      position: [SECONDARY_MOVING_BASE_OFFSET, 0, 0], // Initial offset on X-axis
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
  }, []);

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
    if (!sceneController) return;

    const unsubscribe = replayController.on((event) => {
      if (event.type === ReplayEventType.Progress) {
        // Extract angular velocities and shift distance
        const primaryAngularVelocity = event.data.system?.cvt?.primaryPulleyState?.angular_velocity ?? 0;
        const secondaryAngularVelocity = event.data.system?.cvt?.secondaryPulleyState?.angular_velocity ?? 0;
        const shiftDistance = event.data.state?.shift_distance ?? 0;

        // Update all models
        sceneController.updateModels({
          primaryFixed: {
            rotation: [primaryAngularVelocity * event.data.time, 0, 0],
          },
          primaryMoving: {
            // Position offset by shift_distance + base constant (relative to parent)
            // TODO: Do unit adjustment * 7 is temporary
            position: [PRIMARY_MOVING_BASE_OFFSET + shiftDistance * 7, 0, 0],
          },
          secondaryFixed: {
            rotation: [secondaryAngularVelocity * event.data.time, 0, 0],
          },
          secondaryMoving: {
            // Position offset by shift_distance + base constant (relative to parent)
            // TODO: Do unit adjustment * 7 is temporary
            position: [SECONDARY_MOVING_BASE_OFFSET + shiftDistance * 7, 0, 0],
          },
        });
      }
    });

    return unsubscribe;
  }, [sceneController, replayController]);

  return <div ref={containerRef} className={`${styles.scene3dViewer} ${className ?? ''}`} />;
};
