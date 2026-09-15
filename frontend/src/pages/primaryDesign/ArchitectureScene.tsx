import { useMemo, useRef, useState } from 'react';
import type {
  ArchitectureAnalysis,
  FixedPivotArchitecture,
  PackagingZone,
  PackagingZoneRule,
  PackagingZoneSubject,
} from '@api/primaryDesign';
import styles from './PrimaryDesign.module.scss';

const WIDTH = 1040;
const HEIGHT = 640;
const PAD = 34;
const MIN_ARM_M = 2e-3;
const MIN_TRAVEL_M = 0.5e-3;

type DrawTool = 'select' | 'draw-zone';
type DragKind = 'pivot' | 'arm' | 'travel';

interface WorldPoint {
  x: number;
  r: number;
}

interface ArchitectureSceneProps {
  architecture: FixedPivotArchitecture;
  analysis: ArchitectureAnalysis | null;
  zones: PackagingZone[];
  stale: boolean;
  selectedZoneId: string | null;
  onArchitectureChange: (patch: Partial<FixedPivotArchitecture>) => void;
  onZonesChange: (zones: PackagingZone[]) => void;
  onSelectedZoneChange: (zoneId: string | null) => void;
}

export function ArchitectureScene({
  architecture,
  analysis,
  zones,
  stale,
  selectedZoneId,
  onArchitectureChange,
  onZonesChange,
  onSelectedZoneChange,
}: ArchitectureSceneProps) {
  const svgRef = useRef<SVGSVGElement | null>(null);
  const [tool, setTool] = useState<DrawTool>('select');
  const [drawSubject, setDrawSubject] = useState<PackagingZoneSubject>('flyweight');
  const [drawRule, setDrawRule] = useState<PackagingZoneRule>('forbid');
  const [draftPoints, setDraftPoints] = useState<WorldPoint[]>([]);
  const [drag, setDrag] = useState<{ kind: DragKind; pointerId: number } | null>(null);

  const view = useMemo(() => {
    const fallback = {
      x_min_m: architecture.pivot_axial_position_m - architecture.arm_length_m - 0.02,
      x_max_m: architecture.pivot_axial_position_m + architecture.arm_length_m + architecture.required_travel_m + 0.08,
      r_min_m: Math.max(0, architecture.pivot_radius_m - 0.03),
      r_max_m: architecture.pivot_radius_m + architecture.arm_length_m + architecture.roller_radius_m + 0.03,
    };
    if (!analysis) return fallback;
    const currentArmEnd = draftArmEndpoint(architecture, analysis);
    return {
      x_min_m: Math.min(analysis.viewport.x_min_m, architecture.pivot_axial_position_m - 0.01, currentArmEnd.x - 0.01),
      x_max_m: Math.max(analysis.viewport.x_max_m, architecture.pivot_axial_position_m + 0.01, currentArmEnd.x + 0.01),
      r_min_m: Math.max(0, Math.min(analysis.viewport.r_min_m, architecture.pivot_radius_m - 0.01, currentArmEnd.r - 0.01)),
      r_max_m: Math.max(analysis.viewport.r_max_m, architecture.pivot_radius_m + 0.01, currentArmEnd.r + 0.01),
    };
  }, [analysis, architecture]);

  const scene = useMemo(() => createScene(view), [view]);
  const armEndpoint = useMemo(
    () => analysis ? draftArmEndpoint(architecture, analysis) : {
      x: architecture.pivot_axial_position_m + architecture.arm_length_m,
      r: architecture.pivot_radius_m,
    },
    [analysis, architecture],
  );
  const q90Endpoint = useMemo(
    () => analysis ? draftQ90Endpoint(architecture, analysis) : {
      x: architecture.pivot_axial_position_m,
      r: architecture.pivot_radius_m + architecture.arm_length_m,
    },
    [analysis, architecture],
  );

  const openA = analysis && analysis.ramp_surface.open.x_m.length > 0
    ? { x: analysis.ramp_surface.open.x_m[0], r: analysis.ramp_surface.open.r_m[0] }
    : null;
  const travelHandle = openA
    ? { x: openA.x + architecture.required_travel_m, r: openA.r }
    : null;

  const worldFromPointer = (event: React.PointerEvent<SVGSVGElement>): WorldPoint | null => {
    const svg = svgRef.current;
    const matrix = svg?.getScreenCTM();
    if (!svg || !matrix) return null;
    const point = svg.createSVGPoint();
    point.x = event.clientX;
    point.y = event.clientY;
    const local = point.matrixTransform(matrix.inverse());
    return scene.world(local.x, local.y);
  };

  const beginDrag = (event: React.PointerEvent<SVGElement>, kind: DragKind) => {
    if (tool !== 'select') return;
    event.stopPropagation();
    svgRef.current?.setPointerCapture(event.pointerId);
    setDrag({ kind, pointerId: event.pointerId });
  };

  const onPointerMove = (event: React.PointerEvent<SVGSVGElement>) => {
    if (!drag || drag.pointerId !== event.pointerId) return;
    const world = worldFromPointer(event);
    if (!world) return;
    if (drag.kind === 'pivot') {
      onArchitectureChange({
        pivot_axial_position_m: world.x,
        pivot_radius_m: Math.max(0.5e-3, world.r),
      });
      return;
    }
    if (drag.kind === 'arm') {
      const dx = world.x - architecture.pivot_axial_position_m;
      const dr = world.r - architecture.pivot_radius_m;
      onArchitectureChange({ arm_length_m: Math.max(MIN_ARM_M, Math.hypot(dx, dr)) });
      return;
    }
    if (openA) {
      onArchitectureChange({ required_travel_m: Math.max(MIN_TRAVEL_M, world.x - openA.x) });
    }
  };

  const stopDrag = (event: React.PointerEvent<SVGSVGElement>) => {
    if (drag?.pointerId === event.pointerId) {
      if (svgRef.current?.hasPointerCapture(event.pointerId)) {
        svgRef.current.releasePointerCapture(event.pointerId);
      }
      setDrag(null);
    }
  };

  const addDraftPoint = (event: React.PointerEvent<SVGSVGElement>) => {
    if (tool !== 'draw-zone') return;
    const world = worldFromPointer(event);
    if (!world) return;
    setDraftPoints((points) => [...points, world]);
  };

  const finishZone = () => {
    if (draftPoints.length < 3) return;
    const number = zones.length + 1;
    const id = typeof crypto !== 'undefined' && 'randomUUID' in crypto
      ? crypto.randomUUID()
      : `zone-${Date.now().toString(36)}`;
    const label = `${drawSubject === 'flyweight' ? 'Flyweight' : 'Ramp'} ${drawRule === 'forbid' ? 'keep-out' : 'allowed'} ${number}`;
    const zone: PackagingZone = {
      id,
      label,
      subject: drawSubject,
      rule: drawRule,
      polygon_m: draftPoints.map((point) => [point.x, point.r]),
      clearance_m: 0,
    };
    onZonesChange([...zones, zone]);
    onSelectedZoneChange(id);
    setDraftPoints([]);
    setTool('select');
  };

  const deleteSelected = () => {
    if (!selectedZoneId) return;
    onZonesChange(zones.filter((zone) => zone.id !== selectedZoneId));
    onSelectedZoneChange(null);
  };

  const reach = analysis?.reach;
  const requestedRampOpacity = stale ? 0.35 : 0.85;

  return (
    <div className={styles.architectureSceneWrap}>
      <div className={styles.architectureToolbar}>
        <div className={styles.toolGroup}>
          <button type="button" className={tool === 'select' ? styles.toolActive : styles.toolButton} onClick={() => { setTool('select'); setDraftPoints([]); }}>
            Select / move
          </button>
          <button type="button" className={tool === 'draw-zone' ? styles.toolActive : styles.toolButton} onClick={() => setTool('draw-zone')}>
            Draw zone
          </button>
        </div>
        <label className={styles.compactField}>
          <span>Subject</span>
          <select value={drawSubject} onChange={(event) => setDrawSubject(event.target.value as PackagingZoneSubject)}>
            <option value="flyweight">Flyweight</option>
            <option value="ramp">Ramp</option>
          </select>
        </label>
        <label className={styles.compactField}>
          <span>Rule</span>
          <select value={drawRule} onChange={(event) => setDrawRule(event.target.value as PackagingZoneRule)}>
            <option value="forbid">Keep-out</option>
            <option value="contain">Must stay inside</option>
          </select>
        </label>
        {tool === 'draw-zone' && (
          <>
            <button type="button" className={styles.toolButton} disabled={draftPoints.length < 3} onClick={finishZone}>Finish zone</button>
            <button type="button" className={styles.toolButton} onClick={() => setDraftPoints([])}>Cancel</button>
          </>
        )}
        <button type="button" className={styles.toolButton} disabled={!selectedZoneId} onClick={deleteSelected}>Delete selected</button>
        <div className={styles.toolbarSpacer} />
        <span className={stale ? styles.dirty : styles.valid}>{stale ? 'workspace stale' : 'workspace current'}</span>
      </div>

      <svg
        ref={svgRef}
        viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
        role="img"
        aria-label="Fixed-pivot primary architecture and packaging workspace"
        className={tool === 'draw-zone' ? styles.crosshairCanvas : styles.engineeringCanvas}
        onPointerDown={addDraftPoint}
        onPointerMove={onPointerMove}
        onPointerUp={stopDrag}
        onPointerCancel={stopDrag}
      >
        <rect width={WIDTH} height={HEIGHT} rx="12" fill="var(--primary-design-canvas, #0d1319)" />
        <EngineeringGrid scene={scene} />

        {zones.map((zone) => (
          <polygon
            key={zone.id}
            points={zone.polygon_m.map(([x, r]) => `${scene.sx(x)},${scene.sy(r)}`).join(' ')}
            className={zoneClass(zone, zone.id === selectedZoneId)}
            onPointerDown={(event) => {
              if (tool !== 'select') return;
              event.stopPropagation();
              onSelectedZoneChange(zone.id);
            }}
          />
        ))}

        {analysis?.envelopes.flyweight_swept.map((polygon, index) => (
          <path key={`fly-sweep-${index}`} d={scene.path(polygon.x_m, polygon.r_m, true)} className={styles.flyweightEnvelope} opacity={stale ? 0.22 : 0.38} />
        ))}
        {analysis?.envelopes.ramp_swept.map((polygon, index) => (
          <path key={`ramp-sweep-${index}`} d={scene.path(polygon.x_m, polygon.r_m, true)} className={styles.rampEnvelope} opacity={stale ? 0.18 : 0.32} />
        ))}

        {analysis && (
          <>
            <path d={scene.path(analysis.ramp_surface.open.x_m, analysis.ramp_surface.open.r_m)} className={styles.archRampOpen} opacity={requestedRampOpacity} />
            <path d={scene.path(analysis.ramp_surface.full_shift.x_m, analysis.ramp_surface.full_shift.r_m)} className={styles.archRampFull} opacity={requestedRampOpacity} />
          </>
        )}

        {reach && (
          <path
            d={scene.path(reach.roller_center_x_m, reach.roller_center_r_m)}
            className={styles.reachBase}
            opacity={stale ? 0.22 : 0.5}
          />
        )}
        {reach && reach.q_deg.slice(0, -1).map((_q, index) => {
          const ok = reach.admissible[index] && reach.admissible[index + 1];
          return (
            <line
              key={`reach-${index}`}
              x1={scene.sx(reach.roller_center_x_m[index])}
              y1={scene.sy(reach.roller_center_r_m[index])}
              x2={scene.sx(reach.roller_center_x_m[index + 1])}
              y2={scene.sy(reach.roller_center_r_m[index + 1])}
              className={ok ? styles.reachAdmissible : styles.reachBlocked}
              opacity={stale ? 0.35 : 0.95}
            />
          );
        })}

        <line
          x1={scene.sx(architecture.pivot_axial_position_m)}
          y1={scene.sy(architecture.pivot_radius_m)}
          x2={scene.sx(q90Endpoint.x)}
          y2={scene.sy(q90Endpoint.r)}
          className={styles.q90Boundary}
        />
        <text x={scene.sx(q90Endpoint.x) + 8} y={scene.sy(q90Endpoint.r) - 8} className={styles.svgLabel}>q = 90° hard limit</text>

        <line
          x1={scene.sx(architecture.pivot_axial_position_m)}
          y1={scene.sy(architecture.pivot_radius_m)}
          x2={scene.sx(armEndpoint.x)}
          y2={scene.sy(armEndpoint.r)}
          className={styles.archArm}
        />
        <circle
          cx={scene.sx(architecture.pivot_axial_position_m)}
          cy={scene.sy(architecture.pivot_radius_m)}
          r="8"
          className={styles.dragPivot}
          onPointerDown={(event) => beginDrag(event, 'pivot')}
        />
        <circle
          cx={scene.sx(armEndpoint.x)}
          cy={scene.sy(armEndpoint.r)}
          r="10"
          className={styles.dragHandle}
          onPointerDown={(event) => beginDrag(event, 'arm')}
        />
        <text x={scene.sx(architecture.pivot_axial_position_m) + 11} y={scene.sy(architecture.pivot_radius_m) + 18} className={styles.svgLabel}>pivot</text>
        <text x={scene.sx(armEndpoint.x) + 12} y={scene.sy(armEndpoint.r) - 12} className={styles.svgLabel}>arm length</text>

        {openA && travelHandle && (
          <>
            <circle cx={scene.sx(openA.x)} cy={scene.sy(openA.r)} r="5" className={styles.pointA} />
            <text x={scene.sx(openA.x) + 8} y={scene.sy(openA.r) - 8} className={styles.svgLabel}>A</text>
            <line x1={scene.sx(openA.x)} y1={scene.sy(openA.r) + 24} x2={scene.sx(travelHandle.x)} y2={scene.sy(travelHandle.r) + 24} className={styles.travelDimension} />
            <circle
              cx={scene.sx(travelHandle.x)}
              cy={scene.sy(travelHandle.r) + 24}
              r="8"
              className={styles.dragHandle}
              onPointerDown={(event) => beginDrag(event, 'travel')}
            />
            <text x={(scene.sx(openA.x) + scene.sx(travelHandle.x)) / 2 - 26} y={scene.sy(openA.r) + 45} className={styles.svgLabel}>required travel</text>
          </>
        )}

        {draftPoints.length > 0 && (
          <>
            <polyline
              points={draftPoints.map((point) => `${scene.sx(point.x)},${scene.sy(point.r)}`).join(' ')}
              className={styles.zoneDraft}
            />
            {draftPoints.map((point, index) => (
              <circle key={`draft-${index}`} cx={scene.sx(point.x)} cy={scene.sy(point.r)} r="4" className={styles.zoneDraftPoint} />
            ))}
          </>
        )}
      </svg>
      <div className={styles.sceneFooter}>
        <span>Axial x →</span>
        <span>Radial r ↑</span>
        {tool === 'draw-zone' && <strong>Click vertices, then Finish zone.</strong>}
        {tool === 'select' && <strong>Drag the pivot, arm handle, or travel handle.</strong>}
      </div>
    </div>
  );
}

function EngineeringGrid({ scene }: { scene: ReturnType<typeof createScene> }) {
  const vertical: number[] = [];
  const horizontal: number[] = [];
  const xStartMm = Math.ceil(scene.view.x_min_m * 1000 / 10) * 10;
  const xEndMm = Math.floor(scene.view.x_max_m * 1000 / 10) * 10;
  for (let mm = xStartMm; mm <= xEndMm; mm += 10) vertical.push(mm / 1000);
  const rStartMm = Math.ceil(scene.view.r_min_m * 1000 / 10) * 10;
  const rEndMm = Math.floor(scene.view.r_max_m * 1000 / 10) * 10;
  for (let mm = rStartMm; mm <= rEndMm; mm += 10) horizontal.push(mm / 1000);
  return (
    <g className={styles.engineeringGrid}>
      {vertical.map((x) => <line key={`gx-${x}`} x1={scene.sx(x)} y1={PAD} x2={scene.sx(x)} y2={HEIGHT - PAD} />)}
      {horizontal.map((r) => <line key={`gr-${r}`} x1={PAD} y1={scene.sy(r)} x2={WIDTH - PAD} y2={scene.sy(r)} />)}
    </g>
  );
}

function zoneClass(zone: PackagingZone, selected: boolean): string {
  const base = zone.rule === 'forbid'
    ? styles.zoneForbid
    : zone.subject === 'ramp'
      ? styles.zoneContainRamp
      : styles.zoneContainFlyweight;
  return selected ? `${base} ${styles.zoneSelected}` : base;
}

function draftArmEndpoint(architecture: FixedPivotArchitecture, analysis: ArchitectureAnalysis): WorldPoint {
  return {
    x: architecture.pivot_axial_position_m + analysis.manipulators.arm_direction_x * architecture.arm_length_m,
    r: architecture.pivot_radius_m + analysis.manipulators.arm_direction_r * architecture.arm_length_m,
  };
}

function draftQ90Endpoint(architecture: FixedPivotArchitecture, analysis: ArchitectureAnalysis): WorldPoint {
  const oldDx = analysis.manipulators.q90_endpoint_x_m - analysis.architecture.pivot_axial_position_m;
  const oldDr = analysis.manipulators.q90_endpoint_r_m - analysis.architecture.pivot_radius_m;
  const length = Math.hypot(oldDx, oldDr) || 1;
  return {
    x: architecture.pivot_axial_position_m + architecture.arm_length_m * oldDx / length,
    r: architecture.pivot_radius_m + architecture.arm_length_m * oldDr / length,
  };
}

function createScene(view: ArchitectureAnalysis['viewport']) {
  const xSpan = Math.max(1e-9, view.x_max_m - view.x_min_m);
  const rSpan = Math.max(1e-9, view.r_max_m - view.r_min_m);
  const innerWidth = WIDTH - 2 * PAD;
  const innerHeight = HEIGHT - 2 * PAD;
  const scale = Math.min(innerWidth / xSpan, innerHeight / rSpan);
  const usedWidth = scale * xSpan;
  const usedHeight = scale * rSpan;
  const xOffset = PAD + 0.5 * (innerWidth - usedWidth);
  const yOffset = PAD + 0.5 * (innerHeight - usedHeight);
  const sx = (x: number) => xOffset + (x - view.x_min_m) * scale;
  const sy = (r: number) => yOffset + usedHeight - (r - view.r_min_m) * scale;
  const world = (screenX: number, screenY: number): WorldPoint => ({
    x: view.x_min_m + (screenX - xOffset) / scale,
    r: view.r_min_m + (yOffset + usedHeight - screenY) / scale,
  });
  const path = (xs: number[], rs: number[], close = false) => {
    if (xs.length === 0 || xs.length !== rs.length) return '';
    const commands = xs.map((x, index) => `${index === 0 ? 'M' : 'L'} ${sx(x)} ${sy(rs[index])}`);
    if (close) commands.push('Z');
    return commands.join(' ');
  };
  return { view, sx, sy, world, path };
}
