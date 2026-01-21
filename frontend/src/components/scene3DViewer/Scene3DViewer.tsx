import { useCallback, useEffect, useState } from 'react';
import type { Model3DConfig } from '@types';
import { useScene3D } from '@hooks/useScene3D';
import { ReplayController, ReplayEventType } from '@utils/ReplayController';
import { getConstants, type ConstantsResponse } from '@utils/api';
import { convertConstants, convertValue } from '@utils/conversion';
import styles from './Scene3DViewer.module.scss';
import { SCENE_DISTANCE_UNIT } from './modelConfigs';
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

  useEffect(() => {
    if (!constants) return;

    loadCVTModels(constants)
      .then(setLoadedModels)
      .catch(console.error);
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
