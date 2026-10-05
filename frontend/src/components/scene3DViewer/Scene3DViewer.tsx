import { ForceOverlay } from './ForceOverlay';
import { useFullscreenElement } from '@mantine/hooks';
import {
  IconArrowsMaximize,
  IconArrowsMinimize,
  IconRestore,
} from '@tabler/icons-react';
import { Playbar } from '@components/playbar/Playbar';
import { reportAxisTimes } from '@utils/reportTable';
import {
  DEFAULT_SCENE,
  useScenePreferences,
  type ScenePreferences,
} from '../../features/playback/preferences';
import { mechanismPose } from './mechanisms';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import * as THREE from 'three';
import type { SimulationCaseDocument, SimulationResult } from '@api/client';
import { interpolatedValue, valueAt } from '@utils/reportTable';
import type {
  ReportReplayController,
  VisualReplaySample,
} from '@utils/reportReplay';
import type { TemporalRotationTarget } from '@utils/Scene3DController';
import {
  findSpatialDomain,
  findSpatialField,
  reportSignalRange,
  sampleSpatialDomain,
  sampleSpatialDomainInterpolated,
  sampleSpatialFieldInterpolated,
} from '@utils/spatialFields';
import { useScene3D } from '@hooks/useScene3D';
import { Alert } from '@mantine/core';
import { ActionButton } from '@components/button/ActionButton';
import { createCVTModels, fitCVT, positionCVT } from './proceduralModels';
import styles from './Scene3DViewer.module.scss';
import {
  setupAxisHelpers,
  setupBelt,
  setupSceneGrid,
  setupVerticalGrid,
  setCVTModelsTransparent,
} from './sceneElements';
import { beltSceneLayout, updateBeltMesh } from './beltGeometry';
import {
  integratedAngularPosition,
  interpolatedArrayValue,
} from './sceneKinematics';
import {
  sceneConfiguration,
  sceneDistance,
  sceneGeometry,
  type ResolvedSceneGeometry,
} from './sceneSpec';

const BELT_DOMAIN_KEY = 'belt.path';
const TENSION_FIELD_KEY = 'belt.tension';
const BELT_SAMPLE_COUNT = 200;
const LOCAL_Z_AXIS = new THREE.Vector3(0, 0, 1);

const TENSION_BOUNDARY_KEYS = [
  'contact.primary_tension_in',
  'contact.primary_tension_out',
  'contact.secondary_tension_in',
  'contact.secondary_tension_out',
] as const;

interface Scene3DViewerProps {
  forceSource?: string;
  replayController: ReportReplayController;
  result: SimulationResult;
  document: SimulationCaseDocument;
  className?: string;
  resolvedGeometry: ResolvedSceneGeometry;
}

type ReplayBracket = Pick<
  VisualReplaySample,
  'lowerIndex' | 'upperIndex' | 'alpha'
>;

const finite = (value: number | null | undefined, fallback: number) =>
  typeof value === 'number' && Number.isFinite(value) ? value : fallback;

function formatScaleValue(value: number): string {
  return new Intl.NumberFormat(undefined, { maximumFractionDigits: 0 }).format(
    value,
  );
}

export const Scene3DViewer = ({
  replayController,
  forceSource,
  result,
  resolvedGeometry,
  className,
}: Scene3DViewerProps) => {
  const table = result.report_table;
  const baseGeometry = useMemo(
    () => sceneGeometry(resolvedGeometry),
    [resolvedGeometry],
  );
  const beltDomain = useMemo(
    () => findSpatialDomain(result, BELT_DOMAIN_KEY),
    [result],
  );
  const tensionField = useMemo(
    () => findSpatialField(result, TENSION_FIELD_KEY),
    [result],
  );
  const tensionRange = useMemo(
    () => reportSignalRange(table, TENSION_BOUNDARY_KEYS),
    [table],
  );
  const tensionAvailable =
    beltDomain !== undefined &&
    tensionField !== undefined &&
    tensionField.domain === beltDomain.key &&
    tensionRange !== null;

  const initialBeltSample = useMemo(() => {
    if (beltDomain === undefined || table.row_count === 0) return null;
    try {
      return sampleSpatialDomain(beltDomain, table, 0, BELT_SAMPLE_COUNT);
    } catch {
      return null;
    }
  }, [beltDomain, table]);

  const initialLayout = useMemo(
    () =>
      initialBeltSample === null ? null : beltSceneLayout(initialBeltSample),
    [initialBeltSample],
  );

  const geometry = useMemo(() => {
    if (initialLayout === null) return baseGeometry;
    const dx =
      initialLayout.secondaryCenter[0] - initialLayout.primaryCenter[0];
    const dy =
      initialLayout.secondaryCenter[1] - initialLayout.primaryCenter[1];
    return {
      ...baseGeometry,
      centreDistance: Math.hypot(dx, dy),
    };
  }, [baseGeometry, initialLayout]);

  const beltTravel = useMemo(
    () => integratedAngularPosition(table, 'state.belt_speed'),
    [table],
  );
  const primaryIntegratedAngle = useMemo(
    () => integratedAngularPosition(table, 'state.primary_angular_speed'),
    [table],
  );
  const secondaryIntegratedAngle = useMemo(
    () => integratedAngularPosition(table, 'state.secondary_angular_speed'),
    [table],
  );

  const primaryAngleAt = useCallback(
    (sample: ReplayBracket): number =>
      finite(
        interpolatedValue(
          table,
          'observer.primary_shaft_angle',
          sample.lowerIndex,
          sample.upperIndex,
          sample.alpha,
        ),
        interpolatedArrayValue(primaryIntegratedAngle, sample),
      ),
    [primaryIntegratedAngle, table],
  );

  const secondaryAngleAt = useCallback(
    (sample: ReplayBracket): number =>
      interpolatedArrayValue(secondaryIntegratedAngle, sample),
    [secondaryIntegratedAngle],
  );

  const helixAngleAt = useCallback(
    (sample: ReplayBracket): number =>
      mechanismPose(
        geometry,
        sceneDistance(
          finite(
            interpolatedValue(
              table,
              'state.shift_position',
              sample.lowerIndex,
              sample.upperIndex,
              sample.alpha,
            ),
            0,
          ),
        ),
      )?.secondary_angle_rad ?? 0,
    [geometry, table],
  );

  const models = useMemo(() => createCVTModels(geometry), [geometry]);
  const [beltMesh, setBeltMesh] = useState<THREE.Mesh | null>(null);
  const [preferences, setPreferences] = useScenePreferences();
  const {
    beltVisible,
    showTension,
    showAngularRotation,
    showMotionBlur,
    gridsVisible,
    orthographicView,
    crossSectionEnabled,
    modelsTransparent,
  } = preferences;
  const togglePreference = (key: Exclude<keyof ScenePreferences, 'forces'>) =>
    setPreferences((current) => ({ ...current, [key]: !current[key] }));
  const {
    ref: fullscreenRef,
    toggle: toggleFullscreen,
    fullscreen,
  } = useFullscreenElement<HTMLDivElement>();
  const [fullscreenError, setFullscreenError] = useState<string | null>(null);
  const times = useMemo(() => reportAxisTimes(table), [table]);
  const [gridObjects, setGridObjects] = useState<THREE.Object3D[]>([]);

  const motionTargetsRef = useRef<TemporalRotationTarget[]>([]);
  const crossSectionStateRef = useRef<{
    enabled: boolean;
    primaryY: number;
    secondaryY: number;
  } | null>(null);
  const pulleyCentersRef = useRef({
    primaryY: initialLayout?.primaryCenter[1] ?? 0,
    secondaryY: initialLayout?.secondaryCenter[1] ?? 0,
  });

  const { containerRef, sceneController, error } = useScene3D({
    sceneConfig: sceneConfiguration(),
    models,
  });
  useEffect(() => {
    if (sceneController) fitCVT(sceneController, geometry);
  }, [sceneController, geometry]);

  useEffect(() => {
    if (!sceneController) return;
    const cleanups = [
      setupSceneGrid(sceneController),
      setupAxisHelpers(sceneController),
      setupVerticalGrid(sceneController),
    ];
    const grids: THREE.Object3D[] = [];
    sceneController.getScene().traverse((object) => {
      if (
        object instanceof THREE.GridHelper ||
        object instanceof THREE.AxesHelper
      ) {
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

  const applyCrossSection = useCallback(
    (primaryY: number, secondaryY: number) => {
      if (!sceneController) return;

      const previous = crossSectionStateRef.current;
      if (
        previous !== null &&
        previous.enabled === crossSectionEnabled &&
        Math.abs(previous.primaryY - primaryY) < 1e-9 &&
        Math.abs(previous.secondaryY - secondaryY) < 1e-9
      ) {
        return;
      }
      crossSectionStateRef.current = {
        enabled: crossSectionEnabled,
        primaryY,
        secondaryY,
      };

      const renderer = sceneController.getRenderer();
      renderer.localClippingEnabled = crossSectionEnabled;

      const apply = (id: string, centerY: number) => {
        const model = sceneController.getModel(id);
        if (!model) return;
        const plane = new THREE.Plane(new THREE.Vector3(0, -1, 0), centerY);
        model.object3D.traverse((object) => {
          if (!(object instanceof THREE.Mesh)) return;
          const materials = Array.isArray(object.material)
            ? object.material
            : [object.material];
          materials.forEach((material) => {
            material.clippingPlanes = crossSectionEnabled ? [plane] : [];
            material.needsUpdate = true;
          });
        });
      };

      apply('primaryFixed', primaryY);
      apply('secondaryFixed', secondaryY);
    },
    [crossSectionEnabled, sceneController],
  );

  const updateScene = useCallback(
    (sample: VisualReplaySample) => {
      if (!sceneController || !beltMesh) return;

      const shiftMeters = finite(
        interpolatedValue(
          table,
          'state.shift_position',
          sample.lowerIndex,
          sample.upperIndex,
          sample.alpha,
        ),
        0,
      );
      const shift = sceneDistance(shiftMeters);
      const primaryAngle = primaryAngleAt(sample);
      const secondaryAngle = secondaryAngleAt(sample);
      const secondaryHelixAngle = helixAngleAt(sample);

      const beltAxialPosition = -Math.max(geometry.deadzoneShift, shift) / 2;

      let primaryCenter: [number, number] = initialLayout?.primaryCenter ?? [
        -geometry.centreDistance / 2,
        0,
      ];
      let secondaryCenter: [number, number] =
        initialLayout?.secondaryCenter ?? [geometry.centreDistance / 2, 0];

      if (beltDomain !== undefined) {
        try {
          const domainSample = sampleSpatialDomainInterpolated(
            beltDomain,
            table,
            sample.lowerIndex,
            sample.upperIndex,
            sample.alpha,
            BELT_SAMPLE_COUNT,
          );
          const tensionSample =
            showTension &&
            tensionField !== undefined &&
            tensionField.domain === beltDomain.key
              ? sampleSpatialFieldInterpolated(
                  tensionField,
                  domainSample,
                  table,
                  sample.lowerIndex,
                  sample.upperIndex,
                  sample.alpha,
                )
              : undefined;
          const layout = updateBeltMesh(
            beltMesh,
            domainSample,
            geometry,
            beltAxialPosition,
            tensionSample?.values,
            tensionRange,
            showTension && tensionAvailable,
            showAngularRotation
              ? sceneDistance(interpolatedArrayValue(beltTravel, sample))
              : 0,
          );
          if (layout !== null) {
            primaryCenter = layout.primaryCenter;
            secondaryCenter = layout.secondaryCenter;
          }
          beltMesh.visible = beltVisible;
        } catch (error) {
          beltMesh.visible = false;
          console.warn(
            'Unable to sample CINDER belt.path for smooth 3D playback.',
            error,
          );
        }
      } else {
        beltMesh.visible = false;
      }

      pulleyCentersRef.current = {
        primaryY: primaryCenter[1],
        secondaryY: secondaryCenter[1],
      };

      const radiusAt = (key: string, fallback: number) =>
        sceneDistance(
          finite(
            interpolatedValue(
              table,
              key,
              sample.lowerIndex,
              sample.upperIndex,
              sample.alpha,
            ),
            fallback / sceneDistance(1),
          ),
        );
      positionCVT(sceneController, geometry, {
        primaryCenter,
        secondaryCenter,
        shift,
        beltZ: beltAxialPosition,
        primaryRadius:
          radiusAt(
            'geometry.primary_effective_radius',
            geometry.primaryMinRadius - geometry.cordDepth,
          ) + geometry.cordDepth,
        secondaryRadius:
          radiusAt(
            'geometry.secondary_effective_radius',
            geometry.secondaryMaxRadius - geometry.cordDepth,
          ) + geometry.cordDepth,
        primaryAngle: showAngularRotation ? primaryAngle : 0,
        secondaryAngle: showAngularRotation ? secondaryAngle : 0,
        helixAngle: secondaryHelixAngle,
      });

      applyCrossSection(primaryCenter[1], secondaryCenter[1]);

      const primaryFixed = sceneController.getModel('primaryFixed')?.object3D;
      const secondaryFixed =
        sceneController.getModel('secondaryFixed')?.object3D;
      const secondaryMoving =
        sceneController.getModel('secondaryMoving')?.object3D;
      const blurActive = sample.playing && showMotionBlur;

      const primaryAngularSpeed = finite(
        interpolatedValue(
          table,
          'state.primary_angular_speed',
          sample.lowerIndex,
          sample.upperIndex,
          sample.alpha,
        ),
        0,
      );
      const secondaryAngularSpeed = finite(
        interpolatedValue(
          table,
          'state.secondary_angular_speed',
          sample.lowerIndex,
          sample.upperIndex,
          sample.alpha,
        ),
        0,
      );

      const lowerTime = finite(
        valueAt(table, table.axis_key, sample.lowerIndex),
        sample.simulationTime,
      );
      const upperTime = finite(
        valueAt(table, table.axis_key, sample.upperIndex),
        lowerTime,
      );
      const helixRate =
        upperTime > lowerTime
          ? (helixAngleAt({
              lowerIndex: sample.upperIndex,
              upperIndex: sample.upperIndex,
              alpha: 0,
            }) -
              helixAngleAt({
                lowerIndex: sample.lowerIndex,
                upperIndex: sample.lowerIndex,
                alpha: 0,
              })) /
            (upperTime - lowerTime)
          : 0;

      const sampleAtShutterOffset = (wallOffsetSeconds: number) =>
        replayController.sampleAtSimulationTime(
          sample.simulationTime + wallOffsetSeconds,
        );

      const targets: TemporalRotationTarget[] = [];

      if (primaryFixed && showAngularRotation && blurActive) {
        targets.push({
          object: primaryFixed,
          axisLocal: LOCAL_Z_AXIS,
          angularSpeedRadPerSecond: primaryAngularSpeed,
          angleOffsetAt: (wallOffset) =>
            primaryAngleAt(sampleAtShutterOffset(wallOffset)) - primaryAngle,
        });
      }

      if (secondaryFixed && showAngularRotation && blurActive) {
        targets.push({
          object: secondaryFixed,
          axisLocal: LOCAL_Z_AXIS,
          angularSpeedRadPerSecond: secondaryAngularSpeed,
          angleOffsetAt: (wallOffset) =>
            secondaryAngleAt(sampleAtShutterOffset(wallOffset)) -
            secondaryAngle,
        });
      }

      if (secondaryMoving && blurActive && Math.abs(helixRate) > 0) {
        targets.push({
          object: secondaryMoving,
          axisLocal: LOCAL_Z_AXIS,
          angularSpeedRadPerSecond: helixRate,
          angleOffsetAt: (wallOffset) =>
            helixAngleAt(sampleAtShutterOffset(wallOffset)) -
            secondaryHelixAngle,
        });
      }

      motionTargetsRef.current = targets;
    },
    [
      applyCrossSection,
      beltDomain,
      beltTravel,
      beltMesh,
      beltVisible,
      geometry,
      helixAngleAt,
      initialLayout,
      primaryAngleAt,
      replayController,
      sceneController,
      secondaryAngleAt,
      showAngularRotation,
      showMotionBlur,
      showTension,
      table,
      tensionAvailable,
      tensionField,
      tensionRange,
    ],
  );

  useEffect(() => {
    if (!sceneController || !beltMesh) return;

    let previousTime: number | null = null;
    let previousPlaying: boolean | null = null;
    sceneController.setFrameUpdate((now) => {
      const sample = replayController.visualSample(now);
      if (
        sample.simulationTime === previousTime &&
        sample.playing === previousPlaying
      )
        return;
      previousTime = sample.simulationTime;
      previousPlaying = sample.playing;
      updateScene(sample);
    });
    sceneController.setTemporalRotationProvider(
      showMotionBlur ? () => motionTargetsRef.current : null,
    );

    return () => {
      sceneController.setFrameUpdate(null);
      sceneController.setTemporalRotationProvider(null);
      motionTargetsRef.current = [];
    };
  }, [
    beltMesh,
    replayController,
    sceneController,
    showMotionBlur,
    updateScene,
  ]);

  useEffect(() => {
    if (beltMesh) beltMesh.visible = beltVisible && beltDomain !== undefined;
  }, [beltDomain, beltMesh, beltVisible]);

  useEffect(() => {
    gridObjects.forEach((grid) => {
      grid.visible = gridsVisible;
    });
  }, [gridObjects, gridsVisible]);

  useEffect(() => {
    crossSectionStateRef.current = null;
    applyCrossSection(
      pulleyCentersRef.current.primaryY,
      pulleyCentersRef.current.secondaryY,
    );
  }, [applyCrossSection, models]);

  useEffect(() => {
    if (!sceneController) return;
    setCVTModelsTransparent(sceneController, modelsTransparent);
  }, [modelsTransparent, models, sceneController, beltMesh]);

  useEffect(() => {
    if (!sceneController) return;
    sceneController.setCameraProjection(
      orthographicView ? 'orthographic' : 'perspective',
    );
  }, [orthographicView, sceneController]);
  const tensionUnit = tensionField?.canonical_unit ?? 'N';

  return (
    <div
      ref={fullscreenRef}
      className={`${styles.scene3dViewer} ${fullscreen ? styles.fullscreen : ''} ${className ?? ''}`}
      aria-label="CVT scene"
    >
      <div className={styles.viewport}>
        <div ref={containerRef} className={styles.canvasContainer} />
        {showTension && tensionAvailable && tensionRange !== null && (
          <div className={styles.tensionLegend}>
            <div className={styles.legendTitle}>Belt tension</div>
            <div className={styles.legendBar} />
            <div className={styles.legendValues}>
              <span>
                {formatScaleValue(tensionRange.minimum)} {tensionUnit}
              </span>
              <span>
                {formatScaleValue(tensionRange.maximum)} {tensionUnit}
              </span>
            </div>
            <div className={styles.legendNote}>Fixed scale for entire run</div>
          </div>
        )}
      </div>
      {error && (
        <Alert className={styles.sceneError} title="3D preview unavailable">
          {error}
        </Alert>
      )}
      <div
        className={styles.controls}
        role="group"
        aria-label="3D view options"
      >
        {forceSource && (
          <ForceOverlay
            key={forceSource}
            source={forceSource}
            scene={sceneController}
            geometry={geometry}
            replay={replayController}
            table={table}
            settings={preferences.forces}
            onChange={(forces) =>
              setPreferences((current) => ({ ...current, forces }))
            }
            fullscreen={fullscreen}
          />
        )}
        {[
          {
            label: 'Belt',
            active: beltVisible,
            toggle: () => togglePreference('beltVisible'),
          },
          {
            label: 'Tension',
            active: showTension,
            toggle: () => togglePreference('showTension'),
            reason: tensionAvailable
              ? undefined
              : 'Belt tension is unavailable for this result.',
          },
          {
            label: 'Transparent',
            active: modelsTransparent,
            toggle: () => togglePreference('modelsTransparent'),
          },
          {
            label: 'Rotation',
            active: showAngularRotation,
            toggle: () => togglePreference('showAngularRotation'),
          },
          {
            label: 'Blur',
            active: showMotionBlur,
            toggle: () => togglePreference('showMotionBlur'),
          },
          {
            label: 'Orthographic',
            active: orthographicView,
            toggle: () => togglePreference('orthographicView'),
          },
          {
            label: 'Grids',
            active: gridsVisible,
            toggle: () => togglePreference('gridsVisible'),
          },
          {
            label: 'Section',
            active: crossSectionEnabled,
            toggle: () => togglePreference('crossSectionEnabled'),
          },
        ].map((option) => (
          <ActionButton
            key={option.label}
            size="compact-xs"
            variant={option.active ? 'light' : 'default'}
            aria-pressed={option.active}
            disabledReason={
              error
                ? '3D rendering is unavailable in this browser.'
                : option.reason
            }
            onClick={option.toggle}
          >
            {option.label}
          </ActionButton>
        ))}
        <ActionButton
          size="compact-xs"
          variant="default"
          leftSection={<IconRestore size={13} />}
          onClick={() => {
            setPreferences(DEFAULT_SCENE);
            sceneController?.resetView();
          }}
        >
          Reset scene
        </ActionButton>
        <ActionButton
          size="compact-xs"
          variant="default"
          leftSection={
            fullscreen ? (
              <IconArrowsMinimize size={13} />
            ) : (
              <IconArrowsMaximize size={13} />
            )
          }
          disabledReason={
            !window.document.fullscreenEnabled
              ? 'Fullscreen is unavailable in this browser.'
              : undefined
          }
          aria-pressed={fullscreen}
          onClick={() => {
            setFullscreenError(null);
            void toggleFullscreen().catch(() =>
              setFullscreenError('Couldn’t open fullscreen. Try again.'),
            );
          }}
        >
          {fullscreen ? 'Exit fullscreen' : 'Fullscreen'}
        </ActionButton>
      </div>
      {fullscreenError && (
        <Alert
          className={styles.sceneError}
          color="red"
          withCloseButton
          onClose={() => setFullscreenError(null)}
        >
          {fullscreenError}
        </Alert>
      )}
      {fullscreen && (
        <div className={styles.fullscreenPlayback}>
          <Playbar replayController={replayController} times={times} />
        </div>
      )}
    </div>
  );
};
