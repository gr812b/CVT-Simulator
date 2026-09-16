import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  conditionPrimaryPathDomain,
  type AbsoluteForceCapability,
  type ConditionedPathDomainAnalysis,
  type FixedPivotArchitecture,
  type ForceRequirement,
  type PrimaryPathDomainAnalysis,
} from '@api/primaryDesign';
import styles from './PrimaryDesign.module.scss';

const WIDTH = 720;
const HEIGHT = 420;
const PAD_LEFT = 58;
const PAD_RIGHT = 20;
const PAD_TOP = 24;
const PAD_BOTTOM = 46;
const MM = 1000;
const G = 1000;
const RPM_PER_RAD_S = 60 / (2 * Math.PI);
const RAD_S_PER_RPM = 2 * Math.PI / 60;

type DragState = { id: string; pointerId: number } | null;

export function RequirementsExplorer({
  architecture,
  domain,
}: {
  architecture: FixedPivotArchitecture;
  domain: PrimaryPathDomainAnalysis;
}) {
  const [rpm, setRpm] = useState(3800);
  const [maxMassKg, setMaxMassKg] = useState(Math.min(0.300, architecture.max_tip_mass_per_flyweight_kg));
  const [toleranceN, setToleranceN] = useState(5);
  const [requirements, setRequirements] = useState<ForceRequirement[]>([]);
  const [conditioned, setConditioned] = useState<ConditionedPathDomainAnalysis | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [drag, setDrag] = useState<DragState>(null);
  const forceSvgRef = useRef<SVGSVGElement | null>(null);
  const requestSerial = useRef(0);

  const solve = useCallback(async (
    nextRequirements: ForceRequirement[],
    nextRpm = rpm,
    nextMaxMassKg = maxMassKg,
  ) => {
    const serial = ++requestSerial.current;
    setLoading(true);
    setError(null);
    try {
      let result = await conditionPrimaryPathDomain(
        domain.domain_id,
        nextRequirements,
        nextMaxMassKg,
        {
          mass_sample_count: 1025,
          representative_solution_count: 8,
          reference_shaft_speed_rad_s: nextRpm * RAD_S_PER_RPM,
        },
      );
      const impossibleIds = new Set(
        result.requirements
          .filter((requirement) => !requirement.individually_attainable)
          .map((requirement) => requirement.id),
      );
      if (impossibleIds.size > 0) {
        const cleaned = nextRequirements.filter((requirement) => !impossibleIds.has(requirement.id));
        setRequirements(cleaned);
        result = await conditionPrimaryPathDomain(
          domain.domain_id,
          cleaned,
          nextMaxMassKg,
          {
            mass_sample_count: 1025,
            representative_solution_count: 8,
            reference_shaft_speed_rad_s: nextRpm * RAD_S_PER_RPM,
          },
        );
        if (serial === requestSerial.current) {
          setError('That force point is outside the full attainable region for this RPM and mass limit, so it was not added.');
        }
      }
      if (serial === requestSerial.current) setConditioned(result);
    } catch (caught) {
      if (serial === requestSerial.current) {
        setError(caught instanceof Error ? caught.message : 'Could not condition the ramp + mass domain.');
      }
    } finally {
      if (serial === requestSerial.current) setLoading(false);
    }
  }, [domain.domain_id, maxMassKg, rpm]);

  useEffect(() => {
    setRequirements([]);
    setMaxMassKg((value) => Math.min(value, architecture.max_tip_mass_per_flyweight_kg));
    void solve([], rpm, Math.min(maxMassKg, architecture.max_tip_mass_per_flyweight_kg));
  }, [domain.domain_id]); // solve is deliberately not included; domain changes are the reset boundary.

  const updateRpm = (nextRpm: number) => {
    const bounded = Math.max(100, Math.min(7000, nextRpm));
    setRpm(bounded);
    const next = requirements.map((item) => ({ ...item, shaft_speed_rad_s: bounded * RAD_S_PER_RPM }));
    setRequirements(next);
    window.setTimeout(() => void solve(next, bounded, maxMassKg), 0);
  };

  const updateMaxMass = (nextGrams: number) => {
    const next = Math.max(0, Math.min(architecture.max_tip_mass_per_flyweight_kg, nextGrams / G));
    setMaxMassKg(next);
    window.setTimeout(() => void solve(requirements, rpm, next), 0);
  };

  const fullCapability = conditioned?.force_capability.full ?? null;
  const conditionedCapability = conditioned?.force_capability.conditioned ?? null;
  const plot = useMemo(
    () => createForcePlot(fullCapability, architecture.required_travel_m),
    [fullCapability, architecture.required_travel_m],
  );

  const eventToRequirement = (event: React.PointerEvent<SVGSVGElement>): { shiftM: number; forceN: number; rawForceN: number; insideEnvelope: boolean } | null => {
    if (!plot || !fullCapability) return null;
    const svg = forceSvgRef.current;
    const matrix = svg?.getScreenCTM();
    if (!svg || !matrix) return null;
    const point = svg.createSVGPoint();
    point.x = event.clientX;
    point.y = event.clientY;
    const local = point.matrixTransform(matrix.inverse());
    const shiftM = clamp(plot.shift(local.x), 0, architecture.required_travel_m);
    const [minForce, maxForce] = interpolateEnvelope(fullCapability, shiftM);
    if (minForce === null || maxForce === null) return null;
    const requestedForce = plot.force(local.y);
    const forceN = clamp(requestedForce, minForce, maxForce);
    return { shiftM, forceN, rawForceN: requestedForce, insideEnvelope: requestedForce >= minForce - 1e-6 && requestedForce <= maxForce + 1e-6 };
  };

  const addRequirement = (event: React.PointerEvent<SVGSVGElement>) => {
    if (drag || !fullCapability) return;
    const value = eventToRequirement(event);
    if (!value) return;
    if (!value.insideEnvelope) return;
    const requirement: ForceRequirement = {
      id: `force-${Date.now().toString(36)}-${requirements.length}`,
      shift_m: value.shiftM,
      force_N: value.forceN,
      shaft_speed_rad_s: rpm * RAD_S_PER_RPM,
      tolerance_N: toleranceN,
    };
    const next = [...requirements, requirement].sort((a, b) => a.shift_m - b.shift_m);
    setRequirements(next);
    void solve(next);
  };

  const beginDrag = (event: React.PointerEvent<SVGCircleElement>, id: string) => {
    event.stopPropagation();
    forceSvgRef.current?.setPointerCapture(event.pointerId);
    setDrag({ id, pointerId: event.pointerId });
  };

  const moveDrag = (event: React.PointerEvent<SVGSVGElement>) => {
    if (!drag || drag.pointerId !== event.pointerId) return;
    const value = eventToRequirement(event);
    if (!value) return;
    setRequirements((items) => items
      .map((item) => item.id === drag.id ? { ...item, shift_m: value.shiftM, force_N: value.forceN } : item)
      .sort((a, b) => a.shift_m - b.shift_m));
  };

  const finishDrag = (event: React.PointerEvent<SVGSVGElement>) => {
    if (!drag || drag.pointerId !== event.pointerId) return;
    if (forceSvgRef.current?.hasPointerCapture(event.pointerId)) {
      forceSvgRef.current.releasePointerCapture(event.pointerId);
    }
    setDrag(null);
    // Use the latest functional-state value; the final pointer-move update may
    // not have produced a new render before pointer-up fires.
    setRequirements((current) => {
      window.setTimeout(() => void solve(current), 0);
      return current;
    });
  };

  const deleteRequirement = (id: string) => {
    const next = requirements.filter((item) => item.id !== id);
    setRequirements(next);
    void solve(next);
  };

  const clearRequirements = () => {
    setRequirements([]);
    void solve([]);
  };

  return (
    <div className={styles.requirementsExplorer}>
      <div className={styles.requirementControlBar}>
        <label className={styles.requirementField}>
          <span>Design RPM</span>
          <div><input type="number" value={rpm} min={100} max={7000} step={50} onChange={(event) => updateRpm(Number(event.target.value))} /><em>rpm</em></div>
        </label>
        <label className={styles.requirementField}>
          <span>Maximum tip mass</span>
          <div><input type="number" value={maxMassKg * G} min={0} max={architecture.max_tip_mass_per_flyweight_kg * G} step={5} onChange={(event) => updateMaxMass(Number(event.target.value))} /><em>g / flyweight</em></div>
        </label>
        <label className={styles.requirementField}>
          <span>New-point tolerance</span>
          <div><input type="number" value={toleranceN} min={0} step={1} onChange={(event) => setToleranceN(Math.max(0, Number(event.target.value)))} /><em>N</em></div>
        </label>
        <div className={styles.requirementControlActions}>
          <button type="button" className={styles.toolButton} disabled={requirements.length === 0} onClick={clearRequirements}>Clear force points</button>
          {loading && <span className={styles.dirty}>conditioning…</span>}
        </div>
      </div>

      {error && <div className={styles.requirementError}>{error}</div>}

      <div className={styles.requirementPairedViews}>
        <section className={styles.requirementPanel}>
          <div className={styles.rampFamilyHeader}>
            <div>
              <strong>Force requirements</strong>
              <span>Click inside the faded full-capability band. Drag a point to move it; the graph is reconditioned when you release.</span>
            </div>
            <span>{requirements.length} point{requirements.length === 1 ? '' : 's'}</span>
          </div>
          {plot && fullCapability ? (
            <svg
              ref={forceSvgRef}
              viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
              className={styles.requirementForceCanvas}
              onPointerDown={addRequirement}
              onPointerMove={moveDrag}
              onPointerUp={finishDrag}
              onPointerCancel={finishDrag}
              role="img"
              aria-label="Force capability and requirements through shift"
            >
              <rect width={WIDTH} height={HEIGHT} rx="12" className={styles.requirementCanvasBackground} />
              <ForceGrid plot={plot} />
              <path d={envelopePath(fullCapability, plot)} className={styles.requirementFullBand} />
              {conditionedCapability && <path d={envelopePath(conditionedCapability, plot)} className={styles.requirementConditionedBand} />}
              {conditioned?.representative_solutions.map((solution, index) => (
                <path
                  key={index}
                  d={curvePath(solution.shift_m, solution.solution.force_N.values, plot)}
                  className={styles.requirementSolutionCurve}
                />
              ))}
              {requirements.map((requirement) => (
                <g key={requirement.id}>
                  <line x1={plot.x(requirement.shift_m)} x2={plot.x(requirement.shift_m)} y1={plot.y(requirement.force_N - requirement.tolerance_N)} y2={plot.y(requirement.force_N + requirement.tolerance_N)} className={styles.requirementTolerance} />
                  <circle
                    cx={plot.x(requirement.shift_m)}
                    cy={plot.y(requirement.force_N)}
                    r="7"
                    className={styles.requirementPoint}
                    onPointerDown={(event) => beginDrag(event, requirement.id)}
                  />
                </g>
              ))}
              <text x={PAD_LEFT} y={HEIGHT - 12} className={styles.requirementAxisTitle}>shift (mm)</text>
              <text x={12} y={PAD_TOP + 4} className={styles.requirementAxisTitle}>closing force (N)</text>
            </svg>
          ) : <div className={styles.loading}>Building absolute force capability for this mass limit…</div>}
          <div className={styles.requirementLegend}>
            <span><i className={styles.requirementLegendFull} />full architecture capability</span>
            <span><i className={styles.requirementLegendConditioned} />surviving ramp + mass domain</span>
            <span><i className={styles.requirementLegendCurve} />surviving complete ramp examples</span>
          </div>
        </section>

        <section className={styles.requirementPanel}>
          <div className={styles.rampFamilyHeader}>
            <div>
              <strong>Physical ramp consequence</strong>
              <span>The faded cloud is the complete architecture ramp domain. Highlighted states can still belong to at least one complete solution carrying one common mass.</span>
            </div>
            <span>{conditioned?.summary.conditioned_domain_point_count ?? 0} states</span>
          </div>
          <RampDomainPair full={domain} conditioned={conditioned} />
          <div className={styles.requirementLegend}>
            <span><i className={styles.requirementLegendRampFull} />full physical path domain</span>
            <span><i className={styles.requirementLegendRampConditioned} />requirement-conditioned domain</span>
            <span><i className={styles.requirementLegendCurve} />history-certified solution ramps</span>
          </div>
        </section>
      </div>

      <div className={styles.requirementSummaryGrid}>
        <Summary label="Joint solution" value={conditioned ? (conditioned.summary.jointly_feasible ? 'available' : 'none') : '—'} kind={conditioned?.summary.jointly_feasible ? 'good' : 'neutral'} />
        <Summary label="Surviving mass range" value={conditioned?.mass.surviving_mass_min_kg == null ? '—' : `${(conditioned.mass.surviving_mass_min_kg * G).toFixed(1)}–${((conditioned.mass.surviving_mass_max_kg ?? 0) * G).toFixed(1)} g`} />
        <Summary label="Example solutions" value={String(conditioned?.representative_solutions.length ?? 0)} />
        <Summary label="Mass lattice resolution" value={conditioned ? `${(conditioned.mass.mass_resolution_kg * G).toFixed(2)} g` : '—'} />
      </div>

      {conditioned && !conditioned.validity.valid && conditioned.validity.findings.length > 0 && (
        <div className={styles.requirementFinding}>
          {conditioned.validity.findings.map((finding, index) => <span key={index}>{String(finding.message ?? finding.code ?? 'Requirements are incompatible.')}</span>)}
        </div>
      )}

      {conditioned && conditioned.representative_solutions.length > 0 && (
        <div className={styles.requirementSolutions}>
          {conditioned.representative_solutions.map((solution, index) => (
            <div key={index} className={styles.requirementSolutionCard}>
              <strong>Example ramp {index + 1}</strong>
              <span>example mass {(solution.solution.example_tip_mass_kg * G).toFixed(1)} g / flyweight</span>
              <span>allowed {(solution.solution.tip_mass_min_kg * G).toFixed(1)}–{(solution.solution.tip_mass_max_kg * G).toFixed(1)} g</span>
              <span>q {solution.q_deg[0].toFixed(1)}° → {solution.q_deg[solution.q_deg.length - 1].toFixed(1)}°</span>
            </div>
          ))}
        </div>
      )}

      <p className={styles.helpText}>The highlighted result is a domain of <strong>ramp + one constant physical tip mass</strong> solutions. Each additional force point intersects the shared mass carried through the complete path graph. Points cannot be created outside the full architecture capability; nevertheless, two individually attainable points can still be jointly incompatible.</p>
    </div>
  );
}

function Summary({ label, value, kind = 'neutral' }: { label: string; value: string; kind?: 'good' | 'neutral' }) {
  return <div className={styles.requirementSummary}><span>{label}</span><strong className={kind === 'good' ? styles.requirementGood : undefined}>{value}</strong></div>;
}

function RampDomainPair({
  full,
  conditioned,
}: {
  full: PrimaryPathDomainAnalysis;
  conditioned: ConditionedPathDomainAnalysis | null;
}) {
  const width = WIDTH;
  const height = HEIGHT;
  const fullPoints = full.domain_projection.ramp_surface_points;
  const conditionedPoints = conditioned?.domain_projection.ramp_surface_points ?? null;
  const bounds = useMemo(() => {
    const xs = fullPoints.x_m;
    const rs = fullPoints.r_m;
    if (!xs.length) return { xMin: -0.02, xMax: 0.08, rMin: 0, rMax: 0.12 };
    const pad = 0.006;
    return {
      xMin: Math.min(...xs) - pad,
      xMax: Math.max(...xs) + pad,
      rMin: Math.max(0, Math.min(...rs) - pad),
      rMax: Math.max(...rs) + pad,
    };
  }, [fullPoints]);
  const xSpan = Math.max(1e-9, bounds.xMax - bounds.xMin);
  const rSpan = Math.max(1e-9, bounds.rMax - bounds.rMin);
  const sx = (x: number) => PAD_LEFT + (x - bounds.xMin) / xSpan * (width - PAD_LEFT - PAD_RIGHT);
  const sy = (r: number) => PAD_TOP + (bounds.rMax - r) / rSpan * (height - PAD_TOP - PAD_BOTTOM);
  const radius = Math.max(1.4, Math.min(4.5, full.domain_projection.visual_radius_m / xSpan * (width - PAD_LEFT - PAD_RIGHT)));

  return (
    <svg viewBox={`0 0 ${width} ${height}`} className={styles.requirementRampCanvas} role="img" aria-label="Full and force-conditioned physical ramp domains">
      <rect width={width} height={height} rx="12" className={styles.requirementCanvasBackground} />
      {fullPoints.x_m.map((x, index) => <circle key={`f-${index}`} cx={sx(x)} cy={sy(fullPoints.r_m[index])} r={radius} className={styles.requirementRampFullPoint} />)}
      {conditionedPoints?.x_m.map((x, index) => <circle key={`c-${index}`} cx={sx(x)} cy={sy(conditionedPoints.r_m[index])} r={radius} className={styles.requirementRampConditionedPoint} />)}
      {conditioned?.representative_solutions.map((solution, index) => (
        <path key={index} d={solution.ramp_surface.x_m.map((x, pointIndex) => `${pointIndex === 0 ? 'M' : 'L'} ${sx(x)} ${sy(solution.ramp_surface.r_m[pointIndex])}`).join(' ')} className={styles.requirementRampSolutionCurve} />
      ))}
      <text x={PAD_LEFT} y={height - 12} className={styles.requirementAxisTitle}>ramp axial position</text>
      <text x={12} y={PAD_TOP + 4} className={styles.requirementAxisTitle}>radius</text>
    </svg>
  );
}

interface ForcePlot {
  x: (shiftM: number) => number;
  y: (forceN: number) => number;
  shift: (screenX: number) => number;
  force: (screenY: number) => number;
  yMin: number;
  yMax: number;
}

function createForcePlot(capability: AbsoluteForceCapability | null, travelM: number): ForcePlot | null {
  if (!capability) return null;
  const values = capability.stations.flatMap((station) => [station.force_min_N, station.force_max_N]).filter((value): value is number => value !== null && Number.isFinite(value));
  if (!values.length) return null;
  const rawMin = Math.min(...values, 0);
  const rawMax = Math.max(...values, 1);
  const margin = Math.max(10, 0.08 * (rawMax - rawMin));
  const yMin = Math.max(0, rawMin - margin);
  const yMax = rawMax + margin;
  const innerW = WIDTH - PAD_LEFT - PAD_RIGHT;
  const innerH = HEIGHT - PAD_TOP - PAD_BOTTOM;
  const x = (shiftM: number) => PAD_LEFT + clamp(shiftM / Math.max(1e-12, travelM), 0, 1) * innerW;
  const y = (forceN: number) => PAD_TOP + (yMax - forceN) / Math.max(1e-12, yMax - yMin) * innerH;
  const shift = (screenX: number) => clamp((screenX - PAD_LEFT) / innerW, 0, 1) * travelM;
  const force = (screenY: number) => yMax - (screenY - PAD_TOP) / innerH * (yMax - yMin);
  return { x, y, shift, force, yMin, yMax };
}

function ForceGrid({ plot }: { plot: ForcePlot }) {
  const forceTicks = Array.from({ length: 6 }, (_, index) => plot.yMin + index / 5 * (plot.yMax - plot.yMin));
  const shiftTicks = Array.from({ length: 5 }, (_, index) => index / 4);
  return <g>{forceTicks.map((value) => <g key={value}><line x1={PAD_LEFT} x2={WIDTH - PAD_RIGHT} y1={plot.y(value)} y2={plot.y(value)} className={styles.requirementGrid} /><text x={8} y={plot.y(value) + 4} className={styles.requirementTick}>{value.toFixed(0)}</text></g>)}{shiftTicks.map((fraction) => { const x = PAD_LEFT + fraction * (WIDTH - PAD_LEFT - PAD_RIGHT); return <g key={fraction}><line x1={x} x2={x} y1={PAD_TOP} y2={HEIGHT - PAD_BOTTOM} className={styles.requirementGrid} /><text x={x} y={HEIGHT - 15} textAnchor="middle" className={styles.requirementTick}>{fraction === 0 ? '0' : `${(fraction * 100).toFixed(0)}%`}</text></g>; })}</g>;
}

function envelopePath(capability: AbsoluteForceCapability, plot: ForcePlot): string {
  const valid = capability.stations.filter((station) => station.force_min_N !== null && station.force_max_N !== null);
  if (valid.length < 2) return '';
  const top = valid.map((station, index) => `${index === 0 ? 'M' : 'L'} ${plot.x(station.shift_m)} ${plot.y(station.force_max_N as number)}`);
  const bottom = valid.slice().reverse().map((station) => `L ${plot.x(station.shift_m)} ${plot.y(station.force_min_N as number)}`);
  return [...top, ...bottom, 'Z'].join(' ');
}

function curvePath(shifts: number[], forces: number[], plot: ForcePlot): string {
  if (!shifts.length || shifts.length !== forces.length) return '';
  return shifts.map((shift, index) => `${index === 0 ? 'M' : 'L'} ${plot.x(shift)} ${plot.y(forces[index])}`).join(' ');
}

function interpolateEnvelope(capability: AbsoluteForceCapability, shiftM: number): [number | null, number | null] {
  const rows = capability.stations;
  if (!rows.length) return [null, null];
  if (shiftM <= rows[0].shift_m) return [rows[0].force_min_N, rows[0].force_max_N];
  if (shiftM >= rows[rows.length - 1].shift_m) return [rows[rows.length - 1].force_min_N, rows[rows.length - 1].force_max_N];
  let lo = 0;
  let hi = rows.length - 1;
  while (hi - lo > 1) {
    const mid = Math.floor((lo + hi) / 2);
    if (rows[mid].shift_m <= shiftM) lo = mid;
    else hi = mid;
  }
  const a = rows[lo];
  const b = rows[hi];
  if (a.force_min_N === null || a.force_max_N === null || b.force_min_N === null || b.force_max_N === null) return [null, null];
  const t = (shiftM - a.shift_m) / Math.max(1e-12, b.shift_m - a.shift_m);
  return [
    a.force_min_N + t * (b.force_min_N - a.force_min_N),
    a.force_max_N + t * (b.force_max_N - a.force_max_N),
  ];
}

function clamp(value: number, min: number, max: number): number {
  return Math.max(min, Math.min(max, value));
}
