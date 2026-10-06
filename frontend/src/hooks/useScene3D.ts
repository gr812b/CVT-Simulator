import { useEffect, useRef, useState } from 'react';
import type { Model3DConfig, Scene3DConfig } from '@utils/sceneTypes';
import { Scene3DController } from '@utils/Scene3DController';

interface UseScene3DOptions {
  sceneConfig: Omit<Scene3DConfig, 'container'>;
  models?: Model3DConfig[];
}

interface UseScene3DReturn {
  containerRef: React.RefObject<HTMLDivElement | null>;
  sceneController: Scene3DController | null;
  isReady: boolean;
  error: string | null;
}

/** Generic Three.js lifecycle. It has no CVT or backend knowledge. */
export function useScene3D({
  sceneConfig,
  models = [],
}: UseScene3DOptions): UseScene3DReturn {
  const containerRef = useRef<HTMLDivElement>(null);
  const [sceneController, setSceneController] =
    useState<Scene3DController | null>(null);
  const [isReady, setIsReady] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const addedModels = useRef<Model3DConfig[]>([]);

  useEffect(() => {
    if (containerRef.current === null) return;
    let controller: Scene3DController;
    try {
      controller = new Scene3DController({
        ...sceneConfig,
        container: containerRef.current,
      });
    } catch {
      setError(
        'The 3D preview needs WebGL. You can still explore the workspace and run data.',
      );
      return;
    }
    setSceneController(controller);
    setIsReady(true);

    return () => {
      controller.dispose();
      addedModels.current = [];
      setSceneController(null);
      setIsReady(false);
    };
    // A scene is intentionally constructed once per viewer mount.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (sceneController === null) return;
    const previous = addedModels.current;
    if (
      previous.length === models.length &&
      previous.every((model, i) => model === models[i])
    )
      return;
    // Children are removed before parents so reusing an ID cannot leave stale
    // geometry attached after a study or result changes.
    [...previous]
      .reverse()
      .forEach((model) => sceneController.removeModel(model.id));
    models.forEach((model) => sceneController.addModel(model));
    addedModels.current = models;
  }, [models, sceneController]);

  return { containerRef, sceneController, isReady, error };
}
