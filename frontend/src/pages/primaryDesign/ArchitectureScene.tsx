import { useMemo, useRef, useState } from 'react';
import type {
  ArchitectureAnalysis,
  FixedPivotArchitecture,
  PackagingZone,
  PackagingZoneRule,
  PackagingZoneSubject,
  PrimaryPathDomainAnalysis,
  WorkspacePolygon,
} from '@api/primaryDesign';
import styles from './PrimaryDesign.module.scss';

const WIDTH = 1040;
const HEIGHT = 640;
const PAD = 34;
const MIN_ARM_M = 2e-3;
const MIN_TRAVEL_M = 0.5e-3;

type DrawTool = 'select' | 'draw-zone';
type DragKind = 'pivot-radius' | 'arm-radius' | 'roller-radius' | 'travel';

interface WorldPoint {
  x: number;
  r: number;
}

interface DragState {
  kind: DragKind;
  pointerId: number;
  shiftM?: number;
}

interface ArchitectureSceneProps {
  architecture: FixedPivotArchitecture;
  analysis: ArchitectureAnalysis | null;
  pathDomain?: PrimaryPathDomainAnalysis | null;
  comparisonBaseline?: PrimaryPathDomainAnalysis | null;
  showLocalWorkspace?: boolean;
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
  pathDomain = null,
  comparisonBaseline = null,
  showLocalWorkspace = false,
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
  const [drag, setDrag] = useState<DragState | null>(null);

  const qMinDeg = analysis?.limits.q_min_deg ?? -30;
  const qMaxDeg = analysis?.limits.q_max_deg ?? 90;

  const draftOpenArc = useMemo(
    () => rollerArc(architecture, 0, qMinDeg, qMaxDeg),
    [architecture, qMinDeg, qMaxDeg],
  );
  const draftFullArc = useMemo(
    () => rollerArc(architecture, architecture.required_travel_m, qMinDeg, qMaxDeg),
    [architecture, qMinDeg, qMaxDeg],
  );

  const openRollerEnvelope = useMemo(
    () => rollerEnvelope(architecture, 0, qMinDeg, qMaxDeg),
    [architecture, qMinDeg, qMaxDeg],
  );
  const fullRollerEnvelope = useMemo(
    () => rollerEnvelope(architecture, architecture.required_travel_m, qMinDeg, qMaxDeg),
    [architecture, qMinDeg, qMaxDeg],
  );

  const view = useMemo(() => {
    const draftXs = [...draftOpenArc.x_m, ...draftFullArc.x_m];
    const draftRs = [...draftOpenArc.r_m, ...draftFullArc.r_m];
    const fallback = {
      x_min_m: Math.min(...draftXs) - architecture.roller_radius_m - 0.02,
      x_max_m: Math.max(...draftXs) + architecture.roller_radius_m + 0.02,
      r_min_m: Math.max(0, Math.min(...draftRs) - architecture.roller_radius_m - 0.02),
      r_max_m: Math.max(...draftRs) + architecture.roller_radius_m + 0.02,
    };
    const xCandidates = [fallback.x_min_m, fallback.x_max_m];
    const rCandidates = [fallback.r_min_m, fallback.r_max_m];
    if (analysis) {
      xCandidates.push(analysis.viewport.x_min_m, analysis.viewport.x_max_m);
      rCandidates.push(analysis.viewport.r_min_m, analysis.viewport.r_max_m);
    }
    if (pathDomain) {
      xCandidates.push(...pathDomain.domain_projection.ramp_surface_points.x_m);
      rCandidates.push(...pathDomain.domain_projection.ramp_surface_points.r_m);
    }
    if (comparisonBaseline) {
      xCandidates.push(...comparisonBaseline.domain_projection.ramp_surface_points.x_m);
      rCandidates.push(...comparisonBaseline.domain_projection.ramp_surface_points.r_m);
    }
    return {
      x_min_m: Math.min(...xCandidates),
      x_max_m: Math.max(...xCandidates),
      r_min_m: Math.max(0, Math.min(...rCandidates)),
      r_max_m: Math.max(...rCandidates),
    };
  }, [analysis, architecture.roller_radius_m, draftOpenArc, draftFullArc, pathDomain, comparisonBaseline]);

  const scene = useMemo(() => createScene(view), [view]);
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

  const beginDrag = (
    event: React.PointerEvent<SVGElement>,
    kind: DragKind,
    shiftM?: number,
  ) => {
    if (tool !== 'select') return;
    event.stopPropagation();
    svgRef.current?.setPointerCapture(event.pointerId);
    setDrag({ kind, pointerId: event.pointerId, shiftM });
  };

  const onPointerMove = (event: React.PointerEvent<SVGSVGElement>) => {
    if (!drag || drag.pointerId !== event.pointerId) return;
    const world = worldFromPointer(event);
    if (!world) return;

    if (drag.kind === 'pivot-radius') {
      onArchitectureChange({ pivot_radius_m: Math.max(0.5e-3, world.r) });
      return;
    }

    if (drag.kind === 'arm-radius') {
      const shift = drag.shiftM ?? 0;
      const pivotX = architecture.pivot_axial_position_m - shift;
      const dx = world.x - pivotX;
      const dr = world.r - architecture.pivot_radius_m;
      onArchitectureChange({ arm_length_m: Math.max(MIN_ARM_M, Math.hypot(dx, dr)) });
      return;
    }

    if (drag.kind === 'roller-radius') {
      const shift = drag.shiftM ?? 0;
      const pivotX = architecture.pivot_axial_position_m - shift;
      const dx = world.x - pivotX;
      const dr = world.r - architecture.pivot_radius_m;
      const radialDistance = Math.hypot(dx, dr);
      const requestedRadius = radialDistance - architecture.arm_length_m;
      onArchitectureChange({
        roller_radius_m: Math.max(0.5e-3, Math.min(0.95 * architecture.arm_length_m, requestedRadius)),
      });
      return;
    }

    onArchitectureChange({
      required_travel_m: Math.max(
        MIN_TRAVEL_M,
        architecture.pivot_axial_position_m - world.x,
      ),
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

  const openArcPath = scene.path(draftOpenArc.x_m, draftOpenArc.r_m);
  const fullArcPath = scene.path(draftFullArc.x_m, draftFullArc.r_m);
  const openInnerPath = scene.path(openRollerEnvelope.inner.x_m, openRollerEnvelope.inner.r_m);
  const openOuterPath = scene.path(openRollerEnvelope.outer.x_m, openRollerEnvelope.outer.r_m);
  const fullInnerPath = scene.path(fullRollerEnvelope.inner.x_m, fullRollerEnvelope.inner.r_m);
  const fullOuterPath = scene.path(fullRollerEnvelope.outer.x_m, fullRollerEnvelope.outer.r_m);
  const openQMaxCenter = pointAtAngle(architecture, 0, qMaxDeg, architecture.arm_length_m);
  const rollerRadiusPx = architecture.roller_radius_m * scene.scale;

  return (
    <div className={styles.architectureSceneWrap}>
      <div className={styles.architectureToolbar}>
        <div className={styles.toolGroup}>
          <button
            type="button"
            className={tool === 'select' ? styles.toolActive : styles.toolButton}
            onClick={() => { setTool('select'); setDraftPoints([]); }}
          >
            Select / move
          </button>
          <button
            type="button"
            className={tool === 'draw-zone' ? styles.toolActive : styles.toolButton}
            onClick={() => setTool('draw-zone')}
          >
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
        aria-label="Full fixed-pivot architecture workspace"
        className={tool === 'draw-zone' ? styles.crosshairCanvas : styles.engineeringCanvas}
        onPointerDown={addDraftPoint}
        onPointerMove={onPointerMove}
        onPointerUp={stopDrag}
        onPointerCancel={stopDrag}
      >
        <rect width={WIDTH} height={HEIGHT} rx="12" fill="var(--primary-design-canvas, #0d1319)" />
        <EngineeringGrid scene={scene} />

        <FullWorkspaceView
          scene={scene}
          architecture={architecture}
          analysis={analysis}
          stale={stale}
          showLocalRampWorkspace={showLocalWorkspace || !pathDomain}
          ghostLocalRampWorkspace={Boolean(pathDomain)}
        />

        {comparisonBaseline && (
          <DomainProjectionView
            scene={scene}
            pathDomain={comparisonBaseline}
            stale={false}
            baseline
          />
        )}

        {pathDomain && (
          <DomainProjectionView
            scene={scene}
            pathDomain={pathDomain}
            stale={stale}
          />
        )}

        {/* Finite roller sweep: exact tube around the roller-centre loci. */}
        <g pointerEvents="none">
          <path
            d={openArcPath}
            className={styles.rollerSweepBand}
            style={{ strokeWidth: Math.max(1, 2 * rollerRadiusPx) }}
          />
          <path
            d={fullArcPath}
            className={styles.rollerSweepBandGhost}
            style={{ strokeWidth: Math.max(1, 2 * rollerRadiusPx) }}
          />
          <path d={openInnerPath} className={styles.rollerRadiusBoundary} />
          <path d={openOuterPath} className={styles.rollerRadiusBoundary} />
          <path d={fullInnerPath} className={styles.rollerRadiusBoundaryGhost} />
          <path d={fullOuterPath} className={styles.rollerRadiusBoundaryGhost} />

          <circle
            cx={scene.sx(openQMaxCenter.x)}
            cy={scene.sy(openQMaxCenter.r)}
            r={rollerRadiusPx}
            className={styles.representativeRoller}
          />
          <line
            x1={scene.sx(openQMaxCenter.x)}
            y1={scene.sy(openQMaxCenter.r)}
            x2={scene.sx(openQMaxCenter.x)}
            y2={scene.sy(openQMaxCenter.r + architecture.roller_radius_m)}
            className={styles.rollerRadiusDimension}
          />
          <text
            x={scene.sx(openQMaxCenter.x) + 9}
            y={scene.sy(openQMaxCenter.r + 0.52 * architecture.roller_radius_m)}
            className={styles.svgLabel}
          >
            Rᵣ = {(architecture.roller_radius_m * 1000).toFixed(2)} mm
          </text>
        </g>

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

        {/* Live architecture manipulators. Centre arcs set arm length; outer envelope arcs set roller radius. */}
        <path d={openArcPath} className={styles.workspaceArcDraft} />
        <path d={fullArcPath} className={styles.workspaceArcDraftGhost} />
        {tool === 'select' && (
          <>
            <path d={openArcPath} className={styles.arcDragTarget} onPointerDown={(event) => beginDrag(event, 'arm-radius', 0)} />
            <path d={fullArcPath} className={styles.arcDragTarget} onPointerDown={(event) => beginDrag(event, 'arm-radius', architecture.required_travel_m)} />
            <path d={openOuterPath} className={styles.rollerRadiusDragTarget} onPointerDown={(event) => beginDrag(event, 'roller-radius', 0)} />
            <path d={fullOuterPath} className={styles.rollerRadiusDragTarget} onPointerDown={(event) => beginDrag(event, 'roller-radius', architecture.required_travel_m)} />
          </>
        )}

        <circle
          cx={scene.sx(architecture.pivot_axial_position_m)}
          cy={scene.sy(architecture.pivot_radius_m)}
          r="7"
          className={styles.dragPivot}
          onPointerDown={(event) => beginDrag(event, 'pivot-radius')}
        />
        <circle
          cx={scene.sx(travelHandle.x)}
          cy={scene.sy(travelHandle.r)}
          r="8"
          className={styles.dragHandle}
          onPointerDown={(event) => beginDrag(event, 'travel')}
        />
        <text x={scene.sx(architecture.pivot_axial_position_m) + 10} y={scene.sy(architecture.pivot_radius_m) - 10} className={styles.svgLabel}>P₀</text>
        <text x={scene.sx(travelHandle.x) + 10} y={scene.sy(travelHandle.r) + 18} className={styles.svgLabel}>P at full shift</text>
      </svg>

      <div className={styles.sceneFooter}>
        <span><strong>blue</strong> full roller-centre workspace</span>
        <span><strong>dotted centre arcs</strong> draggable arm length</span>
        <span><strong>dashed roller edges + faint band</strong> finite roller radius; drag outer edge to resize</span>
        <span><strong>gold</strong> any positive-tangent ramp surface</span>
        <span><strong>green cloud</strong> current complete-path-viable physical ramp states</span>
        {comparisonBaseline && <span><strong>blue cloud</strong> pinned baseline domain</span>}
        <span><strong>gold / pale green</strong> optional Phase-2 local geometric superset</span>
        <span><strong>flat dashed</strong> q = -30° / 90° limiting ramps</span>
      </div>
    </div>
  );
}

function FullWorkspaceView({
  scene,
  architecture,
  analysis,
  stale,
  showLocalRampWorkspace,
  ghostLocalRampWorkspace = false,
}: {
  scene: ReturnType<typeof createScene>;
  architecture: FixedPivotArchitecture;
  analysis: ArchitectureAnalysis | null;
  stale: boolean;
  showLocalRampWorkspace: boolean;
  ghostLocalRampWorkspace?: boolean;
}) {
  if (!analysis) return null;
  const baseOpacity = stale ? 0.20 : 1;
  const localOpacity = stale ? 0.12 : ghostLocalRampWorkspace ? 0.25 : 1;
  return (
    <g>
      <g opacity={baseOpacity}>
        <PolygonSet scene={scene} polygons={analysis.workspace.roller_center} className={styles.rollerWorkspace} opacity={0.38} />
      </g>
      {showLocalRampWorkspace && (
        <g opacity={localOpacity}>
          <PolygonSet scene={scene} polygons={analysis.workspace.potential_ramp_surface} className={styles.rampOpportunity} opacity={0.30} />
          <PolygonSet scene={scene} polygons={analysis.workspace.packaging_feasible_ramp_surface} className={styles.rampFeasible} opacity={0.38} />
        </g>
      )}
      <g opacity={baseOpacity}>
      <path d={scene.path(analysis.boundaries.q_min_flat_ramp.x_m, analysis.boundaries.q_min_flat_ramp.r_m)} className={styles.qLimitFlat} />
      <path d={scene.path(analysis.boundaries.q_max_flat_ramp.x_m, analysis.boundaries.q_max_flat_ramp.r_m)} className={styles.qLimitFlat} />
      <path d={scene.path(analysis.boundaries.pivot_travel.x_m, analysis.boundaries.pivot_travel.r_m)} className={styles.travelDimension} />
      <text x={scene.sx(analysis.boundaries.q_min_flat_ramp.x_m[0]) + 8} y={scene.sy(analysis.boundaries.q_min_flat_ramp.r_m[0]) + 18} className={styles.svgLabel}>q = {analysis.limits.q_min_deg.toFixed(0)}° flat limit</text>
      <text x={scene.sx(analysis.boundaries.q_max_flat_ramp.x_m[0]) + 8} y={scene.sy(analysis.boundaries.q_max_flat_ramp.r_m[0]) - 9} className={styles.svgLabel}>q = {analysis.limits.q_max_deg.toFixed(0)}° flat limit</text>
        <line x1={scene.sx(architecture.pivot_axial_position_m)} y1={scene.sy(0)} x2={scene.sx(architecture.pivot_axial_position_m)} y2={scene.sy(architecture.pivot_radius_m)} className={styles.shaftReference} />
        <text x={scene.sx(architecture.pivot_axial_position_m) + 8} y={scene.sy(0) - 7} className={styles.svgLabel}>shaft r = 0</text>
      </g>
    </g>
  );
}

function DomainProjectionView({
  scene,
  pathDomain,
  stale,
  baseline = false,
}: {
  scene: ReturnType<typeof createScene>;
  pathDomain: PrimaryPathDomainAnalysis;
  stale: boolean;
  baseline?: boolean;
}) {
  const points = pathDomain.domain_projection.ramp_surface_points;
  const radiusPx = Math.max(1.8, pathDomain.domain_projection.visual_radius_m * scene.scale);
  return (
    <g opacity={stale ? 0.24 : 1} pointerEvents="none">
      {points.x_m.map((x, index) => (
        <circle
          key={`${points.station[index]}-${index}`}
          cx={scene.sx(x)}
          cy={scene.sy(points.r_m[index])}
          r={radiusPx}
          className={baseline ? styles.domainBaselinePoint : styles.domainViablePoint}
        />
      ))}
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

function rollerArc(
  architecture: FixedPivotArchitecture,
  shiftM: number,
  qMinDeg: number,
  qMaxDeg: number,
  radiusM = architecture.arm_length_m,
): { x_m: number[]; r_m: number[] } {
  const count = 241;
  const pivotX = architecture.pivot_axial_position_m - shiftM;
  const qMin = qMinDeg * Math.PI / 180;
  const qMax = qMaxDeg * Math.PI / 180;
  const x_m: number[] = [];
  const r_m: number[] = [];
  for (let index = 0; index < count; index += 1) {
    const fraction = index / (count - 1);
    const q = qMin + fraction * (qMax - qMin);
    x_m.push(pivotX + radiusM * Math.cos(q));
    r_m.push(architecture.pivot_radius_m + radiusM * Math.sin(q));
  }
  return { x_m, r_m };
}

function rollerEnvelope(
  architecture: FixedPivotArchitecture,
  shiftM: number,
  qMinDeg: number,
  qMaxDeg: number,
): { inner: { x_m: number[]; r_m: number[] }; outer: { x_m: number[]; r_m: number[] } } {
  const innerRadius = Math.max(1e-6, architecture.arm_length_m - architecture.roller_radius_m);
  const outerRadius = architecture.arm_length_m + architecture.roller_radius_m;
  return {
    inner: rollerArc(architecture, shiftM, qMinDeg, qMaxDeg, innerRadius),
    outer: rollerArc(architecture, shiftM, qMinDeg, qMaxDeg, outerRadius),
  };
}

function pointAtAngle(
  architecture: FixedPivotArchitecture,
  shiftM: number,
  qDeg: number,
  radiusM: number,
): WorldPoint {
  const q = qDeg * Math.PI / 180;
  const pivotX = architecture.pivot_axial_position_m - shiftM;
  return {
    x: pivotX + radiusM * Math.cos(q),
    r: architecture.pivot_radius_m + radiusM * Math.sin(q),
  };
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
