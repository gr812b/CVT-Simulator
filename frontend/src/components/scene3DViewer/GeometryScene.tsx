import { useEffect, useMemo, useRef } from 'react';
import { Box3, Quaternion, Vector3 } from 'three';
import { orientInspectionModels } from './inspectionFrame';
import { InspectionOverlay } from './InspectionOverlay';
import { mechanismLayout, mechanismPose } from './mechanisms';
import { Alert } from '@mantine/core';
import { useScene3D } from '@hooks/useScene3D';
import { createCVTModels, fitCVT, positionCVT } from './proceduralModels';
import { setupBelt } from './sceneElements';
import { updateBeltMesh } from './beltGeometry';
import {
  sceneConfiguration,
  sceneDistance,
  sceneGeometry,
  type ScenePreview,
} from './sceneSpec';
import styles from './Scene3DViewer.module.scss';

/** Static geometry adapter. No replay controller, result table or CAD assets. */
export default function GeometryScene({
  preview,
  frameIndex = 0,
  className,
  component,
  resetKey = 0,
}: {
  preview: ScenePreview;
  frameIndex?: number;
  className?: string;
  component?: 'primary' | 'secondary';
  resetKey?: number;
}) {
  const geometry = useMemo(
    () => sceneGeometry(preview.geometry),
    [preview.geometry],
  );
  const models = useMemo(() => {
    const built = createCVTModels(geometry, component);
    return component ? orientInspectionModels(built, component, geometry.mechanisms?.poses[0]?.secondary_angle_rad ?? 0) : built;
  }, [geometry, component]);
  const fitted = useRef<{ controller: unknown; reset: number; component?: string } | null>(null);
  // Landing scenes remain orbit-only. Tune inspection explicitly permits zoom/pan.
  const config = sceneConfiguration(false);
  config.renderOnDemand = true;
  if (component) {
    config.camera.position = [0, 0, 20];
    config.camera.lookAt = [0, 0, 0];
  }
  const { containerRef, sceneController, error } = useScene3D({
    sceneConfig: config,
    models,
  });
  const frame = preview.frames[frameIndex] ?? preview.frames[0];
  useEffect(() => {
    if (sceneController && !component) fitCVT(sceneController, geometry);
  }, [sceneController, geometry, component]);
  useEffect(() => {
    if (!sceneController || !frame) return;
    if (component) {
      positionCVT(sceneController, geometry, {
        primaryRadius: sceneDistance(frame.primary_outer_radius_m),
        secondaryRadius: sceneDistance(frame.secondary_outer_radius_m),
        primaryCenter: [0, 0],
        secondaryCenter: [0, 0],
        shift: sceneDistance(frame.shift_m),
        beltZ: sceneDistance(frame.belt_axial_position_m),
      });
      const previous = fitted.current;
      if (!previous || previous.controller !== sceneController || previous.reset !== resetKey || previous.component !== component) {
        const root = sceneController.getModel(`${component}Fixed`)?.object3D;
        if (root) {
          root.updateWorldMatrix(true, true);
          const bounds = new Box3();
          if (component === 'primary') {
            // Hidden arms have no contact pose; do not fit their construction
            // placeholder. Ramp, pivot and the solved swing define the view.
            for (const id of ['primaryRamps', 'primaryCarrier']) {
              const object = sceneController.getModel(id)?.object3D;
              if (object) bounds.union(new Box3().setFromObject(object));
            }
          } else bounds.setFromObject(root);
          if (component === 'primary' && geometry.mechanisms?.primary) {
            // Fit the solved swing envelope once, not just the initial arm pose.
            const layout = mechanismLayout(geometry);
            const radius = sceneDistance(geometry.mechanisms.primary.roller_radius_m);
            const size = new Vector3(radius * 3, radius * 3, radius * 3);
            for (const pose of geometry.mechanisms.poses) {
              if (!pose.primary_roller_m) continue;
              const point = new Vector3(sceneDistance(pose.primary_roller_m[1]), 0,
                layout.back - sceneDistance(pose.primary_roller_m[0])).applyMatrix4(root.matrixWorld);
              bounds.union(new Box3().setFromCenterAndSize(point, size));
            }
            const ramp = sceneController.getModel('primaryRamps')?.object3D;
            const current = mechanismPose(geometry, sceneDistance(frame.shift_m));
            if (ramp && current) {
              const rampBounds = new Box3().setFromObject(ramp);
              const positions = geometry.mechanisms.poses.map(p => p.primary_ramp_shift_m);
              const worldRotation = root.getWorldQuaternion(new Quaternion());
              for (const end of [Math.min(...positions), Math.max(...positions)])
                bounds.union(rampBounds.clone().translate(new Vector3(0, 0,
                  sceneDistance(current.primary_ramp_shift_m - end)).applyQuaternion(worldRotation)));
            }
          }
          if (!bounds.isEmpty()) {
            if (previous?.controller === sceneController && previous.reset !== resetKey) sceneController.resetView();
            sceneController.fitBounds(bounds.expandByScalar(geometry.beltHeight * 0.25));
            fitted.current = { controller: sceneController, reset: resetKey, component };
          }
        }
      }
      return;
    }
    const { beltMesh, cleanup } = setupBelt(sceneController);
    const beltZ = sceneDistance(frame.belt_axial_position_m);
    const layout = updateBeltMesh(
      beltMesh,
      { position: frame.belt_path_m, regionKeys: frame.belt_regions },
      geometry,
      beltZ,
      undefined,
      null,
      false,
    );
    positionCVT(sceneController, geometry, {
      primaryRadius: sceneDistance(frame.primary_outer_radius_m),
      secondaryRadius: sceneDistance(frame.secondary_outer_radius_m),
      primaryCenter: layout?.primaryCenter ?? [-geometry.centreDistance / 2, 0],
      secondaryCenter: layout?.secondaryCenter ?? [
        geometry.centreDistance / 2,
        0,
      ],
      shift: sceneDistance(frame.shift_m),
      beltZ,
    });
    return cleanup;
  }, [sceneController, frame, geometry, component, models, resetKey]);
  return (
    <div
      ref={containerRef}
      className={`${styles.scene3dViewer} ${component ? styles.componentPreview : ''} ${className ?? ''}`}
    >
      {component && sceneController && frame && <InspectionOverlay controller={sceneController} mount={component} geometry={geometry} shift={sceneDistance(frame.shift_m)}/>}
      {error && (
        <Alert className={styles.sceneError} title="3D preview unavailable">
          {error}
        </Alert>
      )}
    </div>
  );
}
