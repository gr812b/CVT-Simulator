import { useCallback, useEffect, useState } from 'react';
import type { Model3DConfig } from '@types';
import { useScene3D } from '@hooks/useScene3D';
import { ReplayController, ReplayEventType } from '@utils/ReplayController';
import { getConstants, type ConstantsResponse } from '@utils/api';
import { convertConstants, convertValue } from '@utils/conversion';
import styles from './Scene3DViewer.module.scss';
import { SCENE_DISTANCE_UNIT, SCENE_ANGLE_UNIT, primaryOffset, secondaryOffset } from './modelConfigs';
import { loadCVTModels, setupSceneLighting, setupSceneGrid, setupBelt, setupAxisHelpers, setupVerticalGrid } from './sceneElements';
import { updateBeltMesh, type BeltPathData } from './beltGeometry';
import * as THREE from 'three';

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
  const [beltMesh, setBeltMesh] = useState<THREE.Mesh | null>(null);
  const [beltVisible, setBeltVisible] = useState(true);
  const [showAngularRotation, setShowAngularRotation] = useState(true);
  const [gridsVisible, setGridsVisible] = useState(true);
  const [gridObjects, setGridObjects] = useState<THREE.Object3D[]>([]);
  const [initialHelixRotation, setInitialHelixRotation] = useState<number>(0);

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
      .catch((error) => alert(`Failed to load simulator constants: ${error instanceof Error ? error.message : String(error)}`));
  }, []);

  useEffect(() => {
    if (!constants) return;

    loadCVTModels(constants)
      .then((models) => {
        setLoadedModels(models);
        setIsLoading(false);
      })
      .catch((error) => {
        alert(`Failed to load 3D models: ${error instanceof Error ? error.message : String(error)}`);
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
    const cleanup1 = setupSceneGrid(sceneController);
    const cleanup2 = setupAxisHelpers(sceneController);
    const cleanup3 = setupVerticalGrid(sceneController);
    
    // Get the grid objects from the scene to control visibility
    const grids: THREE.Object3D[] = [];
    sceneController.getScene().traverse((obj) => {
      if (obj instanceof THREE.GridHelper || obj instanceof THREE.AxesHelper) {
        grids.push(obj);
      }
    });
    setGridObjects(grids);
    
    return () => {
      cleanup1();
      cleanup2();
      cleanup3();
    };
  }, [sceneController]);

  // Setup belt mesh with initial data from replay controller
  useEffect(() => {
    if (!sceneController || !constants) return;

    // Get first data point to initialize belt with real values
    const firstDataPoint = replayController.getFirstDataPoint();
    if (!firstDataPoint) return;

    // Store initial helix rotation for relative rotation calculations
    const firstBreakdown = firstDataPoint.system?.cvt?.secondaryPulleyState?.breakdown;
    const firstHelixRotation = (firstBreakdown && 'helix_force' in firstBreakdown)
      ? firstBreakdown.helix_force.springTorque.rotation
      : 0;
    setInitialHelixRotation(firstHelixRotation);

    const primaryRadius = firstDataPoint.system?.cvt?.primaryPulleyState?.radius ?? constants.min_prim_radius;
    const secondaryRadius = firstDataPoint.system?.cvt?.secondaryPulleyState?.radius ?? constants.max_sec_radius;
    const primaryWrapAngleDeg = firstDataPoint.system?.cvt?.primaryPulleyState?.wrap_angle ?? 180;
    const secondaryWrapAngleDeg = firstDataPoint.system?.cvt?.secondaryPulleyState?.wrap_angle ?? 180;
    const shiftDistance = firstDataPoint.state?.shift_distance ?? 0;

    const primaryWrapAngle = primaryWrapAngleDeg * (Math.PI / 180);
    const secondaryWrapAngle = secondaryWrapAngleDeg * (Math.PI / 180);
    const shiftDistanceScene = toSceneDistance(shiftDistance);
    const primaryRadiusScene = toSceneDistance(primaryRadius);
    const secondaryRadiusScene = toSceneDistance(secondaryRadius);

    // Belt starts offset and doesn't move until shift distance exceeds initial_sheave_displacement
    const effectiveBeltShift = Math.max(constants.initial_sheave_displacement, shiftDistanceScene);
    const beltZ = -effectiveBeltShift / 2;

    const initialPathData: BeltPathData = {
      primaryRadius: primaryRadiusScene,
      primaryPosition: [-constants.center_to_center / 2, 0, beltZ],
      secondaryRadius: secondaryRadiusScene,
      secondaryPosition: [constants.center_to_center / 2, 0, beltZ],
      primaryWrapAngle,
      secondaryWrapAngle,
    };

    const { beltMesh: mesh, cleanup } = setupBelt(sceneController, constants);
    mesh.visible = beltVisible;
    // Update with actual first data point immediately
    updateBeltMesh(mesh, initialPathData, constants);
    setBeltMesh(mesh);

    return cleanup;
  }, [sceneController, constants, replayController, toSceneDistance, beltVisible]);

  // Subscribe to replay controller and update models
  useEffect(() => {
    if (!sceneController || !constants || !beltMesh) return;

    const unsubscribe = replayController.on((event) => {
      if (event.type === ReplayEventType.Progress) {
        // Extract angular positions and shift distance
        const primaryAngularPosition = event.data.system?.cvt?.primaryPulleyState?.angular_position ?? 0;
        const secondaryAngularPosition = event.data.system?.cvt?.secondaryPulleyState?.angular_position ?? 0;
        const secondaryBreakdown = event.data.system?.cvt?.secondaryPulleyState?.breakdown;
        const secondaryHelixRotationDeg = (secondaryBreakdown && 'helix_force' in secondaryBreakdown) 
          ? secondaryBreakdown.helix_force.springTorque.rotation - initialHelixRotation
          : 0;
        const secondaryHelixRotation = secondaryHelixRotationDeg * (Math.PI / 180);
        const shiftDistance = event.data.state?.shift_distance ?? 0;

        // Get pulley states for belt calculation
        const primaryRadius = event.data.system?.cvt?.primaryPulleyState?.radius ?? constants.min_prim_radius;
        const secondaryRadius = event.data.system?.cvt?.secondaryPulleyState?.radius ?? constants.max_sec_radius;
        const primaryWrapAngleDeg = event.data.system?.cvt?.primaryPulleyState?.wrap_angle ?? 180;
        const secondaryWrapAngleDeg = event.data.system?.cvt?.secondaryPulleyState?.wrap_angle ?? 180;
        
        // Convert wrap angles from degrees to radians for Three.js
        const primaryWrapAngle = primaryWrapAngleDeg * (Math.PI / 180);
        const secondaryWrapAngle = secondaryWrapAngleDeg * (Math.PI / 180);

        // Angular positions are already in radians from backend, use directly for 3D rotation
        // (Three.js rotations use radians)
        const shiftDistanceScene = toSceneDistance(shiftDistance);
        const primaryRadiusScene = toSceneDistance(primaryRadius);
        const secondaryRadiusScene = toSceneDistance(secondaryRadius);


        // Secondary doesn't move until shift distance exceeds initial_sheave_displacement
        const effectiveSecondaryShift = Math.max(0, shiftDistanceScene - constants.initial_sheave_displacement);

        // Update all models
        sceneController.updateModels({
          primaryFixed: {
            rotation: [0, Math.PI, showAngularRotation ? primaryAngularPosition : 0],
          },
          primaryMoving: {
            // Primary closes as shift increases: max_shift - shift_distance
            // Position is relative to parent (primaryFixed), so just the offset change
            position: [0, 0, -(primaryOffset + constants.max_shift - shiftDistanceScene)],
          },
          secondaryFixed: {
            rotation: [0, 0, showAngularRotation ? secondaryAngularPosition : 0],
          },
          secondaryMoving: {
            // Secondary opens as shift increases: shift_distance
            // Position is relative to parent (secondaryFixed), so apply the offset
            // Only moves after initial_sheave_displacement is exceeded
            position: [0, 0, -(secondaryOffset + effectiveSecondaryShift)],
            // Add helix spring rotation (relative to the fixed sheave)
            rotation: [0, 0, -secondaryHelixRotation],
          },
        });

        // Update belt mesh - starts at initial_sheave_displacement and only moves when shift exceeds it
        const effectiveBeltShift = Math.max(constants.initial_sheave_displacement, shiftDistanceScene);
        const beltZ = -effectiveBeltShift / 2;

        const beltPathData: BeltPathData = {
          primaryRadius: primaryRadiusScene,
          primaryPosition: [-constants.center_to_center / 2, 0, beltZ],
          secondaryRadius: secondaryRadiusScene,
          secondaryPosition: [constants.center_to_center / 2, 0, beltZ],
          primaryWrapAngle,
          secondaryWrapAngle,
        };

        updateBeltMesh(beltMesh, beltPathData, constants);
      }
    });

    return unsubscribe;
  }, [sceneController, replayController, constants, toSceneDistance, beltMesh, initialHelixRotation, showAngularRotation]);

  // Update belt visibility when state changes
  useEffect(() => {
    if (beltMesh) {
      beltMesh.visible = beltVisible;
    }
  }, [beltVisible, beltMesh]);

  // Update grid visibility when state changes
  useEffect(() => {
    gridObjects.forEach(grid => {
      grid.visible = gridsVisible;
    });
  }, [gridsVisible, gridObjects]);

  return (
    <div ref={containerRef} className={`${styles.scene3dViewer} ${className ?? ''}`}>
      {isLoading && (
        <div className={styles.loadingOverlay}>
          <div className={styles.spinner} />
          <p>Loading 3D models...</p>
        </div>
      )}
      <button
        className={styles.toggleBeltButton}
        onClick={() => setBeltVisible(!beltVisible)}
        title={beltVisible ? 'Hide Belt' : 'Show Belt'}
      >
        {beltVisible ? '🔴' : '⚪'} Belt
      </button>
      <button
        className={styles.toggleRotationButton}
        onClick={() => setShowAngularRotation(!showAngularRotation)}
        title={showAngularRotation ? 'Hide Angular Rotation' : 'Show Angular Rotation'}
      >
        {showAngularRotation ? '🔵' : '⚪'} Rotation
      </button>
      <button
        className={styles.toggleGridsButton}
        onClick={() => setGridsVisible(!gridsVisible)}
        title={gridsVisible ? 'Hide Grids' : 'Show Grids'}
      >
        {gridsVisible ? '🟢' : '⚪'} Grids
      </button>
    </div>
  );
};
