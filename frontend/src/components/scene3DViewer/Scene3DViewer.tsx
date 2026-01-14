import { useEffect, useMemo } from 'react';
import * as THREE from 'three';
import type { Model3DConfig } from '@types';
import { useScene3D } from '@hooks/useScene3D';
import { ReplayController, ReplayEventType } from '@utils/ReplayController';
import styles from './Scene3DViewer.module.scss';

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
  // Create a simple box model (replace with your .obj loaded models)
  const models = useMemo<Model3DConfig[]>(() => {
    const boxGeometry = new THREE.BoxGeometry(1, 1, 1);
    const boxMaterial = new THREE.MeshStandardMaterial({ color: 0x4488ff });
    const boxMesh = new THREE.Mesh(boxGeometry, boxMaterial);

    return [
      {
        id: 'rotatingBox',
        object3D: boxMesh,
        position: [0, 0, 0],
      },
    ];
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
    models,
  });

  // Subscribe to replay controller and update models
  useEffect(() => {
    if (!sceneController) return;

    const unsubscribe = replayController.on((event) => {
      if (event.type === ReplayEventType.Progress) {
        // Extract angular velocity from primary pulley
        const angularVelocity = event.data.system?.cvt?.primaryPulleyState?.angular_velocity ?? 0;

        // Update the box rotation (Y-axis spin based on angular velocity)
        sceneController.updateModels({
          rotatingBox: {
            rotation: [0, angularVelocity * event.data.time, 0] as [number, number, number],
          },
        });
      }
    });

    return unsubscribe;
  }, [sceneController, replayController]);

  return <div ref={containerRef} className={`${styles.scene3dViewer} ${className ?? ''}`} />;
};
