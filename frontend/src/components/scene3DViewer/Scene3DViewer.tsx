import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import * as THREE from 'three';
import type { SimulationCaseDocument, SimulationResult } from '@api/client';
import { valueAt } from '@utils/reportTable';
import type { ReportReplayController } from '@utils/reportReplay';
import {
  findSpatialDomain,
  findSpatialField,
  reportSignalRange,
  sampleSpatialDomain,
  sampleSpatialField,
} from '@utils/spatialFields';
import { useScene3D } from '@hooks/useScene3D';
import type { Model3DConfig } from '@utils/sceneTypes';
import styles from './Scene3DViewer.module.scss';
import { primaryOffset, secondaryOffset } from './modelConfigs';
import {
  loadCVTModels,
  setupAxisHelpers,
  setupBelt,
  setupSceneGrid,
  setupSceneLighting,
  setupVerticalGrid,
  setCVTModelsTransparent,
} from './sceneElements';
import { beltSceneLayout, updateBeltMesh } from './beltGeometry';
import {
  integratedAngularPosition,
  secondaryHelixRelativeAngle,
} from './sceneKinematics';
import { sceneDistance, sceneGeometry } from './sceneSpec';

const BELT_DOMAIN_KEY = 'belt.path';
const TENSION_FIELD_KEY = 'belt.tension';
const BELT_SAMPLE_COUNT = 200;
const TENSION_BOUNDARY_KEYS = [
  'contact.primary_tension_in',
  'contact.primary_tension_out',
  'contact.secondary_tension_in',
  'contact.secondary_tension_out',
] as const;

interface Scene3DViewerProps {
  replayController: ReportReplayController;
  result: SimulationResult;
  document: SimulationCaseDocument;
  className?: string;
}

const finite = (value: number | null | undefined, fallback: number) => (
  typeof value === 'number' && Number.isFinite(value) ? value : fallback
);

function formatScaleValue(value: number): string {
  return new Intl.NumberFormat(undefined, { maximumFractionDigits: 0 }).format(value);
}

/**
 * CAD presentation driven by CINDER's report table and portable spatial fields.
 * Belt mechanics are no longer reconstructed in the frontend: belt.path owns
 * the centerline and belt.tension owns the scalar field painted on that path.
 */
export const Scene3DViewer = ({
  replayController,
  result,
  document,
  className,
}: Scene3DViewerProps) => {
  const table = result.report_table;
  const baseGeometry = useMemo(() => sceneGeometry(document), [document]);
  const beltDomain = useMemo(() => findSpatialDomain(result, BELT_DOMAIN_KEY), [result]);
  const tensionField = useMemo(() => findSpatialField(result, TENSION_FIELD_KEY), [result]);
  const tensionRange = useMemo(
    () => reportSignalRange(table, TENSION_BOUNDARY_KEYS),
    [table],
  );
  const tensionAvailable = beltDomain !== undefined
    && tensionField !== undefined
    && tensionField.domain === beltDomain.key
    && tensionRange !== null;

  // Resolve the physical C2C from CINDER's belt.path before the CAD models are
  // loaded. This prevents the old presentation-only spacing from flashing and
  // then snapping into the path-derived positions on the first playback update.
  const initialBeltSample = useMemo(() => {
    if (beltDomain === undefined || table.row_count === 0) return null;
    try {
      return sampleSpatialDomain(beltDomain, table, 0, BELT_SAMPLE_COUNT);
    } catch {
      return null;
    }
  }, [beltDomain, table]);

  const initialLayout = useMemo(
    () => (initialBeltSample === null ? null : beltSceneLayout(initialBeltSample)),
    [initialBeltSample],
  );

  const geometry = useMemo(() => {
    if (initialLayout === null) return baseGeometry;
    const dx = initialLayout.secondaryCenter[0] - initialLayout.primaryCenter[0];
    const dy = initialLayout.secondaryCenter[1] - initialLayout.primaryCenter[1];
    return {
      ...baseGeometry,
      centreDistance: Math.hypot(dx, dy),
    };
  }, [baseGeometry, initialLayout]);

  const primaryIntegratedAngle = useMemo(
    () => integratedAngularPosition(table, 'state.primary_angular_speed'),
    [table],
  );
  const secondaryIntegratedAngle = useMemo(
    () => integratedAngularPosition(table, 'state.secondary_angular_speed'),
    [table],
  );

  const [models, setModels] = useState<Model3DConfig[]>([]);
  const [isLoading, setLoading] = useState(true);
  const [beltMesh, setBeltMesh] = useState<THREE.Mesh | null>(null);
  const [beltVisible, setBeltVisible] = useState(true);
  const [showTension, setShowTension] = useState(false);
  const [showAngularRotation, setShowAngularRotation] = useState(true);
  const [gridsVisible, setGridsVisible] = useState(false);
  const [crossSectionEnabled, setCrossSectionEnabled] = useState(false);
  const [modelsTransparent, setModelsTransparent] = useState(false);
  const [gridObjects, setGridObjects] = useState<THREE.Object3D[]>([]);

  const currentFrameRef = useRef(0);
  const pulleyCentersRef = useRef({
    primaryY: initialLayout?.primaryCenter[1] ?? 0,
    secondaryY: initialLayout?.secondaryCenter[1] ?? 0,
  });

  const shiftKey = 'state.shift_position';

  useEffect(() => {
    setLoading(true);
    void loadCVTModels(geometry).then(setModels).finally(() => setLoading(false));
  }, [geometry]);

  const { containerRef, sceneController } = useScene3D({
    sceneConfig: {
      camera: { type: 'perspective', fov: 50, position: [7, 7, 12], lookAt: [0, 0, 0] },
      enableControls: true,
      backgroundColor: 0x2a2a2a,
      antialias: true,
    },
    models,
  });

  useEffect(
    () => (sceneController ? setupSceneLighting(sceneController) : undefined),
    [sceneController],
  );

  useEffect(() => {
    if (!sceneController) return;
    const cleanups = [
      setupSceneGrid(sceneController),
      setupAxisHelpers(sceneController),
      setupVerticalGrid(sceneController),
    ];
    const grids: THREE.Object3D[] = [];
    sceneController.getScene().traverse((object) => {
      if (object instanceof THREE.GridHelper || object instanceof THREE.AxesHelper) {
        object.visible = gridsVisible;
        grids.push(object);
      }
    });
    setGridObjects(grids);
    return () => cleanups.forEach((cleanup) => cleanup());
  }, [sceneController, gridsVisible]);

  useEffect(() => {
    if (!sceneController) return;
    const setup = setupBelt(sceneController);
    setBeltMesh(setup.beltMesh);
    return setup.cleanup;
  }, [sceneController]);

  const applyCrossSection = useCallback((primaryY: number, secondaryY: number) => {
    if (!sceneController) return;
    const renderer = sceneController.getRenderer();
    renderer.localClippingEnabled = crossSectionEnabled;

    const apply = (id: string, centerY: number) => {
      const model = sceneController.getModel(id);
      if (!model) return;
      // Three.js clips the negative half-space. With a downward normal, points
      // above the pulley centre have negative plane distance and disappear.
      const plane = new THREE.Plane(new THREE.Vector3(0, -1, 0), centerY);
      model.object3D.traverse((object) => {
        if (!(object instanceof THREE.Mesh)) return;
        const materials = Array.isArray(object.material) ? object.material : [object.material];
        materials.forEach((material) => {
          material.clippingPlanes = crossSectionEnabled ? [plane] : [];
          material.needsUpdate = true;
        });
      });
    };

    apply('primaryFixed', primaryY);
    apply('secondaryFixed', secondaryY);
  }, [crossSectionEnabled, sceneController]);

  const updateScene = useCallback((index: number) => {
    if (!sceneController || !beltMesh) return;

    const shiftMeters = finite(valueAt(table, shiftKey, index), 0);
    const shift = sceneDistance(shiftMeters);
    const primaryAngle = finite(
      valueAt(table, 'observer.primary_shaft_angle', index),
      primaryIntegratedAngle[index] ?? 0,
    );
    const secondaryAngle = secondaryIntegratedAngle[index] ?? 0;
    const secondaryHelixAngle = secondaryHelixRelativeAngle(
      document,
      table,
      index,
    );

    const secondaryShift = Math.max(0, shift - geometry.deadzoneShift);
    const beltAxialPosition = -Math.max(geometry.deadzoneShift, shift) / 2;

    let primaryCenter: [number, number] = initialLayout?.primaryCenter
      ?? [-geometry.centreDistance / 2, 0];
    let secondaryCenter: [number, number] = initialLayout?.secondaryCenter
      ?? [geometry.centreDistance / 2, 0];

    if (beltDomain !== undefined) {
      try {
        const domainSample = sampleSpatialDomain(
          beltDomain,
          table,
          index,
          BELT_SAMPLE_COUNT,
        );
        const tensionSample = tensionField !== undefined && tensionField.domain === beltDomain.key
          ? sampleSpatialField(tensionField, domainSample, table, index)
          : undefined;
        const layout = updateBeltMesh(
          beltMesh,
          domainSample,
          geometry,
          beltAxialPosition,
          tensionSample?.values,
          tensionRange,
          showTension && tensionAvailable,
        );
        if (layout !== null) {
          primaryCenter = layout.primaryCenter;
          secondaryCenter = layout.secondaryCenter;
        }
        beltMesh.visible = beltVisible;
      } catch (error) {
        beltMesh.visible = false;
        if (index === 0) {
          console.warn('Unable to sample CINDER belt.path for 3D playback.', error);
        }
      }
    } else {
      beltMesh.visible = false;
    }

    pulleyCentersRef.current = {
      primaryY: primaryCenter[1],
      secondaryY: secondaryCenter[1],
    };

    sceneController.updateModels({
      primaryFixed: {
        position: [primaryCenter[0], primaryCenter[1], -primaryOffset - geometry.maxShift / 2],
        rotation: [0, Math.PI, showAngularRotation ? -primaryAngle : 0],
      },
      primaryMoving: {
        position: [0, 0, -(primaryOffset + geometry.maxShift - shift)],
      },
      secondaryFixed: {
        position: [
          secondaryCenter[0],
          secondaryCenter[1],
          secondaryOffset - geometry.deadzoneShift / 2,
        ],
        // Shaft spin belongs to the complete secondary assembly and is the only
        // part controlled by the Rotation toggle.
        rotation: [0, 0, showAngularRotation ? secondaryAngle : 0],
      },
      secondaryMoving: {
        position: [0, 0, -(secondaryOffset + secondaryShift)],
        // Helix clocking is relative mechanism motion. Because this model is a
        // child of secondaryFixed, it inherits any shaft spin automatically and
        // keeps this relative twist even when shaft Rotation is hidden.
        rotation: [0, 0, secondaryHelixAngle],
      },
    });

    applyCrossSection(primaryCenter[1], secondaryCenter[1]);
  }, [
    applyCrossSection,
    beltDomain,
    beltMesh,
    beltVisible,
    document,
    geometry,
    initialLayout,
    primaryIntegratedAngle,
    sceneController,
    secondaryIntegratedAngle,
    showAngularRotation,
    showTension,
    table,
    tensionAvailable,
    tensionField,
    tensionRange,
  ]);

  useEffect(() => {
    // Redraw whichever frame is currently displayed. Visual toggles such as
    // Tension/Rotation can recreate updateScene; they must not jump playback
    // back to frame zero.
    updateScene(currentFrameRef.current);
    return replayController.on((event) => {
      if (event.type === 'Progress') {
        currentFrameRef.current = event.currentIndex;
        updateScene(event.currentIndex);
      }
    });
  }, [replayController, updateScene]);

  useEffect(() => {
    if (beltMesh) beltMesh.visible = beltVisible && beltDomain !== undefined;
  }, [beltDomain, beltMesh, beltVisible]);

  useEffect(() => {
    gridObjects.forEach((grid) => {
      grid.visible = gridsVisible;
    });
  }, [gridObjects, gridsVisible]);

  useEffect(() => {
    applyCrossSection(
      pulleyCentersRef.current.primaryY,
      pulleyCentersRef.current.secondaryY,
    );
  }, [applyCrossSection]);

  useEffect(() => {
    if (!sceneController) return;
    setCVTModelsTransparent(sceneController, modelsTransparent);
  }, [modelsTransparent, models, sceneController]);

  const tensionUnit = tensionField?.canonical_unit ?? 'N';

  return (
    <div ref={containerRef} className={`${styles.scene3dViewer} ${className ?? ''}`}>
      {isLoading && (
        <div className={styles.loadingOverlay}>
          <div className={styles.spinner} />
          <p>Loading 3D models...</p>
        </div>
      )}

      <div className={styles.controls}>
        <button
          type="button"
          className={styles.controlButton}
          onClick={() => setBeltVisible((current) => !current)}
          title={beltVisible ? 'Hide Belt' : 'Show Belt'}
        >
          {beltVisible ? '●' : '○'} Belt
        </button>
        <button
          type="button"
          className={styles.controlButton}
          onClick={() => setShowTension((current) => !current)}
          disabled={!tensionAvailable}
          title={tensionAvailable ? 'Toggle belt tension colouring' : 'Belt tension field unavailable'}
        >
          {showTension && tensionAvailable ? '●' : '○'} Tension
        </button>
        <button
          type="button"
          className={styles.controlButton}
          onClick={() => setModelsTransparent((current) => !current)}
          title={modelsTransparent ? 'Restore solid pulley models' : 'Ghost pulley models'}
        >
          {modelsTransparent ? '●' : '○'} Transparent
        </button>
        <button
          type="button"
          className={styles.controlButton}
          onClick={() => setShowAngularRotation((current) => !current)}
          title={showAngularRotation ? 'Hide Angular Rotation' : 'Show Angular Rotation'}
        >
          {showAngularRotation ? '●' : '○'} Rotation
        </button>
        <button
          type="button"
          className={styles.controlButton}
          onClick={() => setGridsVisible((current) => !current)}
          title={gridsVisible ? 'Hide Grids' : 'Show Grids'}
        >
          {gridsVisible ? '●' : '○'} Grids
        </button>
        <button
          type="button"
          className={styles.controlButton}
          onClick={() => setCrossSectionEnabled((current) => !current)}
          title={crossSectionEnabled ? 'Disable Cross-Section View' : 'Enable Cross-Section View'}
        >
          {crossSectionEnabled ? '●' : '○'} Section
        </button>
      </div>

      {showTension && tensionAvailable && tensionRange !== null && (
        <div className={styles.tensionLegend}>
          <div className={styles.legendTitle}>Belt tension</div>
          <div className={styles.legendBar} />
          <div className={styles.legendValues}>
            <span>{formatScaleValue(tensionRange.minimum)} {tensionUnit}</span>
            <span>{formatScaleValue(tensionRange.maximum)} {tensionUnit}</span>
          </div>
          <div className={styles.legendNote}>Fixed scale for entire run</div>
        </div>
      )}
    </div>
  );
};
