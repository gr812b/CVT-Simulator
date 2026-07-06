import { useEffect, useRef, useState } from 'react';
import type { Scene3DConfig, Model3DConfig } from '@types';
import { Scene3DController } from '@utils/Scene3DController';

interface UseScene3DOptions {
  /** Scene configuration */
  sceneConfig: Omit<Scene3DConfig, 'container'>;
  /** Model configurations to add to the scene */
  models?: Model3DConfig[];
}

interface UseScene3DReturn {
  /** Reference to attach to the container element */
  containerRef: React.RefObject<HTMLDivElement>;
  /** The scene controller instance (null until mounted) */
  sceneController: Scene3DController | null;
  /** Whether the scene is ready */
  isReady: boolean;
}

/**
 * React hook for managing a Three.js 3D scene.
 * Automatically handles setup and cleanup.
 * 
 * The hook creates a Scene3DController which manages models and rendering.
 * To animate models based on data (like ReplayController), subscribe to your
 * data source in your component and call sceneController.updateModels().
 *
 * @example
 * ```tsx
 * const { containerRef, sceneController } = useScene3D({
 *   sceneConfig: {
 *     camera: { type: 'perspective', position: [10, 10, 10], lookAt: [0, 0, 0] },
 *     enableControls: true,
 *   },
 *   models: [{ id: 'box', object3D: boxMesh, position: [0, 0, 0] }],
 * });
 * 
 * // Subscribe to data updates in your component
 * useEffect(() => {
 *   const unsubscribe = replayController.on((event) => {
 *     if (event.type === ReplayEventType.Progress) {
 *       sceneController?.updateModels({
 *         box: { rotation: [0, event.data.system.cvt.primaryPulleyState.angular_velocity, 0] }
 *       });
 *     }
 *   });
 *   return unsubscribe;
 * }, [sceneController, replayController]);
 * 
 * return <div ref={containerRef} style={{ width: '100%', height: '600px' }} />;
 * ```
 */
export function useScene3D({
  sceneConfig,
  models = [],
}: UseScene3DOptions): UseScene3DReturn {
  const containerRef = useRef<HTMLDivElement>(null);
  const [sceneController, setSceneController] = useState<Scene3DController | null>(null);
  const [isReady, setIsReady] = useState(false);
  const addedModelIds = useRef<Set<string>>(new Set());

  // Initialize scene on mount
  useEffect(() => {
    if (!containerRef.current) return;

    const controller = new Scene3DController({
      ...sceneConfig,
      container: containerRef.current,
    });

    const modelIds = addedModelIds.current;

    setSceneController(controller);
    setIsReady(true);

    // Cleanup on unmount
    return () => {
      controller.dispose();
      setSceneController(null);
      setIsReady(false);
      modelIds.clear(); // Reset tracking when controller is disposed
    };
    // We only want to run this once on mount
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Add models when controller is ready
  useEffect(() => {
    if (!sceneController || models.length === 0) return;

    models.forEach((modelConfig) => {
      // Only add models that haven't been added yet
      if (!addedModelIds.current.has(modelConfig.id)) {
        sceneController.addModel(modelConfig);
        addedModelIds.current.add(modelConfig.id);
      }
    });

    // Note: We don't remove models on unmount since the scene controller
    // will be disposed entirely, which cleans up all models
  }, [sceneController, models]);

  return {
    containerRef,
    sceneController,
    isReady,
  };
}
