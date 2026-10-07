import { useCallback, useEffect, useMemo, useRef, useState, type RefObject } from 'react';
import { Alert, Box, Group, Loader, Slider, Stack, Switch, Text } from '@mantine/core';
import { ActionButton as Button } from '@components/button/ActionButton';
import { useAuth } from '@contexts/AuthContext';
import { useScene3D } from '@hooks/useScene3D';
import type { Scene3DController } from '@utils/Scene3DController';
import { Box3, Mesh, MeshStandardMaterial, Vector3 } from 'three';
import {
  CVT_MODEL_IDS,
  createCVTModels,
  createPulleyModels,
  positionCVT,
} from '@components/scene3DViewer/proceduralModels';
import { orientInspectionModels } from '@components/scene3DViewer/inspectionFrame';
import {
  mechanismLayout,
  primaryTipDimensions,
} from '@components/scene3DViewer/mechanisms';
import { positionBeam } from '@components/scene3DViewer/mechanismGeometry';
import {
  sceneConfiguration,
  sceneDistance,
  sceneGeometry,
  type SceneGeometry,
} from '@components/scene3DViewer/sceneSpec';
import {
  formatPreferredQuantity,
  normalizeUnitPreferences,
} from '@utils/units';
import {
  hardwareMeasurementKey,
  isPrimaryMeasurement,
  type HardwareMeasurementKey,
} from './hardwareMeasurementKeys';
import {
  previewCvtMechanism,
  previewCvtPulleys,
  type CvtData,
  type CvtEditorScenePreview,
} from './api';
import { primaryFixedPivot, primaryShaftRadius } from './cvtHardware';

function projected(point: Vector3, controller: Scene3DController, svg: SVGSVGElement) {
  const camera = controller.getCamera();
  const projectedPoint = point.clone().project(camera);
  if (projectedPoint.z < -1 || projectedPoint.z > 1) return null;
  const rect = svg.getBoundingClientRect();
  return {
    x: ((projectedPoint.x + 1) * rect.width) / 2,
    y: ((1 - projectedPoint.y) * rect.height) / 2,
  };
}

function localWorld(
  controller: Scene3DController,
  model: string,
  local: Vector3,
): Vector3 | null {
  const object = controller.getModel(model)?.object3D;
  if (!object) return null;
  object.updateWorldMatrix(true, true);
  return local.clone().applyMatrix4(object.matrixWorld);
}

function setLine(
  svg: SVGSVGElement,
  a: Vector3 | null,
  b: Vector3 | null,
  label: string,
  controller: Scene3DController,
) {
  const group = svg.querySelector<SVGGElement>('[data-measurement]');
  if (!group || !a || !b) {
    if (group) group.style.display = 'none';
    return;
  }
  const pa = projected(a, controller, svg);
  const pb = projected(b, controller, svg);
  if (!pa || !pb) {
    group.style.display = 'none';
    return;
  }
  group.style.display = '';
  const line = group.querySelector('line')!;
  line.setAttribute('x1', String(pa.x));
  line.setAttribute('y1', String(pa.y));
  line.setAttribute('x2', String(pb.x));
  line.setAttribute('y2', String(pb.y));
  const circles = group.querySelectorAll('circle');
  circles[0]?.setAttribute('cx', String(pa.x));
  circles[0]?.setAttribute('cy', String(pa.y));
  circles[1]?.setAttribute('cx', String(pb.x));
  circles[1]?.setAttribute('cy', String(pb.y));
  const text = group.querySelector('text')!;
  text.setAttribute('x', String((pa.x + pb.x) / 2 + 7));
  text.setAttribute('y', String((pa.y + pb.y) / 2 - 7));
  text.textContent = label;
}

function MeasurementSvg({ svgRef }: { svgRef: RefObject<SVGSVGElement | null> }) {
  return (
    <svg
      ref={svgRef}
      aria-label="Active hardware measurement"
      role="img"
      style={{
        position: 'absolute',
        inset: 0,
        width: '100%',
        height: '100%',
        pointerEvents: 'none',
        zIndex: 3,
        overflow: 'hidden',
      }}
    >
      <g data-measurement style={{ display: 'none' }}>
        <line stroke="var(--mantine-primary-color-filled)" strokeWidth={2} />
        <circle r={4} fill="var(--mantine-color-body)" stroke="var(--mantine-primary-color-filled)" strokeWidth={2} />
        <circle r={4} fill="var(--mantine-color-body)" stroke="var(--mantine-primary-color-filled)" strokeWidth={2} />
        <text
          fontSize={12}
          fontWeight={600}
          fill="currentColor"
          stroke="var(--mantine-color-body)"
          strokeWidth={4}
          paintOrder="stroke"
        />
      </g>
    </svg>
  );
}

function fitModels(controller: Scene3DController, ids: string[], margin: number) {
  const bounds = new Box3();
  ids.forEach((id) => {
    const object = controller.getModel(id)?.object3D;
    if (!object || !object.visible) return;
    object.updateWorldMatrix(true, true);
    bounds.union(new Box3().setFromObject(object));
  });
  if (!bounds.isEmpty()) controller.fitBounds(bounds.expandByScalar(margin));
}

function measurementText(
  key: HardwareMeasurementKey | null,
  value: CvtData,
  preferences: ReturnType<typeof normalizeUnitPreferences>,
) {
  const fixed = primaryFixedPivot(value.assembly)?.component;
  switch (key) {
    case 'shaft-radius':
      return `Primary shaft radius · ${formatPreferredQuantity(primaryShaftRadius(value), 'length', 'hardware', preferences, 'mm', 3)}`;
    case 'secondary-radius':
      return `Secondary belt radius · ${formatPreferredQuantity(value.assembly.geometry.secondary_outer_radius_at_zero_shift_m, 'length', 'hardware', preferences, 'mm', 3)}`;
    case 'primary-travel':
      return `Primary travel · ${formatPreferredQuantity(value.assembly.geometry.max_shift_m, 'length', 'hardware', preferences, 'mm', 3)}`;
    case 'deadzone-travel':
      return `Free travel before belt contact · ${formatPreferredQuantity(value.assembly.geometry.deadzone_shift_m, 'length', 'hardware', preferences, 'mm', 3)}`;
    case 'sheave-angle':
      return `Sheave half-angle · ${formatPreferredQuantity(value.assembly.geometry.sheave_half_angle_rad, 'angle', 'hardware', preferences, 'deg', 2)}`;
    case 'pivot-radius':
      return fixed ? `Pivot radius · ${formatPreferredQuantity(fixed.geometry.pivot_radius_m, 'length', 'hardware', preferences, 'mm', 3)}` : '';
    case 'arm-length':
      return fixed ? `Arm length · ${formatPreferredQuantity(fixed.geometry.arm_length_m, 'length', 'hardware', preferences, 'mm', 3)}` : '';
    case 'roller-radius':
      return fixed ? `Roller radius · ${formatPreferredQuantity(fixed.geometry.roller_radius_m, 'length', 'hardware', preferences, 'mm', 3)}` : '';
    default:
      return '';
  }
}

function useDebouncedPreview<T>(
  key: string,
  request: (signal: AbortSignal) => Promise<T>,
  delay = 220,
) {
  const [resolved, setResolved] = useState<{ key: string; value: T } | null>(null);
  const [failure, setFailure] = useState<{ key: string; message: string } | null>(null);
  useEffect(() => {
    const controller = new AbortController();
    const timer = window.setTimeout(() => {
      void request(controller.signal)
        .then((value) => {
          if (!controller.signal.aborted) {
            setResolved({ key, value });
            setFailure(null);
          }
        })
        .catch((cause) => {
          if (!controller.signal.aborted)
            setFailure({ key, message: cause instanceof Error ? cause.message : String(cause) });
        });
    }, delay);
    return () => {
      window.clearTimeout(timer);
      controller.abort();
    };
  }, [key, request, delay]);
  return {
    value: resolved?.value ?? null,
    current: resolved?.key === key,
    error: failure?.key === key ? failure.message : null,
  };
}

function PulleyScene({
  preview,
  value,
  frameIndex,
  active,
  resetKey,
}: {
  preview: CvtEditorScenePreview;
  value: CvtData;
  frameIndex: number;
  active: HardwareMeasurementKey | null;
  resetKey: number;
}) {
  const geometry = useMemo(() => sceneGeometry(preview.geometry), [preview.geometry]);
  const models = useMemo(
    () => createPulleyModels(geometry, sceneDistance(primaryShaftRadius(value))),
    [geometry, value],
  );
  const config = sceneConfiguration(false);
  config.renderOnDemand = true;
  config.camera.position = [3, 7, 19];
  const { containerRef, sceneController, error } = useScene3D({ sceneConfig: config, models });
  const frame = preview.frames[frameIndex] ?? preview.frames[0];
  const fitted = useRef<{ controller: Scene3DController; reset: number } | null>(null);
  const overlay = useRef<SVGSVGElement>(null);
  const { unitPreferences } = useAuth();
  const preferences = normalizeUnitPreferences(unitPreferences);
  const label = measurementText(active, value, preferences);

  useEffect(() => {
    if (!sceneController || !frame) return;
    positionCVT(sceneController, geometry, {
      primaryRadius: sceneDistance(frame.primary_outer_radius_m),
      secondaryRadius: sceneDistance(frame.secondary_outer_radius_m),
      primaryCenter: [-geometry.centreDistance / 2, 0],
      secondaryCenter: [geometry.centreDistance / 2, 0],
      shift: sceneDistance(frame.shift_m),
      beltZ: sceneDistance(frame.belt_axial_position_m),
    });
    if (
      !fitted.current ||
      fitted.current.controller !== sceneController ||
      fitted.current.reset !== resetKey
    ) {
      fitModels(
        sceneController,
        [...CVT_MODEL_IDS],
        geometry.beltHeight * 0.35,
      );
      fitted.current = { controller: sceneController, reset: resetKey };
    }
  }, [sceneController, frame, geometry, resetKey]);

  useEffect(() => {
    if (!sceneController || !frame || !overlay.current) return;
    const update = () => {
      const svg = overlay.current;
      if (!svg) return;
      const primaryRadius = sceneDistance(primaryShaftRadius(value));
      const secondaryRadius = sceneDistance(value.assembly.geometry.secondary_outer_radius_at_zero_shift_m);
      let a: Vector3 | null = null;
      let b: Vector3 | null = null;
      if (active === 'shaft-radius') {
        a = localWorld(sceneController, 'primaryFixed', new Vector3());
        b = localWorld(sceneController, 'primaryFixed', new Vector3(primaryRadius, 0, 0));
      } else if (active === 'secondary-radius') {
        a = localWorld(sceneController, 'secondaryFixed', new Vector3());
        b = localWorld(sceneController, 'secondaryFixed', new Vector3(secondaryRadius, 0, 0));
      } else if (active === 'primary-travel' || active === 'deadzone-travel') {
        const length = sceneDistance(
          active === 'primary-travel'
            ? value.assembly.geometry.max_shift_m
            : value.assembly.geometry.deadzone_shift_m,
        );
        const radial = geometry.primaryMaxRadius * 1.08;
        a = localWorld(sceneController, 'primaryFixed', new Vector3(radial, 0, 0));
        b = localWorld(sceneController, 'primaryFixed', new Vector3(radial, 0, -length));
      } else if (active === 'sheave-angle') {
        const radial = geometry.primaryMaxRadius * 0.92;
        a = localWorld(sceneController, 'primaryFixed', new Vector3(radial, 0, 0));
        b = localWorld(
          sceneController,
          'primaryFixed',
          new Vector3(radial - geometry.beltHeight, 0, -geometry.beltHeight * Math.tan(geometry.halfAngle)),
        );
      }
      setLine(svg, a, b, label, sceneController);
    };
    update();
    return sceneController.onFrame(update);
  }, [sceneController, frame, geometry, active, label, value]);

  return (
    <Box h={340} pos="relative" style={{ minWidth: 0 }}>
      <div ref={containerRef} style={{ position: 'absolute', inset: 0 }} />
      <MeasurementSvg svgRef={overlay} />
      {error && <Alert pos="absolute" left={8} right={8} bottom={8} title="3D preview unavailable">{error}</Alert>}
    </Box>
  );
}

export function CvtPulleyPreview({ value, activePath }: { value: CvtData; activePath: string | null }) {
  const key = JSON.stringify(value.assembly.geometry);
  const request = useCallback(
    (signal: AbortSignal) => previewCvtPulleys(value, signal),
    [value],
  );
  const preview = useDebouncedPreview(key, request);
  const [travel, setTravel] = useState(0);
  const [reset, setReset] = useState(0);
  const active = hardwareMeasurementKey(activePath);
  useEffect(() => {
    if (active === 'primary-travel') setTravel(100);
    else if (active === 'deadzone-travel') {
      const maximum = value.assembly.geometry.max_shift_m;
      setTravel(
        maximum > 0
          ? Math.min(
              100,
              (100 * value.assembly.geometry.deadzone_shift_m) / maximum,
            )
          : 0,
      );
    } else if (
      active === 'shaft-radius' ||
      active === 'secondary-radius' ||
      active === 'sheave-angle'
    )
      setTravel(0);
  }, [
    active,
    value.assembly.geometry.deadzone_shift_m,
    value.assembly.geometry.max_shift_m,
  ]);
  const frameIndex = preview.value?.frames.length
    ? Math.round((travel / 100) * (preview.value.frames.length - 1))
    : 0;
  return (
    <Stack gap="xs">
      <Group justify="space-between">
        <div>
          <Text fw={600}>Pulley geometry preview</Text>
          <Text size="xs" c="dimmed">Pulleys and shafts only. Focus a measurement below to mark it on the model.</Text>
        </div>
        <Button size="compact-xs" variant="subtle" disabled={!preview.value} onClick={() => setReset((n) => n + 1)}>
          Reset view
        </Button>
      </Group>
      {preview.error && <Alert color="orange">{preview.error}{preview.value && ' The view still shows the last valid geometry.'}</Alert>}
      {!preview.current && !preview.error && <Text role="status" size="xs" c="dimmed">Updating pulley geometry…</Text>}
      {preview.value ? (
        <PulleyScene preview={preview.value} value={value} frameIndex={frameIndex} active={isPrimaryMeasurement(active) ? null : active} resetKey={reset} />
      ) : !preview.error ? <Loader size="sm" /> : null}
      <Text size="sm" fw={500}>Primary travel position</Text>
      <Slider
        min={0}
        max={100}
        step={1}
        value={travel}
        onChange={setTravel}
        disabled={!preview.value}
        label={(v) => `${v.toFixed(0)}%`}
        marks={[{ value: 0, label: 'Open' }, { value: 100, label: 'Closed' }]}
      />
      <Text size="xs" c="dimmed">Drag to rotate · Scroll or pinch to zoom. The slider is visual only and does not edit the CVT.</Text>
    </Stack>
  );
}

function setRampAppearance(controller: Scene3DController, visible: boolean) {
  const ramp = controller.getModel('primaryRamps')?.object3D;
  if (!ramp) return;
  ramp.visible = visible;
  ramp.traverse((object) => {
    if (!(object instanceof Mesh)) return;
    const materials = Array.isArray(object.material) ? object.material : [object.material];
    materials.forEach((material) => {
      if (!(material instanceof MeshStandardMaterial)) return;
      material.transparent = true;
      material.opacity = 0.18;
      material.depthWrite = false;
    });
  });
}

function positionPlaceholderFlyweight(
  controller: Scene3DController,
  geometry: SceneGeometry,
  armLengthM: number,
) {
  const spec = geometry.mechanisms?.primary;
  const weights = controller.getModel('flyweights')?.object3D;
  if (!spec || !weights) return;
  const layout = mechanismLayout(geometry);
  const rollerRadius = sceneDistance(spec.roller_radius_m);
  const armLength = sceneDistance(armLengthM);
  const angle = Math.PI * 35 / 180;
  const pivot = new Vector3(sceneDistance(spec.pivot_m[1]), 0, layout.pivotZ);
  const roller = pivot.clone().add(new Vector3(
    armLength * Math.sin(angle),
    0,
    -armLength * Math.cos(angle),
  ));
  const width = rollerRadius * 1.15;
  const tip = primaryTipDimensions(rollerRadius, spec.tip_mass_per_flyweight_kg);
  weights.visible = true;
  weights.children.forEach((group) => {
    for (const [name, side] of [['arm-left', -1], ['arm-right', 1]] as const) {
      const across = side * width * 0.68;
      const arm = group.getObjectByName(name);
      if (arm) positionBeam(
        arm,
        pivot.clone().add(new Vector3(0, across, 0)),
        roller.clone().add(new Vector3(0, across, 0)),
      );
    }
    const rollerObject = group.getObjectByName('roller');
    if (rollerObject) rollerObject.position.copy(roller);
    for (const [name, side] of [['weight-left', -1], ['weight-right', 1]] as const) {
      const weight = group.getObjectByName(name);
      if (weight) weight.position.copy(roller).y = side * tip.centreAcross;
    }
  });
}

function FlyweightLabels({
  controller,
  geometry,
  active,
  value,
  showRamp,
}: {
  controller: Scene3DController;
  geometry: SceneGeometry;
  active: HardwareMeasurementKey | null;
  value: CvtData;
  showRamp: boolean;
}) {
  const svg = useRef<SVGSVGElement>(null);
  const { unitPreferences } = useAuth();
  const preferences = normalizeUnitPreferences(unitPreferences);
  const label = measurementText(active, value, preferences);
  useEffect(() => {
    const root = svg.current;
    if (!root) return;
    const fixed = primaryFixedPivot(value.assembly)?.component;
    const spec = geometry.mechanisms?.primary;
    if (!fixed || !spec) return;
    const layout = mechanismLayout(geometry);
    const update = () => {
      const primary = controller.getModel('primaryFixed')?.object3D;
      const rollerObject = controller.getModel('flyweights')?.object3D.getObjectByName('roller');
      if (!primary || !rollerObject) return;
      primary.updateWorldMatrix(true, true);
      rollerObject.updateWorldMatrix(true, true);
      const pivotWorld = new Vector3(sceneDistance(spec.pivot_m[1]), 0, layout.pivotZ).applyMatrix4(primary.matrixWorld);
      const shaftWorld = new Vector3(0, 0, layout.pivotZ).applyMatrix4(primary.matrixWorld);
      const rollerWorld = rollerObject.getWorldPosition(new Vector3());
      const marker = (name: string, point: Vector3, text: string) => {
        const group = root.querySelector<SVGGElement>(`[data-point="${name}"]`)!;
        const p = projected(point, controller, root);
        group.style.display = p ? '' : 'none';
        if (!p) return;
        group.setAttribute('transform', `translate(${p.x},${p.y})`);
        group.querySelector('text')!.textContent = text;
      };
      marker('shaft', shaftWorld, 'Shaft centreline');
      marker('pivot', pivotWorld, 'Pivot');
      marker('roller', rollerWorld, 'Roller centre');
      const rampGroup = root.querySelector<SVGGElement>('[data-point="ramp"]')!;
      const ramp = controller.getModel('primaryRamps')?.object3D;
      if (showRamp && ramp) {
        ramp.updateWorldMatrix(true, true);
        const bounds = new Box3().setFromObject(ramp);
        const center = bounds.getCenter(new Vector3());
        const p = projected(center, controller, root);
        rampGroup.style.display = p ? '' : 'none';
        if (p) rampGroup.setAttribute('transform', `translate(${p.x},${p.y})`);
      } else rampGroup.style.display = 'none';
      let a: Vector3 | null = null;
      let b: Vector3 | null = null;
      if (active === 'pivot-radius') {
        a = shaftWorld;
        b = pivotWorld;
      } else if (active === 'arm-length') {
        a = pivotWorld;
        b = rollerWorld;
      } else if (active === 'roller-radius') {
        const outward = rollerWorld.clone().sub(pivotWorld).normalize();
        a = rollerWorld;
        b = rollerWorld.clone().addScaledVector(outward, sceneDistance(fixed.geometry.roller_radius_m));
      }
      setLine(root, a, b, label, controller);
    };
    update();
    return controller.onFrame(update);
  }, [controller, geometry, active, label, showRamp, value]);
  const point = (key: string, text: string, left = false) => (
    <g data-point={key} style={{ display: 'none' }}>
      <circle r={4} fill="var(--mantine-color-body)" stroke="currentColor" strokeWidth={1.5} />
      <path d={left ? 'M-3 3 L-11 15' : 'M3 -3 L11 -15'} fill="none" stroke="currentColor" />
      <text
        x={left ? -14 : 14}
        y={left ? 20 : -11}
        textAnchor={left ? 'end' : 'start'}
        fontSize={11}
        fill="currentColor"
        stroke="var(--mantine-color-body)"
        strokeWidth={3}
        paintOrder="stroke"
      >{text}</text>
    </g>
  );
  return (
    <svg
      ref={svg}
      role="img"
      aria-label="Flyweight hardware reference points and active measurement"
      style={{ position: 'absolute', inset: 0, width: '100%', height: '100%', pointerEvents: 'none', zIndex: 3 }}
    >
      {point('shaft', 'Shaft centreline', true)}
      {point('pivot', 'Pivot', true)}
      {point('roller', 'Roller centre')}
      {point('ramp', 'Reference ramp · adjusted in Tunes')}
      <g data-measurement style={{ display: 'none' }}>
        <line stroke="var(--mantine-primary-color-filled)" strokeWidth={2} />
        <circle r={4} fill="var(--mantine-color-body)" stroke="var(--mantine-primary-color-filled)" strokeWidth={2} />
        <circle r={4} fill="var(--mantine-color-body)" stroke="var(--mantine-primary-color-filled)" strokeWidth={2} />
        <text fontSize={12} fontWeight={600} fill="currentColor" stroke="var(--mantine-color-body)" strokeWidth={4} paintOrder="stroke" />
      </g>
    </svg>
  );
}

function FlyweightScene({
  preview,
  value,
  active,
  showRamp,
  resetKey,
}: {
  preview: CvtEditorScenePreview;
  value: CvtData;
  active: HardwareMeasurementKey | null;
  showRamp: boolean;
  resetKey: number;
}) {
  const geometry = useMemo(() => sceneGeometry(preview.geometry), [preview.geometry]);
  const fixedPivot = primaryFixedPivot(value.assembly);
  const frame = preview.frames[0];
  const models = useMemo(
    () => orientInspectionModels(createCVTModels(geometry, 'primary'), 'primary'),
    [geometry],
  );
  const config = sceneConfiguration(false);
  config.renderOnDemand = true;
  config.camera.position = [5, 4, 18];
  config.camera.lookAt = [0, 0, 0];
  const { containerRef, sceneController, error } = useScene3D({ sceneConfig: config, models });
  const fitted = useRef<{ controller: Scene3DController; reset: number } | null>(null);

  useEffect(() => {
    if (!sceneController || !frame || !fixedPivot) return;
    positionCVT(sceneController, geometry, {
      primaryRadius: sceneDistance(frame.primary_outer_radius_m),
      secondaryRadius: sceneDistance(frame.secondary_outer_radius_m),
      primaryCenter: [0, 0],
      secondaryCenter: [0, 0],
      shift: sceneDistance(frame.shift_m),
      beltZ: sceneDistance(frame.belt_axial_position_m),
    });
    positionPlaceholderFlyweight(
      sceneController,
      geometry,
      fixedPivot.component.geometry.arm_length_m,
    );
    setRampAppearance(sceneController, showRamp);
    if (
      !fitted.current ||
      fitted.current.controller !== sceneController ||
      fitted.current.reset !== resetKey
    ) {
      fitModels(sceneController, ['primaryCarrier', 'flyweights'], geometry.beltHeight * 0.6);
      fitted.current = { controller: sceneController, reset: resetKey };
    }
  }, [sceneController, frame, fixedPivot, geometry, showRamp, resetKey]);

  return (
    <>
      <Box h={350} pos="relative" style={{ minWidth: 0 }}>
        <div ref={containerRef} style={{ position: 'absolute', inset: 0 }} />
        {sceneController && (
          <FlyweightLabels controller={sceneController} geometry={geometry} active={active} value={value} showRamp={showRamp} />
        )}
        {error && <Alert pos="absolute" left={8} right={8} bottom={8} title="3D preview unavailable">{error}</Alert>}
      </Box>
      <Text size="xs" c="dimmed">
        Reference arm pose only. It is not the solved initial roller contact. Ramp
        placement and shape are adjusted in Tunes, not in this hardware section.
      </Text>
    </>
  );
}

export function CvtPrimaryHardwarePreview({ value, activePath }: { value: CvtData; activePath: string | null }) {
  const key = JSON.stringify(value);
  const request = useCallback(
    (signal: AbortSignal) => previewCvtMechanism(value, signal),
    [value],
  );
  const preview = useDebouncedPreview(key, request, 280);
  const [showRamp, setShowRamp] = useState(true);
  const [reset, setReset] = useState(0);
  const active = hardwareMeasurementKey(activePath);
  return (
    <Stack gap="xs">
      <Group justify="space-between" align="center">
        <div>
          <Text fw={600}>Flyweight mounting preview</Text>
          <Text size="xs" c="dimmed">One enlarged flyweight. Labels stay fixed to the hardware; focus a field to show its measurement.</Text>
        </div>
        <Group gap="xs">
          <Switch
            size="sm"
            label="Show reference ramp"
            checked={showRamp}
            onChange={(event) => setShowRamp(event.currentTarget.checked)}
          />
          <Button size="compact-xs" variant="subtle" disabled={!preview.value} onClick={() => setReset((n) => n + 1)}>
            Reset view
          </Button>
        </Group>
      </Group>
      {preview.error && <Alert color="orange">{preview.error}{preview.value && ' The view still shows the last valid mechanism.'}</Alert>}
      {!preview.current && !preview.error && <Text role="status" size="xs" c="dimmed">Updating flyweight geometry…</Text>}
      {preview.value && primaryFixedPivot(value.assembly) ? (
        <FlyweightScene preview={preview.value} value={value} active={isPrimaryMeasurement(active) ? active : null} showRamp={showRamp} resetKey={reset} />
      ) : !preview.error ? <Loader size="sm" /> : null}
      <Text size="xs" c="dimmed">Drag to rotate · Scroll or pinch to zoom. Hiding the reference ramp does not change the CVT.</Text>
    </Stack>
  );
}
