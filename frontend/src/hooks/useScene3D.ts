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
}

/** Generic Three.js lifecycle. It has no CVT or backend knowledge. */
export function useScene3D({ sceneConfig, models = [] }: UseScene3DOptions): UseScene3DReturn {
  const containerRef = useRef<HTMLDivElement>(null);
  const [sceneController, setSceneController] = useState<Scene3DController | null>(null);
  const [isReady, setIsReady] = useState(false);
  const addedModelIds = useRef(new Set<string>());

  useEffect(() => {
    if (containerRef.current === null) return;
    const controller = new Scene3DController({ ...sceneConfig, container: containerRef.current });
    setSceneController(controller);
    setIsReady(true);
    const currentModelIds = addedModelIds.current;
    return () => {
      controller.dispose();
      currentModelIds.clear();
      setSceneController(null);
      setIsReady(false);
    };
  // A scene is intentionally constructed once per viewer mount.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (sceneController === null) return;
    models.forEach((model) => {
      if (!addedModelIds.current.has(model.id)) {
        sceneController.addModel(model);
        addedModelIds.current.add(model.id);
      }
    });
  }, [models, sceneController]);

  return { containerRef, sceneController, isReady };
}
