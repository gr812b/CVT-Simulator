import { useEffect, useMemo, useRef } from 'react';
import { Alert } from '@mantine/core';
import { Box3, Vector3, PerspectiveCamera, OrthographicCamera } from 'three';
import type { SlidingBlockDemo, SlidingBlockFrame } from '@api/client';
import { useScene3D } from '@hooks/useScene3D';
import {
  buildSlidingBlockModels,
  positionSlidingBlockModels,
  updateSampleBelt,
} from './slidingBlockModels';
import styles from './SlidingBlock.module.scss';

export function SlidingBlockScene({
  data,
  frame,
  cutaway,
  contacts,
  reset,
}: {
  data: SlidingBlockDemo;
  frame: SlidingBlockFrame;
  cutaway: boolean;
  contacts: boolean;
  reset: number;
}) {
  const models = useMemo(
    () => buildSlidingBlockModels(data, cutaway),
    [data, cutaway]
  );
  const { containerRef, sceneController, error } = useScene3D({
    models,
    sceneConfig: {
      camera: {
        type: 'perspective',
        fov: 38,
        position: [0.22, 0.13, 0.28],
        lookAt: [0, 0, 0],
        near: 0.001,
        far: 10,
      },
      enableControls: true,
      transparentBackground: true,
      orbitOnly: false,
      renderOnDemand: true,
    },
  });
  const fit = useRef<{ controller: unknown; reset: number } | null>(null);
  useEffect(() => {
    if (!sceneController) return;
    if (
      fit.current?.controller !== sceneController ||
      fit.current.reset !== reset
    ) {
      sceneController.resetView();
      sceneController.fitBounds(
        new Box3(new Vector3(-0.075, -0.1, -0.1), new Vector3(0.145, 0.1, 0.1))
      );
      const camera = sceneController.getCamera();
      if (
        camera instanceof PerspectiveCamera ||
        camera instanceof OrthographicCamera
      ) {
        camera.zoom =
          (containerRef.current?.clientWidth ?? 0) > 600 ? 1.4 : 1.12;
        camera.updateProjectionMatrix();
      }
      fit.current = { controller: sceneController, reset };
    }
    positionSlidingBlockModels(sceneController, data, frame, contacts);
    updateSampleBelt(sceneController, frame, cutaway);
  }, [
    sceneController,
    data,
    frame,
    contacts,
    cutaway,
    reset,
    models,
    containerRef,
  ]);
  return (
    <div
      className={styles.scene}
      ref={containerRef}
      role="img"
      aria-label="Orbitable 3D sliding-block primary assembly"
      data-testid="sliding-3d"
    >
      {error && (
        <Alert color="yellow" className={styles.sceneError}>
          3D view unavailable. The section view below shows the same assembly
          and motion.
        </Alert>
      )}
    </div>
  );
}
