import { useEffect, useMemo } from 'react';
import { Box3 } from 'three';
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
}: {
  preview: ScenePreview;
  frameIndex?: number;
  className?: string;
  component?: 'primary' | 'secondary';
}) {
  const geometry = useMemo(
    () => sceneGeometry(preview.geometry),
    [preview.geometry],
  );
  const models = useMemo(() => {
    const all = createCVTModels(geometry);
    if (!component) return all;
    const keep = new Set<string>();
    const selected = all.filter((model) => {
      const belongs =
        model.id === `${component}Fixed` ||
        (model.parentId !== undefined && keep.has(model.parentId));
      if (belongs) keep.add(model.id);
      else
        model.object3D?.traverse((object) => {
          const mesh = object as import('three').Mesh;
          mesh.geometry?.dispose();
          if (mesh.material)
            (Array.isArray(mesh.material)
              ? mesh.material
              : [mesh.material]
            ).forEach((material) => material.dispose());
        });
      return belongs;
    });
    return selected;
  }, [geometry, component]);
  const config = sceneConfiguration(true);
  if (component === 'secondary' && config.camera)
    config.camera.position = [3, 9, -16];
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
      const bounds = new Box3();
      models
        .filter((model) => !model.parentId)
        .forEach((model) => {
          model.object3D?.updateWorldMatrix(true, true);
          if (model.object3D)
            bounds.union(new Box3().setFromObject(model.object3D));
        });
      if (!bounds.isEmpty())
        sceneController.fitBounds(
          bounds.expandByScalar(geometry.beltHeight * 0.25),
        );
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
  }, [sceneController, frame, geometry, component, models]);
  return (
    <div
      ref={containerRef}
      className={`${styles.scene3dViewer} ${component ? styles.componentPreview : ''} ${className ?? ''}`}
    >
      {error && (
        <Alert className={styles.sceneError} title="3D preview unavailable">
          {error}
        </Alert>
      )}
    </div>
  );
}
