import { useCallback, useEffect, useMemo, useState } from 'react';
import * as THREE from 'three';
import type { SimulationCaseDocument, ReportTable } from '@api/client';
import { valueAt } from '@utils/reportTable';
import type { ReportReplayController } from '@utils/reportReplay';
import { useScene3D } from '@hooks/useScene3D';
import type { Model3DConfig } from '@utils/sceneTypes';
import styles from './Scene3DViewer.module.scss';
import { primaryOffset, secondaryOffset } from './modelConfigs';
import { loadCVTModels, setupAxisHelpers, setupBelt, setupSceneGrid, setupSceneLighting, setupVerticalGrid } from './sceneElements';
import { updateBeltMesh, type BeltPathData } from './beltGeometry';
import { sceneDistance, sceneGeometry } from './sceneSpec';

interface Scene3DViewerProps { replayController: ReportReplayController; table: ReportTable; document: SimulationCaseDocument; className?: string; }
const finite = (value: number | null | undefined, fallback: number) => typeof value === 'number' && Number.isFinite(value) ? value : fallback;

/** Original CAD scene, now driven only by submitted document dimensions and flattened report columns. */
export const Scene3DViewer = ({ replayController, table, document, className }: Scene3DViewerProps) => {
  const geometry = useMemo(() => sceneGeometry(document), [document]);
  const [models, setModels] = useState<Model3DConfig[]>([]); const [isLoading, setLoading] = useState(true); const [beltMesh, setBeltMesh] = useState<THREE.Mesh | null>(null);
  const [beltVisible, setBeltVisible] = useState(true); const [showAngularRotation, setShowAngularRotation] = useState(true); const [gridsVisible, setGridsVisible] = useState(false); const [crossSectionEnabled, setCrossSectionEnabled] = useState(false); const [gridObjects, setGridObjects] = useState<THREE.Object3D[]>([]);
  const primaryRadiusKey = 'geometry.primary_effective_radius';
  const secondaryRadiusKey = 'geometry.secondary_effective_radius';
  const shiftKey = 'state.shift_position';
  const primaryAngleKey = 'state.primary_shaft_angle';
  const primarySpeedKey = 'state.primary_angular_speed';
  const secondaryAngleKey = 'state.secondary_shaft_angle';
  const primaryWrapKey = 'geometry.primary_wrap_angle_rad';
  const secondaryWrapKey = 'geometry.secondary_wrap_angle_rad';
  const timeKey = table.axisKey;

  useEffect(() => { setLoading(true); void loadCVTModels(geometry).then(setModels).finally(() => setLoading(false)); }, [geometry]);
  const { containerRef, sceneController } = useScene3D({ sceneConfig: { camera: { type: 'perspective', fov: 50, position: [7, 7, 12], lookAt: [0, 0, 0] }, enableControls: true, backgroundColor: 0x2a2a2a, antialias: true }, models });
  useEffect(() => sceneController ? setupSceneLighting(sceneController) : undefined, [sceneController]);
  useEffect(() => { if (!sceneController) return; const cleanups = [setupSceneGrid(sceneController), setupAxisHelpers(sceneController), setupVerticalGrid(sceneController)]; const grids: THREE.Object3D[] = []; sceneController.getScene().traverse((object) => { if (object instanceof THREE.GridHelper || object instanceof THREE.AxesHelper) { object.visible = gridsVisible; grids.push(object); } }); setGridObjects(grids); return () => cleanups.forEach((cleanup) => cleanup()); }, [sceneController, gridsVisible]);
  useEffect(() => { if (!sceneController) return; const setup = setupBelt(sceneController, geometry); setup.beltMesh.visible = beltVisible; setBeltMesh(setup.beltMesh); return setup.cleanup; }, [beltVisible, geometry, sceneController]);

  const updateScene = useCallback((index: number) => {
    if (!sceneController || !beltMesh) return;
    const primaryRadius = sceneDistance(finite(primaryRadiusKey ? valueAt(table, primaryRadiusKey, index) : null, 0.041));
    const secondaryRadius = sceneDistance(finite(secondaryRadiusKey ? valueAt(table, secondaryRadiusKey, index) : null, 0.101));
    const shift = sceneDistance(finite(shiftKey ? valueAt(table, shiftKey, index) : null, 0));
    const time = finite(valueAt(table, timeKey, index), 0);
    const primaryAngle = finite(primaryAngleKey ? valueAt(table, primaryAngleKey, index) : null, finite(primarySpeedKey ? valueAt(table, primarySpeedKey, index) : null, 0) * time);
    const secondaryAngle = finite(secondaryAngleKey ? valueAt(table, secondaryAngleKey, index) : null, 0);
    const primaryWrap = finite(primaryWrapKey ? valueAt(table, primaryWrapKey, index) : null, Math.PI);
    const secondaryWrap = finite(secondaryWrapKey ? valueAt(table, secondaryWrapKey, index) : null, Math.PI);
    const secondaryShift = Math.max(0, shift - geometry.deadzoneShift);
    sceneController.updateModels({ primaryFixed: { rotation: [0, Math.PI, showAngularRotation ? -primaryAngle : 0] }, primaryMoving: { position: [0, 0, -(primaryOffset + geometry.maxShift - shift)] }, secondaryFixed: { rotation: [0, 0, showAngularRotation ? secondaryAngle : 0] }, secondaryMoving: { position: [0, 0, -(secondaryOffset + secondaryShift)], rotation: [0, 0, -secondaryAngle] } });
    const data: BeltPathData = { primaryRadius, primaryPosition: [-geometry.centreDistance / 2, 0, -Math.max(geometry.deadzoneShift, shift) / 2], secondaryRadius, secondaryPosition: [geometry.centreDistance / 2, 0, -Math.max(geometry.deadzoneShift, shift) / 2], primaryWrapAngle: primaryWrap, secondaryWrapAngle: secondaryWrap };
    updateBeltMesh(beltMesh, data, geometry);
  }, [beltMesh, geometry, primaryAngleKey, primaryRadiusKey, primarySpeedKey, primaryWrapKey, secondaryAngleKey, secondaryRadiusKey, secondaryWrapKey, sceneController, shiftKey, showAngularRotation, table, timeKey]);
  useEffect(() => { updateScene(0); return replayController.on((event) => { if (event.type === 'Progress') updateScene(event.currentIndex); }); }, [replayController, updateScene]);
  useEffect(() => { if (beltMesh) beltMesh.visible = beltVisible; }, [beltMesh, beltVisible]);
  useEffect(() => { gridObjects.forEach((grid) => { grid.visible = gridsVisible; }); }, [gridObjects, gridsVisible]);
  useEffect(() => { if (!sceneController) return; const renderer = sceneController.getRenderer(); renderer.localClippingEnabled = crossSectionEnabled; const apply = (id: string, x: number) => { const model = sceneController.getModel(id); if (!model) return; const plane = new THREE.Plane(new THREE.Vector3(1, 0, 0), -x); model.object3D.traverse((object) => { if (!(object instanceof THREE.Mesh)) return; const materials = Array.isArray(object.material) ? object.material : [object.material]; materials.forEach((material) => { material.clippingPlanes = crossSectionEnabled ? [plane] : []; }); }); }; apply('primaryFixed', -geometry.centreDistance / 2); apply('secondaryFixed', geometry.centreDistance / 2); }, [crossSectionEnabled, geometry.centreDistance, sceneController]);

  return <div ref={containerRef} className={`${styles.scene3dViewer} ${className ?? ''}`}>{isLoading && <div className={styles.loadingOverlay}><div className={styles.spinner} /><p>Loading 3D models...</p></div>}<button className={styles.toggleBeltButton} onClick={() => setBeltVisible((current) => !current)} title={beltVisible ? 'Hide Belt' : 'Show Belt'}>{beltVisible ? '🔴' : '⚪'} Belt</button><button className={styles.toggleRotationButton} onClick={() => setShowAngularRotation((current) => !current)} title={showAngularRotation ? 'Hide Angular Rotation' : 'Show Angular Rotation'}>{showAngularRotation ? '🔵' : '⚪'} Rotation</button><button className={styles.toggleGridsButton} onClick={() => setGridsVisible((current) => !current)} title={gridsVisible ? 'Hide Grids' : 'Show Grids'}>{gridsVisible ? '🟢' : '⚪'} Grids</button><button className={styles.toggleSectionButton} onClick={() => setCrossSectionEnabled((current) => !current)} title={crossSectionEnabled ? 'Disable Cross-Section View' : 'Enable Cross-Section View'}>{crossSectionEnabled ? '🟡' : '⚪'} Section</button></div>;
};
