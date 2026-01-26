import { useCallback, useEffect, useState } from 'react';
import type { Model3DConfig } from '@types';
import { useScene3D } from '@hooks/useScene3D';
import { ReplayController, ReplayEventType } from '@utils/ReplayController';
import { getConstants, type ConstantsResponse } from '@utils/api';
import { convertConstants, convertValue } from '@utils/conversion';
import styles from './Scene3DViewer.module.scss';
import { SCENE_DISTANCE_UNIT, SCENE_ANGLE_UNIT } from './modelConfigs';
import { loadCVTModels, setupSceneLighting, setupSceneGrid } from './sceneElements';

interface Scene3DViewerProps {
  replayController: ReplayController;
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
  const [isLoading, setIsLoading] = useState(true);

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
    setIsLoading(true);
    getConstants()
      .then((rawConstants) => {
        // Convert all constants to scene units
        const converted = convertConstants(rawConstants, { distance: SCENE_DISTANCE_UNIT, angle: SCENE_ANGLE_UNIT });
        setConstants(converted);
      })
      .catch(console.error);
  }, []);

  useEffect(() => {
    if (!constants) return;

    loadCVTModels(constants)
      .then((models) => {
        setLoadedModels(models);
        setIsLoading(false);
      })
      .catch((error) => {
        console.error(error);
        setIsLoading(false);
      });
  }, [constants]);

  const { containerRef, sceneController } = useScene3D({
    sceneConfig: {
      camera: {
        type: 'perspective',
        fov: 50,
        position: [7, 7, 12],
        lookAt: [0, 0, 0],
      },
      enableControls: true,
      backgroundColor: 0x2a2a2a,
      antialias: true,
    },
    models: loadedModels,
  });

  useEffect(() => {
    if (!sceneController) return;
    return setupSceneLighting(sceneController);
  }, [sceneController]);

  useEffect(() => {
    if (!sceneController) return;
    return setupSceneGrid(sceneController);
  }, [sceneController]);

  // Subscribe to replay controller and update models
  useEffect(() => {
    if (!sceneController || !constants) return;

    const unsubscribe = replayController.on((event) => {
      if (event.type === ReplayEventType.Progress) {
        // Extract angular velocities and shift distance
        const primaryAngularPosition = event.data.system?.cvt?.primaryPulleyState?.angular_position ?? 0;
        const secondaryAngularPosition = event.data.system?.cvt?.secondaryPulleyState?.angular_position ?? 0;
        const shiftDistance = event.data.state?.shift_distance ?? 0;

        // Angular positions are already in radians from backend, use directly for 3D rotation
        // (Three.js rotations use radians)
        const shiftDistanceScene = toSceneDistance(shiftDistance);

        // Update all models
        sceneController.updateModels({
          primaryFixed: {
            // TODO: Use angular position
            rotation: [0, Math.PI, primaryAngularPosition],
          },
          primaryMoving: {
            // Primary closes as shift increases: max_shift - shift_distance
            position: [0, 0, -(constants.max_shift - shiftDistanceScene)],
          },
          secondaryFixed: {
            // TODO: Use angular position
            rotation: [0, 0, secondaryAngularPosition],
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

  return (
    <div ref={containerRef} className={`${styles.scene3dViewer} ${className ?? ''}`}>
      {isLoading && (
        <div className={styles.loadingOverlay}>
          <div className={styles.spinner} />
          <p>Loading 3D models...</p>
        </div>
      )}
    </div>
  );
};
