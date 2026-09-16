import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  conditionPrimaryPathDomain,
  type AbsoluteForceCapability,
  type ConditionedPathDomainAnalysis,
  type FixedPivotArchitecture,
  type ForceRequirement,
  type PrimaryPathDomainAnalysis,
} from '@api/primaryDesign';
import { ConditionedSolutionsExplorer } from './ConditionedSolutionsExplorer';
import styles from './PrimaryDesign.module.scss';

const WIDTH = 720;
const HEIGHT = 420;
const PAD_LEFT = 58;
const PAD_RIGHT = 20;
const PAD_TOP = 24;
const PAD_BOTTOM = 46;
const G = 1000;
const RAD_S_PER_RPM = 2 * Math.PI / 60;

type DragState = { id: string; pointerId: number } | null;
type RequirementsView = 'requirements' | 'solutions';

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
  const [view, setView] = useState<RequirementsView>('requirements');
  const [yZoom, setYZoom] = useState(1);
  const forceSvgRef = useRef<SVGSVGElement | null>(null);
  const requestSerial = useRef(0);
  const initializedDomainRef = useRef<string | null>(null);

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
          representative_solution_count: 12,
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
            representative_solution_count: 12,
            reference_shaft_speed_rad_s: nextRpm * RAD_S_PER_RPM,
          },
        );
        if (serial === requestSerial.current) {
          setError('That force point is outside the actual attainable force set at this shift, so it was not added.');
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
    // React StrictMode intentionally runs mount effects twice in development.
    // Conditioning a large graph twice is pure duplicate work, so key the
    // initialization to the cached domain id.
    if (initializedDomainRef.current === domain.domain_id) return;
    initializedDomainRef.current = domain.domain_id;
    setRequirements([]);
    setView('requirements');
    setYZoom(1);
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
  const focusForce = requirements.length
    ? requirements.reduce((sum, item) => sum + item.force_N, 0) / requirements.length
    : null;
  const plot = useMemo(
    () => createForcePlot(fullCapability, architecture.required_travel_m, yZoom, focusForce),
    [fullCapability, architecture.required_travel_m, yZoom, focusForce],
  );

  if (view === 'solutions' && conditioned?.summary.jointly_feasible && conditioned.representative_solutions.length > 0) {
    return (
      <ConditionedSolutionsExplorer
        architecture={architecture}
        analysis={conditioned}
        requirements={requirements}
        onBack={() => setView('requirements')}
      />
    );
  }

  const eventToRequirement = (
    event: React.PointerEvent<SVGSVGElement>,
  ): { shiftM: number; forceN: number; rawForceN: number; insideCapability: boolean } | null => {
    if (!plot || !fullCapability) return null;
    const svg = forceSvgRef.current;
    const matrix = svg?.getScreenCTM();
    if (!svg || !matrix) return null;
    const point = svg.createSVGPoint();
    point.x = event.clientX;
    point.y = event.clientY;
    const local = point.matrixTransform(matrix.inverse());
    const requestedShift = clamp(plot.shift(local.x), 0, architecture.required_travel_m);
    const station = nearestCapabilityStation(fullCapability, requestedShift);
    if (!station || station.force_intervals_N.length === 0) return null;
    const rawForceN = plot.force(local.y);
    const containing = station.force_intervals_N.find(([low, high]) => rawForceN >= low - 1e-6 && rawForceN <= high + 1e-6) ?? null;
    const chosen = containing ?? nearestInterval(station.force_intervals_N, rawForceN);
    if (!chosen) return null;
    return {
      shiftM: station.shift_m,
      forceN: clamp(rawForceN, chosen[0], chosen[1]),
      rawForceN,
      insideCapability: containing !== null,
    };
  };

  const addRequirement = (event: React.PointerEvent<SVGSVGElement>) => {
    if (drag || !fullCapability) return;
    const value = eventToRequirement(event);
    if (!value || !value.insideCapability) return;
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
    setRequirements((current) => {
      window.setTimeout(() => void solve(current), 0);
      return current;
    });
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
              <span>Only the actually attainable force intervals are filled. Click in a filled interval; dragging stops at the nearest feasible boundary.</span>
            </div>
            <div className={styles.requirementControlActions}>
              <button type="button" className={styles.toolButton} onClick={() => setYZoom((value) => Math.max(1, value / 1.5))}>Y −</button>
              <button type="button" className={styles.toolButton} onClick={() => setYZoom(1)}>Y ×{yZoom.toFixed(1)}</button>
              <button type="button" className={styles.toolButton} onClick={() => setYZoom((value) => Math.min(8, value * 1.5))}>Y +</button>
            </div>
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
              <CapabilitySlices capability={fullCapability} plot={plot} className={styles.requirementFullBand} />
              {conditionedCapability && <CapabilitySlices capability={conditionedCapability} plot={plot} className={styles.requirementConditionedBand} />}
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
              <text x={PAD_LEFT} y={HEIGHT - 12} className={styles.requirementAxisTitle}>shift</text>
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
        <Summary label="Extracted solution ramps" value={String(conditioned?.representative_solutions.length ?? 0)} />
        <Summary label="Mass lattice resolution" value={conditioned ? `${(conditioned.mass.mass_resolution_kg * G).toFixed(2)} g` : '—'} />
      </div>

      {conditioned && !conditioned.validity.valid && conditioned.validity.findings.length > 0 && (
        <div className={styles.requirementFinding}>
          {conditioned.validity.findings.map((finding, index) => <span key={index}>{String(finding.message ?? finding.code ?? 'Requirements are incompatible.')}</span>)}
        </div>
      )}

      {conditioned?.summary.jointly_feasible && conditioned.representative_solutions.length > 0 && (
        <div className={styles.requirementControlActions}>
          <button type="button" className={styles.primaryButton} onClick={() => setView('solutions')}>
            Review {conditioned.representative_solutions.length} surviving ramps →
          </button>
        </div>
      )}

      {conditioned && conditioned.summary.jointly_feasible && conditioned.representative_solutions.length === 0 && (
        <div className={styles.requirementFinding}>
          <span>The graph is feasible, but no history-certified representative was extracted from this narrow region. The graph solution remains valid; increase the representative extraction budget before choosing a concrete ramp.</span>
        </div>
      )}

      <p className={styles.helpText}>The highlighted result is a domain of <strong>ramp + one constant physical tip mass</strong> solutions. Force-space holes remain holes rather than being filled by a min/max envelope. Each additional force point intersects the shared mass carried through the complete path graph.</p>
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

function createForcePlot(
  capability: AbsoluteForceCapability | null,
  travelM: number,
  zoom: number,
  focusForce: number | null,
): ForcePlot | null {
  if (!capability) return null;
  const values = capability.stations.flatMap((station) => station.force_intervals_N.flat()).filter(Number.isFinite);
  if (!values.length) return null;
  const rawMin = Math.min(...values, 0);
  const rawMax = Math.max(...values, 1);
  const margin = Math.max(10, 0.08 * (rawMax - rawMin));
  const baseMin = Math.max(0, rawMin - margin);
  const baseMax = rawMax + margin;
  const baseSpan = Math.max(1, baseMax - baseMin);
  const span = baseSpan / Math.max(1, zoom);
  const desiredCenter = focusForce ?? 0.5 * (baseMin + baseMax);
  let yMin = desiredCenter - 0.5 * span;
  let yMax = desiredCenter + 0.5 * span;
  if (yMin < 0) {
    yMax -= yMin;
    yMin = 0;
  }
  if (yMax > baseMax && zoom <= 1.0001) yMax = baseMax;
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

function CapabilitySlices({ capability, plot, className }: { capability: AbsoluteForceCapability; plot: ForcePlot; className: string }) {
  const rows = capability.stations;
  if (rows.length === 0) return null;
  return (
    <g className={className}>
      {rows.flatMap((station, stationIndex) => {
        const leftShift = stationIndex === 0 ? station.shift_m : 0.5 * (rows[stationIndex - 1].shift_m + station.shift_m);
        const rightShift = stationIndex === rows.length - 1 ? station.shift_m : 0.5 * (station.shift_m + rows[stationIndex + 1].shift_m);
        const x0 = plot.x(leftShift);
        const x1 = plot.x(rightShift);
        return station.force_intervals_N.map(([low, high], intervalIndex) => {
          const y0 = plot.y(high);
          const y1 = plot.y(low);
          return <rect key={`${stationIndex}-${intervalIndex}`} x={Math.min(x0, x1)} y={Math.min(y0, y1)} width={Math.max(1.5, Math.abs(x1 - x0) + 0.8)} height={Math.max(0.8, Math.abs(y1 - y0))} stroke="none" />;
        });
      })}
    </g>
  );
}

function curvePath(shifts: number[], forces: number[], plot: ForcePlot): string {
  if (!shifts.length || shifts.length !== forces.length) return '';
  return shifts.map((shift, index) => `${index === 0 ? 'M' : 'L'} ${plot.x(shift)} ${plot.y(forces[index])}`).join(' ');
}

function nearestCapabilityStation(capability: AbsoluteForceCapability, shiftM: number) {
  if (!capability.stations.length) return null;
  let best = capability.stations[0];
  let bestDistance = Math.abs(best.shift_m - shiftM);
  for (const station of capability.stations.slice(1)) {
    const distance = Math.abs(station.shift_m - shiftM);
    if (distance < bestDistance) {
      best = station;
      bestDistance = distance;
    }
  }
  return best;
}

function nearestInterval(intervals: Array<[number, number]>, value: number): [number, number] | null {
  if (!intervals.length) return null;
  let best = intervals[0];
  let bestDistance = intervalDistance(best, value);
  for (const interval of intervals.slice(1)) {
    const distance = intervalDistance(interval, value);
    if (distance < bestDistance) {
      best = interval;
      bestDistance = distance;
    }
  }
  return best;
}

function intervalDistance([low, high]: [number, number], value: number): number {
  if (value < low) return low - value;
  if (value > high) return value - high;
  return 0;
}

function clamp(value: number, min: number, max: number): number {
  return Math.max(min, Math.min(max, value));
}
