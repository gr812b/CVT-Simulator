import { useEffect, useMemo, useRef, useState } from 'react';
import {
  inverseDesignPrimaryForceCurve,
  type FixedPivotArchitecture,
  type InverseDesignAnalysis,
  type InverseDesignTargetPoint,
  type InverseRampSolution,
  type PackagingZone,
  type PrimaryPathDomainAnalysis,
} from '@api/primaryDesign';
import styles from './ForceInverseDesigner.module.scss';

const MM = 1000;
const G = 1000;
const RAD_S_PER_RPM = 2 * Math.PI / 60;

type DragState = { index: number; pointerId: number } | null;
type Range = { min: number; max: number };

export function ForceInverseDesigner({
  architecture,
  zones,
  domain,
}: {
  architecture: FixedPivotArchitecture;
  zones: PackagingZone[];
  domain: PrimaryPathDomainAnalysis | null;
}) {
  const [rpm, setRpm] = useState(3800);
  const [massMode, setMassMode] = useState<'free' | 'fixed'>('free');
  const [massKg, setMassKg] = useState(Math.min(0.250, architecture.max_tip_mass_per_flyweight_kg));
  const [maxMassKg, setMaxMassKg] = useState(Math.min(0.350, architecture.max_tip_mass_per_flyweight_kg));
  const [points, setPoints] = useState<InverseDesignTargetPoint[]>(() => initialTarget(architecture, 3800));
  const [result, setResult] = useState<InverseDesignAnalysis | null>(null);
  const [selectedIndex, setSelectedIndex] = useState(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [drag, setDrag] = useState<DragState>(null);
  const [yRange, setYRange] = useState<Range | null>(null);
  const [inspectionShiftM, setInspectionShiftM] = useState(0);
  const svgRef = useRef<SVGSVGElement | null>(null);

  useEffect(() => {
    setPoints(initialTarget(architecture, rpm));
    setResult(null);
    setSelectedIndex(0);
    setYRange(null);
    setInspectionShiftM(0);
  }, [architecture.pivot_radius_m, architecture.arm_length_m, architecture.roller_radius_m, architecture.required_travel_m]);

  const selected = result?.solutions[selectedIndex] ?? null;
  useEffect(() => {
    if (!selected) {
      setInspectionShiftM(0);
      return;
    }
    setInspectionShiftM((value) => clamp(value, selected.shift_m[0] ?? 0, selected.shift_m[selected.shift_m.length - 1] ?? architecture.required_travel_m));
  }, [selectedIndex, selected, architecture.required_travel_m]);
  const inspectedForce = selected ? interpolateSeries(selected.shift_m, selected.force.recovered_N, inspectionShiftM) : null;
  const inspectedTarget = selected ? interpolateSeries(selected.shift_m, selected.force.target_N, inspectionShiftM) : null;
  const capability = useMemo(() => contextualCapability(domain, rpm), [domain, rpm]);
  const targetCurve = useMemo(() => sampleMonotone(points, architecture.required_travel_m, 181), [points, architecture.required_travel_m]);
  const autoRange = useMemo(() => forceRange(capability, targetCurve.force_N, selected?.force.recovered_N ?? []), [capability, targetCurve, selected]);
  const activeRange = yRange ?? autoRange;

  const run = async () => {
    if (points.length === 0) return;
    setLoading(true);
    setError(null);
    try {
      const next = await inverseDesignPrimaryForceCurve(
        architecture,
        zones,
        points,
        rpm * RAD_S_PER_RPM,
        massMode === 'free' ? maxMassKg : massKg,
        massMode === 'fixed' ? massKg : null,
        { solution_count: 8, sample_count: 181 },
      );
      setResult(next);
      setSelectedIndex(0);
      setYRange(null);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Continuous inverse design failed.');
    } finally {
      setLoading(false);
    }
  };

  const width = 980;
  const height = 450;
  const pad = { left: 72, right: 22, top: 22, bottom: 50 };
  const xScale = (x: number) => pad.left + (x / architecture.required_travel_m) * (width - pad.left - pad.right);
  const yScale = (force: number) => pad.top + (activeRange.max - force) / Math.max(activeRange.max - activeRange.min, 1) * (height - pad.top - pad.bottom);
  const xInvert = (x: number) => clamp((x - pad.left) / (width - pad.left - pad.right) * architecture.required_travel_m, 0, architecture.required_travel_m);
  const yInvert = (y: number) => activeRange.max - (y - pad.top) / (height - pad.top - pad.bottom) * (activeRange.max - activeRange.min);

  const localPoint = (clientX: number, clientY: number) => {
    const svg = svgRef.current;
    const matrix = svg?.getScreenCTM();
    if (!svg || !matrix) return null;
    const p = svg.createSVGPoint();
    p.x = clientX;
    p.y = clientY;
    const local = p.matrixTransform(matrix.inverse());
    return { x: local.x, y: local.y };
  };

  const addPoint = (event: React.PointerEvent<SVGSVGElement>) => {
    if (drag) return;
    const p = localPoint(event.clientX, event.clientY);
    if (!p || p.x < pad.left || p.x > width - pad.right || p.y < pad.top || p.y > height - pad.bottom) return;
    const next = [...points, { shift_m: xInvert(p.x), force_N: Math.max(0, yInvert(p.y)) }]
      .sort((a, b) => a.shift_m - b.shift_m);
    setPoints(next);
    setResult(null);
  };

  const beginDrag = (event: React.PointerEvent<SVGCircleElement>, index: number) => {
    event.stopPropagation();
    svgRef.current?.setPointerCapture(event.pointerId);
    setDrag({ index, pointerId: event.pointerId });
  };

  const moveDrag = (event: React.PointerEvent<SVGSVGElement>) => {
    if (!drag || drag.pointerId !== event.pointerId) return;
    const p = localPoint(event.clientX, event.clientY);
    if (!p) return;
    setPoints((rows) => rows.map((row, index) => index === drag.index
      ? { shift_m: xInvert(p.x), force_N: Math.max(0, yInvert(p.y)) }
      : row));
    setResult(null);
  };

  const endDrag = (event: React.PointerEvent<SVGSVGElement>) => {
    if (!drag || drag.pointerId !== event.pointerId) return;
    if (svgRef.current?.hasPointerCapture(event.pointerId)) svgRef.current.releasePointerCapture(event.pointerId);
    setPoints((rows) => [...rows].sort((a, b) => a.shift_m - b.shift_m));
    setDrag(null);
  };

  const wheel = (event: React.WheelEvent<SVGSVGElement>) => {
    event.preventDefault();
    const p = localPoint(event.clientX, event.clientY);
    if (!p) return;
    const range = yRange ?? autoRange;
    const span = Math.max(50, range.max - range.min);
    if (event.shiftKey) {
      const shift = event.deltaY / 700 * span;
      setYRange({ min: Math.max(0, range.min + shift), max: Math.max(range.min + 50, range.max + shift) });
      return;
    }
    const anchor = clamp(yInvert(p.y), range.min, range.max);
    const factor = event.deltaY > 0 ? 1.18 : 0.84;
    const nextSpan = clamp(span * factor, 150, Math.max(50000, autoRange.max * 4));
    const fraction = (anchor - range.min) / span;
    let min = anchor - fraction * nextSpan;
    let max = min + nextSpan;
    if (min < 0) { max -= min; min = 0; }
    setYRange({ min, max });
  };

  const gridForces = niceTicks(activeRange.min, activeRange.max, 6);
  const gridShift = Array.from({ length: 6 }, (_, index) => architecture.required_travel_m * index / 5);

  return (
    <div className={styles.root}>
      <div className={styles.controls}>
        <div>
          <strong>Continuous force → ramp inverse</strong>
          <p>Draw the flyweight closing-force curve you want. Nothing is filtered while you draw; the backend generates the finite-roller ramp directly from the Appendix-D mechanics when you ask for solutions.</p>
        </div>
        <label><span>Primary speed</span><div><input type="number" value={rpm} min={100} max={7000} step={25} onChange={(event) => { setRpm(Number(event.target.value)); setResult(null); setYRange(null); }} /><em>rpm</em></div></label>
        <label><span>Tip mass</span><select value={massMode} onChange={(event) => { setMassMode(event.target.value as 'free' | 'fixed'); setResult(null); }}><option value="free">Solve mass</option><option value="fixed">Fix mass</option></select></label>
        {massMode === 'free' ? (
          <label><span>Maximum tip mass</span><div><input type="number" value={(maxMassKg * G).toFixed(0)} min={0} max={architecture.max_tip_mass_per_flyweight_kg * G} step={5} onChange={(event) => { setMaxMassKg(Number(event.target.value) / G); setResult(null); }} /><em>g / flyweight</em></div></label>
        ) : (
          <label><span>Fixed tip mass</span><div><input type="number" value={(massKg * G).toFixed(0)} min={0} max={architecture.max_tip_mass_per_flyweight_kg * G} step={5} onChange={(event) => { setMassKg(Number(event.target.value) / G); setResult(null); }} /><em>g / flyweight</em></div></label>
        )}
        <button type="button" className={styles.generate} disabled={loading || points.length === 0} onClick={() => void run()}>{loading ? 'Generating physical ramps…' : 'Generate physical ramps'}</button>
      </div>

      {error && <div className={styles.error}>{error}</div>}

      <div className={styles.plotCard}>
        <div className={styles.plotHeader}>
          <div><strong>Desired static flyweight closing force</strong><span>Click to add · drag handles · double-click a handle to remove · wheel zoom Y · Shift+wheel pan Y</span></div>
          <div className={styles.plotActions}><button type="button" onClick={() => setYRange(null)}>Fit Y</button><button type="button" onClick={() => { setPoints([]); setResult(null); }}>Clear</button></div>
        </div>
        <svg ref={svgRef} className={styles.forcePlot} viewBox={`0 0 ${width} ${height}`} onPointerDown={addPoint} onPointerMove={moveDrag} onPointerUp={endDrag} onPointerCancel={endDrag} onWheel={wheel}>
          <rect x={pad.left} y={pad.top} width={width - pad.left - pad.right} height={height - pad.top - pad.bottom} className={styles.plotBackground} />
          {gridForces.map((force) => <g key={force}><line x1={pad.left} x2={width - pad.right} y1={yScale(force)} y2={yScale(force)} className={styles.grid} /><text x={pad.left - 10} y={yScale(force) + 4} textAnchor="end" className={styles.axisText}>{Math.round(force).toLocaleString()}</text></g>)}
          {gridShift.map((shift) => <g key={shift}><line x1={xScale(shift)} x2={xScale(shift)} y1={pad.top} y2={height - pad.bottom} className={styles.grid} /><text x={xScale(shift)} y={height - 18} textAnchor="middle" className={styles.axisText}>{(shift * MM).toFixed(1)}</text></g>)}
          <text transform={`translate(18 ${(pad.top + height - pad.bottom) / 2}) rotate(-90)`} textAnchor="middle" className={styles.axisTitle}>Closing force (N)</text>
          <text x={(pad.left + width - pad.right) / 2} y={height - 2} textAnchor="middle" className={styles.axisTitle}>Primary closure (mm)</text>
          {capability && <path d={areaPath(capability.shift_m, capability.min_N, capability.max_N, xScale, yScale)} className={styles.capabilityBand} />}
          <path d={linePath(targetCurve.shift_m, targetCurve.force_N, xScale, yScale)} className={styles.targetLine} />
          {result?.solutions.map((solution, index) => index === selectedIndex ? null : (
            <path key={`candidate-${index}`} d={linePath(solution.shift_m, solution.force.recovered_N, xScale, yScale)} className={styles.solutionCandidateLine} />
          ))}
          {selected && <path d={linePath(selected.shift_m, selected.force.recovered_N, xScale, yScale)} className={styles.solutionLine} />}
          {selected && (
            <>
              <line x1={xScale(inspectionShiftM)} x2={xScale(inspectionShiftM)} y1={pad.top} y2={height - pad.bottom} className={styles.inspectionCursor} />
              {inspectedForce != null && <circle cx={xScale(inspectionShiftM)} cy={yScale(inspectedForce)} r={5.5} className={styles.solutionCursor} />}
              {inspectedTarget != null && <circle cx={xScale(inspectionShiftM)} cy={yScale(inspectedTarget)} r={4.5} className={styles.targetCursor} />}
            </>
          )}
          {points.map((point, index) => <circle key={`${point.shift_m}-${index}`} cx={xScale(point.shift_m)} cy={yScale(point.force_N)} r={7} className={styles.handle} onPointerDown={(event) => beginDrag(event, index)} onDoubleClick={(event) => { event.stopPropagation(); setPoints((rows) => rows.filter((_, rowIndex) => rowIndex !== index)); setResult(null); }} />)}
        </svg>
        <div className={styles.legend}><span className={styles.legendTarget}>requested force</span>{result && result.solutions.length > 1 && <span className={styles.legendCandidates}>other generated ramps</span>}{selected && <span className={styles.legendSolution}>selected ramp · actual generated force</span>}{capability && <span className={styles.legendCapability}>architecture context only</span>}{selected && inspectedForce != null && inspectedTarget != null && <strong className={styles.cursorReadout}>{(inspectionShiftM * MM).toFixed(2)} mm · actual {inspectedForce.toFixed(0)} N · target {inspectedTarget.toFixed(0)} N</strong>}</div>
      </div>

      {result && (
        <>
          <div className={styles.summary}>
            <Metric label="Certified ramps" value={String(result.summary.certified_solution_count)} />
            <Metric label="Best RMS error" value={result.summary.best_rms_error_N == null ? '—' : `${result.summary.best_rms_error_N.toFixed(1)} N`} />
            <Metric label="Best max error" value={result.summary.best_max_error_N == null ? '—' : `${result.summary.best_max_error_N.toFixed(1)} N`} />
            <Metric label="Target force area" value={`${result.summary.target_integrated_force_Nm.toFixed(2)} N·m`} />
          </div>

          {result.solutions.length > 0 && (
            <div className={styles.solutionsSection}>
              <div className={styles.solutionStrip}>
                {result.solutions.map((solution, index) => <SolutionCard key={index} solution={solution} index={index} selected={index === selectedIndex} onClick={() => setSelectedIndex(index)} />)}
              </div>
              {selected && <RampInspector architecture={architecture} solution={selected} shiftM={inspectionShiftM} onShiftChange={setInspectionShiftM} />}
            </div>
          )}

          {result.diagnostics.length > 0 && (
            <div className={styles.diagnostics}>
              <strong>{result.solutions.length ? 'Boundaries encountered by rejected alternatives' : 'Why the requested curve did not produce an admissible ramp'}</strong>
              {result.diagnostics.slice(0, 8).map((item, index) => <div key={`${item.code}-${index}`}><span>{item.code}</span><p>{item.message}</p>{item.shift_m != null && <em>near {(item.shift_m * MM).toFixed(2)} mm</em>}</div>)}
            </div>
          )}
        </>
      )}
    </div>
  );
}

function SolutionCard({ solution, index, selected, onClick }: { solution: InverseRampSolution; index: number; selected: boolean; onClick: () => void }) {
  return <button type="button" className={selected ? styles.solutionCardSelected : styles.solutionCard} onClick={onClick}>
    <strong>Ramp {index + 1}</strong>
    <span>{(solution.tip_mass_per_flyweight_kg * G).toFixed(1)} g · q₀ {solution.initial_q_deg.toFixed(1)}°</span>
    <em>RMS {solution.metrics.rms_force_error_N.toFixed(1)} N · max {solution.metrics.max_force_error_N.toFixed(1)} N</em>
  </button>;
}

function RampInspector({
  architecture,
  solution,
  shiftM,
  onShiftChange,
}: {
  architecture: FixedPivotArchitecture;
  solution: InverseRampSolution;
  shiftM: number;
  onShiftChange: (value: number) => void;
}) {
  const width = 820;
  const height = 360;
  const currentQ = interpolateSeries(solution.shift_m, solution.q_deg, shiftM);
  const currentTangent = interpolateSeries(solution.shift_m, solution.ramp_tangent_deg, shiftM);
  const currentForce = interpolateSeries(solution.shift_m, solution.force.recovered_N, shiftM);
  const currentTarget = interpolateSeries(solution.shift_m, solution.force.target_N, shiftM);
  const currentRollerX = interpolateSeries(solution.shift_m, solution.roller_center.x_m, shiftM);
  const currentRollerR = interpolateSeries(solution.shift_m, solution.roller_center.r_m, shiftM);
  const currentContactX = interpolateSeries(solution.shift_m, solution.ramp_surface.x_m, shiftM);
  const currentContactR = interpolateSeries(solution.shift_m, solution.ramp_surface.r_m, shiftM);
  const currentPivotX = architecture.pivot_axial_position_m - shiftM;
  const currentPivotR = architecture.pivot_radius_m;

  const pivotStartX = architecture.pivot_axial_position_m;
  const pivotEndX = architecture.pivot_axial_position_m - architecture.required_travel_m;
  const allX = [
    ...solution.ramp_surface.x_m,
    ...solution.roller_center.x_m,
    pivotStartX,
    pivotEndX,
  ];
  const allR = [
    ...solution.ramp_surface.r_m,
    ...solution.roller_center.r_m,
    currentPivotR - architecture.roller_radius_m,
    currentPivotR + architecture.arm_length_m + architecture.roller_radius_m,
  ];
  const minX = Math.min(...allX); const maxX = Math.max(...allX);
  const minR = Math.min(...allR); const maxR = Math.max(...allR);
  const pad = 34;
  const scale = Math.min((width - 2 * pad) / Math.max(maxX - minX, 1e-4), (height - 2 * pad) / Math.max(maxR - minR, 1e-4));
  const x = (value: number) => pad + (value - minX) * scale;
  const y = (value: number) => height - pad - (value - minR) * scale;
  const rollerRadiusPx = Math.max(4, architecture.roller_radius_m * scale);

  return <div className={styles.inspector}>
    <div className={styles.inspectorHeader}>
      <div>
        <strong>Selected ramp · mechanism through shift</strong>
        <span>Ramp is fixed in the movable-sheave frame; scrub closure to move the pivot, arm and finite roller through the generated contact path.</span>
      </div>
      <div className={styles.inspectorForce}>{currentForce == null ? '—' : `${currentForce.toFixed(0)} N`} <span>actual</span></div>
    </div>
    <ForceMatchPlot solution={solution} shiftM={shiftM} onShiftChange={onShiftChange} />
    <div className={styles.scrubber}>
      <input
        type="range"
        min={0}
        max={architecture.required_travel_m * MM}
        step={0.02}
        value={shiftM * MM}
        onChange={(event) => onShiftChange(Number(event.target.value) / MM)}
      />
      <strong>{(shiftM * MM).toFixed(2)} / {(architecture.required_travel_m * MM).toFixed(2)} mm</strong>
    </div>
    <svg viewBox={`0 0 ${width} ${height}`}>
      <line x1={x(pivotStartX)} y1={y(currentPivotR)} x2={x(pivotEndX)} y2={y(currentPivotR)} className={styles.pivotTravel} />
      <path d={linePath(solution.roller_center.x_m, solution.roller_center.r_m, x, y)} className={styles.rollerPath} />
      <path d={linePath(solution.ramp_surface.x_m, solution.ramp_surface.r_m, x, y)} className={styles.rampPath} />
      {currentRollerX != null && currentRollerR != null && (
        <>
          <line x1={x(currentPivotX)} y1={y(currentPivotR)} x2={x(currentRollerX)} y2={y(currentRollerR)} className={styles.flyArm} />
          <circle cx={x(currentPivotX)} cy={y(currentPivotR)} r={5.5} className={styles.pivot} />
          <circle cx={x(currentRollerX)} cy={y(currentRollerR)} r={rollerRadiusPx} className={styles.roller} />
        </>
      )}
      {currentContactX != null && currentContactR != null && <circle cx={x(currentContactX)} cy={y(currentContactR)} r={4} className={styles.contactPoint} />}
    </svg>
    <div className={styles.inspectorMetrics}>
      <Metric label="Arm angle q" value={currentQ == null ? '—' : `${currentQ.toFixed(2)}°`} />
      <Metric label="Ramp tangent" value={currentTangent == null ? '—' : `${currentTangent.toFixed(2)}°`} />
      <Metric label="Actual / target force" value={currentForce == null || currentTarget == null ? '—' : `${currentForce.toFixed(0)} / ${currentTarget.toFixed(0)} N`} />
      <Metric label="Tip mass" value={`${(solution.tip_mass_per_flyweight_kg * G).toFixed(1)} g`} />
      <Metric label="q margin" value={`${solution.metrics.q_margin_deg.toFixed(2)}°`} />
      <Metric label="Tangent margin" value={`${solution.metrics.ramp_tangent_margin_deg.toFixed(2)}°`} />
      <Metric label="Min offset factor" value={solution.metrics.minimum_offset_factor.toFixed(4)} />
      <Metric label="History" value={solution.history.valid ? 'certified' : 'not certified'} />
    </div>
  </div>;
}

function ForceMatchPlot({ solution, shiftM, onShiftChange }: { solution: InverseRampSolution; shiftM: number; onShiftChange: (value: number) => void }) {
  const width = 820;
  const height = 250;
  const pad = { left: 58, right: 20, top: 18, bottom: 40 };
  const values = [...solution.force.target_N, ...solution.force.recovered_N];
  const lo = Math.max(0, Math.min(...values) * 0.92);
  const hi = Math.max(lo + 100, Math.max(...values) * 1.08);
  const x0 = solution.shift_m[0] ?? 0;
  const x1 = solution.shift_m[solution.shift_m.length - 1] ?? x0 + 1;
  const sx = (v: number) => pad.left + (v - x0) / Math.max(x1 - x0, 1e-9) * (width - pad.left - pad.right);
  const sy = (v: number) => pad.top + (hi - v) / Math.max(hi - lo, 1) * (height - pad.top - pad.bottom);
  const currentActual = interpolateSeries(solution.shift_m, solution.force.recovered_N, shiftM);
  const currentTarget = interpolateSeries(solution.shift_m, solution.force.target_N, shiftM);
  return <div className={styles.localForcePlot}>
    <div className={styles.localForceHeader}>
      <div><strong>Target vs this ramp's actual generated force</strong><span>This is the same selected ramp shown in the mechanism view below.</span></div>
      <b>{currentActual == null || currentTarget == null ? '—' : `${currentActual.toFixed(0)} / ${currentTarget.toFixed(0)} N`}</b>
    </div>
    <svg viewBox={`0 0 ${width} ${height}`} onPointerDown={(event) => {
      const svg = event.currentTarget;
      const matrix = svg.getScreenCTM();
      if (!matrix) return;
      const p = svg.createSVGPoint(); p.x = event.clientX; p.y = event.clientY;
      const q = p.matrixTransform(matrix.inverse());
      const fraction = clamp((q.x - pad.left) / (width - pad.left - pad.right), 0, 1);
      onShiftChange(x0 + fraction * (x1 - x0));
    }}>
      {niceTicks(lo, hi, 5).map((tick) => <g key={tick}><line x1={pad.left} x2={width - pad.right} y1={sy(tick)} y2={sy(tick)} className={styles.grid} /><text x={pad.left - 8} y={sy(tick) + 4} textAnchor="end" className={styles.axisText}>{Math.round(tick)}</text></g>)}
      <path d={linePath(solution.shift_m, solution.force.target_N, sx, sy)} className={styles.targetLine} />
      <path d={linePath(solution.shift_m, solution.force.recovered_N, sx, sy)} className={styles.solutionLine} />
      <line x1={sx(shiftM)} x2={sx(shiftM)} y1={pad.top} y2={height - pad.bottom} className={styles.inspectionCursor} />
      {currentActual != null && <circle cx={sx(shiftM)} cy={sy(currentActual)} r={5} className={styles.solutionCursor} />}
      {currentTarget != null && <circle cx={sx(shiftM)} cy={sy(currentTarget)} r={4} className={styles.targetCursor} />}
      <text x={width / 2} y={height - 7} textAnchor="middle" className={styles.axisText}>primary closure</text>
    </svg>
    <div className={styles.localForceLegend}><span className={styles.legendTarget}>target</span><span className={styles.legendSolution}>actual from selected ramp</span><em>Click the plot or use the scrubber below.</em></div>
  </div>;
}

function Metric({ label, value }: { label: string; value: string }) { return <div><span>{label}</span><strong>{value}</strong></div>; }

function initialTarget(architecture: FixedPivotArchitecture, rpm: number): InverseDesignTargetPoint[] {
  // Seed the editor from a simple physically meaningful q(x) progression, not
  // from the discrete path-domain graph. The graph is optional visual context
  // only; running Path-domain Explorer later must never change the user's force
  // target or make Force → Ramp appear graph-dependent.
  const travel = Math.max(1e-9, architecture.required_travel_m);
  const q0 = 8 * Math.PI / 180;
  const q1 = 44 * Math.PI / 180;
  const qPrime = (q1 - q0) / travel;
  const tipMass = Math.min(0.250, architecture.max_tip_mass_per_flyweight_kg);
  const armMass = architecture.arm_mass_per_flyweight_kg;
  const L = architecture.arm_length_m;
  const Mu = armMass * L / 2 + tipMass * L;
  const Su = armMass * L * L / 3 + tipMass * L * L;
  const omega2 = (rpm * RAD_S_PER_RPM) ** 2;
  const fractions = [0, 0.25, 0.5, 0.75, 1];

  return fractions.map((fraction) => {
    const q = q0 + fraction * (q1 - q0);
    const leverage = architecture.number_of_flyweights
      * Math.cos(q)
      * (architecture.pivot_radius_m * Mu + Su * Math.sin(q));
    return {
      shift_m: fraction * travel,
      force_N: Math.max(0, omega2 * leverage * qPrime),
    };
  });
}

function contextualCapability(domain: PrimaryPathDomainAnalysis | null, rpm: number): { shift_m: number[]; min_N: number[]; max_N: number[] } | null {
  if (!domain?.capability.stations.length) return null;
  const omega2 = (rpm * RAD_S_PER_RPM) ** 2;
  const shift_m: number[] = []; const min_N: number[] = []; const max_N: number[] = [];
  for (const station of domain.capability.stations) {
    if (station.max_tip_total_force_per_omega2_min == null || station.max_tip_total_force_per_omega2_max == null) continue;
    shift_m.push(station.shift_m);
    min_N.push(omega2 * station.max_tip_total_force_per_omega2_min);
    max_N.push(omega2 * station.max_tip_total_force_per_omega2_max);
  }
  return shift_m.length ? { shift_m, min_N, max_N } : null;
}

function sampleMonotone(points: InverseDesignTargetPoint[], travel: number, count: number) {
  if (!points.length) return { shift_m: [], force_N: [] };
  const sorted = [...points].sort((a, b) => a.shift_m - b.shift_m);
  const xs = sorted.map((p) => p.shift_m); const ys = sorted.map((p) => p.force_N);
  if (xs[0] > 0) { xs.unshift(0); ys.unshift(ys[0]); }
  if (xs[xs.length - 1] < travel) { xs.push(travel); ys.push(ys[ys.length - 1]); }
  if (xs.length === 1) return { shift_m: [0, travel], force_N: [ys[0], ys[0]] };
  const slopes = pchipSlopes(xs, ys);
  const outX = Array.from({ length: count }, (_, i) => travel * i / (count - 1));
  const outY = outX.map((x) => hermiteAt(xs, ys, slopes, x));
  return { shift_m: outX, force_N: outY };
}

function pchipSlopes(x: number[], y: number[]): number[] {
  const n = x.length; if (n === 2) { const d = (y[1] - y[0]) / (x[1] - x[0]); return [d, d]; }
  const h = Array.from({ length: n - 1 }, (_, i) => x[i + 1] - x[i]);
  const d = Array.from({ length: n - 1 }, (_, i) => (y[i + 1] - y[i]) / h[i]);
  const m = Array(n).fill(0);
  for (let i = 1; i < n - 1; i += 1) {
    if (d[i - 1] === 0 || d[i] === 0 || Math.sign(d[i - 1]) !== Math.sign(d[i])) m[i] = 0;
    else { const w1 = 2 * h[i] + h[i - 1]; const w2 = h[i] + 2 * h[i - 1]; m[i] = (w1 + w2) / (w1 / d[i - 1] + w2 / d[i]); }
  }
  m[0] = endpointSlope(h[0], h[1], d[0], d[1]);
  m[n - 1] = endpointSlope(h[n - 2], h[n - 3], d[n - 2], d[n - 3]);
  return m;
}
function endpointSlope(h0: number, h1: number, d0: number, d1: number) { let m = ((2 * h0 + h1) * d0 - h0 * d1) / (h0 + h1); if (Math.sign(m) !== Math.sign(d0)) m = 0; else if (Math.sign(d0) !== Math.sign(d1) && Math.abs(m) > 3 * Math.abs(d0)) m = 3 * d0; return m; }
function hermiteAt(x: number[], y: number[], m: number[], value: number) { let i = x.length - 2; for (let j = 0; j < x.length - 1; j += 1) if (value <= x[j + 1]) { i = j; break; } const h = x[i + 1] - x[i]; const t = clamp((value - x[i]) / h, 0, 1); const t2 = t * t; const t3 = t2 * t; return (2 * t3 - 3 * t2 + 1) * y[i] + (t3 - 2 * t2 + t) * h * m[i] + (-2 * t3 + 3 * t2) * y[i + 1] + (t3 - t2) * h * m[i + 1]; }

function forceRange(capability: ReturnType<typeof contextualCapability>, target: number[], solution: number[]): Range { const values = [...target, ...solution, ...(capability?.min_N ?? []), ...(capability?.max_N ?? [])].filter(Number.isFinite); if (!values.length) return { min: 0, max: 10000 }; const max = Math.max(...values, 100); const min = Math.max(0, Math.min(...values, 0)); return { min, max: Math.ceil(max * 1.12 / 500) * 500 }; }
function linePath(xs: number[], ys: number[], sx: (x: number) => number, sy: (y: number) => number) { return xs.map((x, i) => `${i === 0 ? 'M' : 'L'} ${sx(x).toFixed(2)} ${sy(ys[i]).toFixed(2)}`).join(' '); }
function areaPath(xs: number[], lo: number[], hi: number[], sx: (x: number) => number, sy: (y: number) => number) { if (!xs.length) return ''; const upper = xs.map((x, i) => `${i === 0 ? 'M' : 'L'} ${sx(x).toFixed(2)} ${sy(hi[i]).toFixed(2)}`).join(' '); const lower = [...xs].reverse().map((x, ri) => { const i = xs.length - 1 - ri; return `L ${sx(x).toFixed(2)} ${sy(lo[i]).toFixed(2)}`; }).join(' '); return `${upper} ${lower} Z`; }
function niceTicks(min: number, max: number, count: number) { const raw = (max - min) / Math.max(1, count - 1); const mag = 10 ** Math.floor(Math.log10(Math.max(raw, 1e-9))); const norm = raw / mag; const step = (norm <= 1 ? 1 : norm <= 2 ? 2 : norm <= 5 ? 5 : 10) * mag; const start = Math.ceil(min / step) * step; const rows: number[] = []; for (let v = start; v <= max + 1e-9; v += step) rows.push(v); return rows; }
function interpolateSeries(xs: number[], ys: number[], value: number): number | null {
  if (!xs.length || xs.length !== ys.length) return null;
  if (value <= xs[0]) return ys[0] ?? null;
  if (value >= xs[xs.length - 1]) return ys[ys.length - 1] ?? null;
  let lo = 0;
  let hi = xs.length - 1;
  while (hi - lo > 1) {
    const mid = Math.floor((lo + hi) / 2);
    if (xs[mid] <= value) lo = mid;
    else hi = mid;
  }
  const span = xs[hi] - xs[lo];
  const t = span <= 0 ? 0 : (value - xs[lo]) / span;
  return ys[lo] + t * (ys[hi] - ys[lo]);
}
function clamp(value: number, min: number, max: number) { return Math.max(min, Math.min(max, value)); }
