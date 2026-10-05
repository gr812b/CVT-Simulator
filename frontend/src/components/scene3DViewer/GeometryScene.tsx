import { useEffect, useMemo } from 'react';
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
}: {
  preview: ScenePreview;
  frameIndex?: number;
  className?: string;
}) {
  const geometry = useMemo(
    () => sceneGeometry(preview.geometry),
    [preview.geometry],
  );
  const models = useMemo(() => createCVTModels(geometry), [geometry]);
  const { containerRef, sceneController, error } = useScene3D({
    sceneConfig: sceneConfiguration(true),
    models,
  });
  const frame = preview.frames[frameIndex] ?? preview.frames[0];
  useEffect(() => {
    if (sceneController) fitCVT(sceneController, geometry);
  }, [sceneController, geometry]);
  useEffect(() => {
    if (!sceneController || !frame) return;
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
  }, [sceneController, frame, geometry]);
  return (
    <div
      ref={containerRef}
      className={`${styles.scene3dViewer} ${className ?? ''}`}
    >
      {error && (
        <Alert className={styles.sceneError} title="3D preview unavailable">
          {error}
        </Alert>
      )}
    </div>
  );
}
