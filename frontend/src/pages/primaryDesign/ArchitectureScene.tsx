import { useMemo, useRef, useState } from 'react';
import type {
  ArchitectureAnalysis,
  ArchitectureSlice,
  FixedPivotArchitecture,
  PackagingZone,
  PackagingZoneRule,
  PackagingZoneSubject,
  WorkspacePolygon,
} from '@api/primaryDesign';
import styles from './PrimaryDesign.module.scss';

const WIDTH = 1040;
const HEIGHT = 640;
const PAD = 34;
const MIN_ARM_M = 2e-3;
const MIN_TRAVEL_M = 0.5e-3;
const MM = 1000;

type DrawTool = 'select' | 'draw-zone';
type DragKind = 'pivot-radius' | 'arm' | 'travel';
type WorkspaceView = 'full' | 'slice';

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
  const [viewMode, setViewMode] = useState<WorkspaceView>('full');
  const [sliceShiftM, setSliceShiftM] = useState(0);
  const [drawSubject, setDrawSubject] = useState<PackagingZoneSubject>('flyweight');
  const [drawRule, setDrawRule] = useState<PackagingZoneRule>('forbid');
  const [draftPoints, setDraftPoints] = useState<WorldPoint[]>([]);
  const [drag, setDrag] = useState<{ kind: DragKind; pointerId: number } | null>(null);

  const currentSlice = useMemo(
    () => nearestSlice(analysis, Math.min(sliceShiftM, architecture.required_travel_m)),
    [analysis, architecture.required_travel_m, sliceShiftM],
  );

  const view = useMemo(() => {
    const fallback = {
      x_min_m: architecture.pivot_axial_position_m - architecture.required_travel_m - architecture.arm_length_m - 0.02,
      x_max_m: architecture.pivot_axial_position_m + architecture.arm_length_m + architecture.roller_radius_m + 0.02,
      r_min_m: Math.max(0, architecture.pivot_radius_m - architecture.arm_length_m - architecture.roller_radius_m - 0.02),
      r_max_m: architecture.pivot_radius_m + architecture.arm_length_m + architecture.roller_radius_m + 0.02,
    };
    if (!analysis) return fallback;
    const fullPivotX = architecture.pivot_axial_position_m - architecture.required_travel_m;
    const armHandle = draftArmEndpoint(architecture, analysis);
    return {
      x_min_m: Math.min(analysis.viewport.x_min_m, fullPivotX - architecture.arm_length_m - 0.01),
      x_max_m: Math.max(analysis.viewport.x_max_m, architecture.pivot_axial_position_m + architecture.arm_length_m + 0.01, armHandle.x + 0.01),
      r_min_m: Math.max(0, Math.min(analysis.viewport.r_min_m, architecture.pivot_radius_m - architecture.arm_length_m - 0.01)),
      r_max_m: Math.max(analysis.viewport.r_max_m, architecture.pivot_radius_m + architecture.arm_length_m + architecture.roller_radius_m + 0.01),
    };
  }, [analysis, architecture]);

  const scene = useMemo(() => createScene(view), [view]);
  const armEndpoint = useMemo(
    () => analysis ? draftArmEndpoint(architecture, analysis) : {
      x: architecture.pivot_axial_position_m + architecture.arm_length_m / Math.sqrt(2),
      r: architecture.pivot_radius_m + architecture.arm_length_m / Math.sqrt(2),
    },
    [analysis, architecture],
  );
  const travelHandle = {
    x: architecture.pivot_axial_position_m - architecture.required_travel_m,
    r: architecture.pivot_radius_m,
  };

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
    if (tool !== 'select' || viewMode !== 'full') return;
    event.stopPropagation();
    svgRef.current?.setPointerCapture(event.pointerId);
    setDrag({ kind, pointerId: event.pointerId });
  };

  const onPointerMove = (event: React.PointerEvent<SVGSVGElement>) => {
    if (!drag || drag.pointerId !== event.pointerId) return;
    const world = worldFromPointer(event);
    if (!world) return;
    if (drag.kind === 'pivot-radius') {
      onArchitectureChange({ pivot_radius_m: Math.max(0.5e-3, world.r) });
      return;
    }
    if (drag.kind === 'arm') {
      const dx = world.x - architecture.pivot_axial_position_m;
      const dr = world.r - architecture.pivot_radius_m;
      onArchitectureChange({ arm_length_m: Math.max(MIN_ARM_M, Math.hypot(dx, dr)) });
      return;
    }
    onArchitectureChange({
      required_travel_m: Math.max(MIN_TRAVEL_M, architecture.pivot_axial_position_m - world.x),
    });
  };

  const stopDrag = (event: React.PointerEvent<SVGSVGElement>) => {
    if (drag?.pointerId !== event.pointerId) return;
    if (svgRef.current?.hasPointerCapture(event.pointerId)) {
      svgRef.current.releasePointerCapture(event.pointerId);
    }
    setDrag(null);
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

  return (
    <div className={styles.architectureSceneWrap}>
      <div className={styles.architectureToolbar}>
        <div className={styles.toolGroup}>
          <button type="button" className={viewMode === 'full' ? styles.toolActive : styles.toolButton} onClick={() => setViewMode('full')}>
            Full workspace
          </button>
          <button type="button" className={viewMode === 'slice' ? styles.toolActive : styles.toolButton} onClick={() => setViewMode('slice')}>
            Shift slice
          </button>
        </div>
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

      {viewMode === 'slice' && (
        <div className={styles.archSliceControl}>
          <div><strong>Shift slice</strong><span>{(Math.min(sliceShiftM, architecture.required_travel_m) * MM).toFixed(2)} / {(architecture.required_travel_m * MM).toFixed(2)} mm</span></div>
          <input
            type="range"
            min={0}
            max={Math.max(0.001, architecture.required_travel_m * MM)}
            step={0.05}
            value={Math.min(sliceShiftM, architecture.required_travel_m) * MM}
            onChange={(event) => setSliceShiftM(Number(event.target.value) / MM)}
          />
        </div>
      )}

      <svg
        ref={svgRef}
        viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
        role="img"
        aria-label={viewMode === 'full' ? 'Full fixed-pivot architecture workspace' : 'Fixed-pivot architecture shift slice'}
        className={tool === 'draw-zone' ? styles.crosshairCanvas : styles.engineeringCanvas}
        onPointerDown={addDraftPoint}
        onPointerMove={onPointerMove}
        onPointerUp={stopDrag}
        onPointerCancel={stopDrag}
      >
        <rect width={WIDTH} height={HEIGHT} rx="12" fill="var(--primary-design-canvas, #0d1319)" />
        <EngineeringGrid scene={scene} />

        {viewMode === 'full' ? (
          <FullWorkspaceView
            scene={scene}
            architecture={architecture}
            analysis={analysis}
            stale={stale}
          />
        ) : (
          <ShiftSliceView
            scene={scene}
            architecture={architecture}
            analysis={analysis}
            slice={currentSlice}
            stale={stale}
          />
        )}

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

        {draftPoints.length > 0 && (
          <>
            <polyline points={draftPoints.map((point) => `${scene.sx(point.x)},${scene.sy(point.r)}`).join(' ')} className={styles.zoneDraft} />
            {draftPoints.map((point, index) => <circle key={index} cx={scene.sx(point.x)} cy={scene.sy(point.r)} r="4" className={styles.zoneDraftPoint} />)}
          </>
        )}

        {viewMode === 'full' && (
          <>
            <line
              x1={scene.sx(architecture.pivot_axial_position_m)}
              y1={scene.sy(architecture.pivot_radius_m)}
              x2={scene.sx(armEndpoint.x)}
              y2={scene.sy(armEndpoint.r)}
              className={styles.archArm}
              opacity="0.72"
            />
            <circle
              cx={scene.sx(architecture.pivot_axial_position_m)}
              cy={scene.sy(architecture.pivot_radius_m)}
              r="7"
              className={styles.dragPivot}
              onPointerDown={(event) => beginDrag(event, 'pivot-radius')}
            />
            <circle cx={scene.sx(armEndpoint.x)} cy={scene.sy(armEndpoint.r)} r="8" className={styles.dragHandle} onPointerDown={(event) => beginDrag(event, 'arm')} />
            <circle cx={scene.sx(travelHandle.x)} cy={scene.sy(travelHandle.r)} r="8" className={styles.dragHandle} onPointerDown={(event) => beginDrag(event, 'travel')} />
            <text x={scene.sx(architecture.pivot_axial_position_m) + 10} y={scene.sy(architecture.pivot_radius_m) - 10} className={styles.svgLabel}>P₀</text>
            <text x={scene.sx(travelHandle.x) + 10} y={scene.sy(travelHandle.r) + 18} className={styles.svgLabel}>P at full shift</text>
          </>
        )}
      </svg>

      <div className={styles.sceneFooter}>
        {viewMode === 'full' ? (
          <>
            <span><strong>blue</strong> roller-centre workspace</span>
            <span><strong>gold</strong> any positive-tangent ramp surface</span>
            <span><strong>green</strong> ramp workspace after packaging</span>
            <span><strong>flat dashed</strong> q = -30° / 90° limiting ramps</span>
          </>
        ) : (
          <>
            <span><strong>solid arc</strong> roller-centre reach at this shift</span>
            <span><strong>green/red</strong> flyweight poses allowed/blocked by packaging</span>
            <span><strong>gold/green</strong> potential / packaging-feasible ramp surface</span>
          </>
        )}
      </div>
    </div>
  );
}

function FullWorkspaceView({
  scene,
  architecture,
  analysis,
  stale,
}: {
  scene: ReturnType<typeof createScene>;
  architecture: FixedPivotArchitecture;
  analysis: ArchitectureAnalysis | null;
  stale: boolean;
}) {
  if (!analysis) return null;
  const opacity = stale ? 0.22 : 1;
  return (
    <g opacity={opacity}>
      <PolygonSet scene={scene} polygons={analysis.workspace.flyweight_swept} className={styles.flyweightEnvelope} opacity={0.20} />
      <PolygonSet scene={scene} polygons={analysis.workspace.roller_center} className={styles.rollerWorkspace} opacity={0.46} />
      <PolygonSet scene={scene} polygons={analysis.workspace.potential_ramp_surface} className={styles.rampOpportunity} opacity={0.34} />
      <PolygonSet scene={scene} polygons={analysis.workspace.packaging_feasible_ramp_surface} className={styles.rampFeasible} opacity={0.42} />
      <path d={scene.path(analysis.workspace.open_roller_arc.x_m, analysis.workspace.open_roller_arc.r_m)} className={styles.workspaceArc} />
      <path d={scene.path(analysis.workspace.full_shift_roller_arc.x_m, analysis.workspace.full_shift_roller_arc.r_m)} className={styles.workspaceArcGhost} />
      <path d={scene.path(analysis.boundaries.q_min_flat_ramp.x_m, analysis.boundaries.q_min_flat_ramp.r_m)} className={styles.qLimitFlat} />
      <path d={scene.path(analysis.boundaries.q_max_flat_ramp.x_m, analysis.boundaries.q_max_flat_ramp.r_m)} className={styles.qLimitFlat} />
      <path d={scene.path(analysis.boundaries.pivot_travel.x_m, analysis.boundaries.pivot_travel.r_m)} className={styles.travelDimension} />
      <text x={scene.sx(analysis.boundaries.q_min_flat_ramp.x_m[0]) + 8} y={scene.sy(analysis.boundaries.q_min_flat_ramp.r_m[0]) + 18} className={styles.svgLabel}>q = {analysis.limits.q_min_deg.toFixed(0)}° flat limit</text>
      <text x={scene.sx(analysis.boundaries.q_max_flat_ramp.x_m[0]) + 8} y={scene.sy(analysis.boundaries.q_max_flat_ramp.r_m[0]) - 9} className={styles.svgLabel}>q = {analysis.limits.q_max_deg.toFixed(0)}° flat limit</text>
      <line x1={scene.sx(architecture.pivot_axial_position_m)} y1={scene.sy(0)} x2={scene.sx(architecture.pivot_axial_position_m)} y2={scene.sy(architecture.pivot_radius_m)} className={styles.shaftReference} />
      <text x={scene.sx(architecture.pivot_axial_position_m) + 8} y={scene.sy(0) - 7} className={styles.svgLabel}>shaft r = 0</text>
    </g>
  );
}

function ShiftSliceView({
  scene,
  architecture,
  analysis,
  slice,
  stale,
}: {
  scene: ReturnType<typeof createScene>;
  architecture: FixedPivotArchitecture;
  analysis: ArchitectureAnalysis | null;
  slice: ArchitectureSlice | null;
  stale: boolean;
}) {
  if (!analysis || !slice) return null;
  const opacity = stale ? 0.22 : 1;
  const pivotX = slice.pivot_x_m;
  const pivotR = slice.pivot_r_m;
  const qMin = analysis.limits.q_min_deg * Math.PI / 180;
  const qMax = analysis.limits.q_max_deg * Math.PI / 180;
  const qMinEnd = {
    x: pivotX + architecture.arm_length_m * Math.cos(qMin),
    r: pivotR + architecture.arm_length_m * Math.sin(qMin),
  };
  const qMaxEnd = {
    x: pivotX + architecture.arm_length_m * Math.cos(qMax),
    r: pivotR + architecture.arm_length_m * Math.sin(qMax),
  };
  return (
    <g opacity={opacity}>
      <PolygonSet scene={scene} polygons={slice.potential_ramp_surface} className={styles.rampOpportunity} opacity={0.32} />
      <PolygonSet scene={scene} polygons={slice.packaging_feasible_ramp_surface} className={styles.rampFeasible} opacity={0.44} />
      <path d={scene.path(slice.roller_center_x_m, slice.roller_center_r_m)} className={styles.reachBase} />
      {segmentedReach(slice).map((segment, index) => (
        <path key={index} d={scene.path(segment.x, segment.r)} className={segment.ok ? styles.reachAdmissible : styles.reachBlocked} />
      ))}
      <line x1={scene.sx(pivotX)} y1={scene.sy(pivotR)} x2={scene.sx(qMinEnd.x)} y2={scene.sy(qMinEnd.r)} className={styles.archArmBoundary} />
      <line x1={scene.sx(pivotX)} y1={scene.sy(pivotR)} x2={scene.sx(qMaxEnd.x)} y2={scene.sy(qMaxEnd.r)} className={styles.q90Boundary} />
      <circle cx={scene.sx(pivotX)} cy={scene.sy(pivotR)} r="7" className={styles.fixedPivot} />
      <circle cx={scene.sx(qMinEnd.x)} cy={scene.sy(qMinEnd.r)} r={Math.max(3, architecture.roller_radius_m * scene.scale)} className={styles.limitRoller} />
      <circle cx={scene.sx(qMaxEnd.x)} cy={scene.sy(qMaxEnd.r)} r={Math.max(3, architecture.roller_radius_m * scene.scale)} className={styles.limitRoller} />
      <text x={scene.sx(pivotX) + 10} y={scene.sy(pivotR) - 10} className={styles.svgLabel}>P · x = {(slice.shift_m * MM).toFixed(2)} mm</text>
      <text x={scene.sx(qMinEnd.x) + 7} y={scene.sy(qMinEnd.r) + 18} className={styles.svgLabel}>q = {analysis.limits.q_min_deg.toFixed(0)}°</text>
      <text x={scene.sx(qMaxEnd.x) + 7} y={scene.sy(qMaxEnd.r) - 8} className={styles.svgLabel}>q = 90°</text>
    </g>
  );
}

function PolygonSet({
  scene,
  polygons,
  className,
  opacity,
}: {
  scene: ReturnType<typeof createScene>;
  polygons: WorkspacePolygon[];
  className: string;
  opacity?: number;
}) {
  return <>{polygons.map((polygon, index) => <path key={index} d={scene.path(polygon.x_m, polygon.r_m, true)} className={className} opacity={opacity} />)}</>;
}

function segmentedReach(slice: ArchitectureSlice): Array<{ x: number[]; r: number[]; ok: boolean }> {
  const result: Array<{ x: number[]; r: number[]; ok: boolean }> = [];
  if (slice.roller_center_x_m.length < 2) return result;
  let start = 0;
  let state = slice.admissible[0] ?? false;
  for (let index = 1; index < slice.roller_center_x_m.length; index += 1) {
    const next = slice.admissible[index] ?? false;
    if (next === state) continue;
    result.push({
      x: slice.roller_center_x_m.slice(start, index + 1),
      r: slice.roller_center_r_m.slice(start, index + 1),
      ok: state,
    });
    start = Math.max(0, index - 1);
    state = next;
  }
  result.push({
    x: slice.roller_center_x_m.slice(start),
    r: slice.roller_center_r_m.slice(start),
    ok: state,
  });
  return result;
}

function nearestSlice(analysis: ArchitectureAnalysis | null, shiftM: number): ArchitectureSlice | null {
  if (!analysis || analysis.slices.items.length === 0) return null;
  let best = analysis.slices.items[0];
  let bestError = Math.abs(best.shift_m - shiftM);
  for (const item of analysis.slices.items.slice(1)) {
    const error = Math.abs(item.shift_m - shiftM);
    if (error < bestError) {
      best = item;
      bestError = error;
    }
  }
  return best;
}

function EngineeringGrid({ scene }: { scene: ReturnType<typeof createScene> }) {
  const vertical = gridValues(scene.view.x_min_m, scene.view.x_max_m, 0.01);
  const horizontal = gridValues(scene.view.r_min_m, scene.view.r_max_m, 0.01);
  return (
    <g className={styles.engineeringGrid}>
      {vertical.map((x) => <line key={`gx-${x}`} x1={scene.sx(x)} y1={PAD} x2={scene.sx(x)} y2={HEIGHT - PAD} />)}
      {horizontal.map((r) => <line key={`gr-${r}`} x1={PAD} y1={scene.sy(r)} x2={WIDTH - PAD} y2={scene.sy(r)} />)}
    </g>
  );
}

function gridValues(min: number, max: number, step: number): number[] {
  const first = Math.ceil(min / step) * step;
  const values: number[] = [];
  for (let value = first; value <= max + 1e-12; value += step) values.push(value);
  return values;
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
  return { view, sx, sy, world, path, scale };
}
