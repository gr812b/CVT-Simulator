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
type YRange = { min: number; max: number };

export function RequirementsExplorer({
  architecture,
  domain,
}: {
  architecture: FixedPivotArchitecture;
  domain: PrimaryPathDomainAnalysis;
}) {
  const [rpm, setRpm] = useState(3800);
  const [maxMassKg, setMaxMassKg] = useState(Math.min(0.300, architecture.max_tip_mass_per_flyweight_kg));
  const [toleranceN, setToleranceN] = useState(50);
  const [requirements, setRequirements] = useState<ForceRequirement[]>([]);
  const [conditioned, setConditioned] = useState<ConditionedPathDomainAnalysis | null>(null);
  const [conditioningLoading, setConditioningLoading] = useState(false);
  const [solutionsLoading, setSolutionsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [drag, setDrag] = useState<DragState>(null);
  const [view, setView] = useState<RequirementsView>('requirements');
  const [yRange, setYRange] = useState<YRange | null>(null);
  const forceSvgRef = useRef<SVGSVGElement | null>(null);
  const requestSerial = useRef(0);
  const initializedDomainRef = useRef<string | null>(null);
  const committedRequirementsRef = useRef<ForceRequirement[]>([]);
  const committedConditionedRef = useRef<ConditionedPathDomainAnalysis | null>(null);

  const requestCondition = useCallback(async (
    nextRequirements: ForceRequirement[],
    nextRpm: number,
    nextMaxMassKg: number,
    representativeSolutionCount: number,
  ) => conditionPrimaryPathDomain(
    domain.domain_id,
    nextRequirements,
    nextMaxMassKg,
    {
      mass_sample_count: 1025,
      representative_solution_count: representativeSolutionCount,
      reference_shaft_speed_rad_s: nextRpm * RAD_S_PER_RPM,
    },
  ), [domain.domain_id]);

  const solve = useCallback(async (
    nextRequirements: ForceRequirement[],
    nextRpm = rpm,
    nextMaxMassKg = maxMassKg,
    rollbackInvalidPoint = false,
  ) => {
    const serial = ++requestSerial.current;
    setConditioningLoading(true);
    setError(null);
    try {
      const result = await requestCondition(nextRequirements, nextRpm, nextMaxMassKg, 0);
      const impossibleIds = new Set(
        result.requirements
          .filter((requirement) => !requirement.individually_attainable && !requirement.id.startsWith('guide-'))
          .map((requirement) => requirement.id),
      );
      if (impossibleIds.size > 0) {
        if (serial !== requestSerial.current) return;
        if (rollbackInvalidPoint) {
          // Point placement/dragging starts from an already committed domain.
          // If the proposed point is impossible, snap back to that exact state
          // instead of issuing a second full conditioning request just to
          // rediscover the previous answer.
          setRequirements(committedRequirementsRef.current);
          setConditioned(committedConditionedRef.current);
          setError('That hard lock is outside the actual attainable force set at this shift, so the previous profile was kept.');
          return;
        }

        const cleaned = nextRequirements.filter((requirement) => !impossibleIds.has(requirement.id));
        setRequirements(cleaned);
        setError('One or more hard locks became unattainable and were removed; soft profile guides were kept.');
        const cleanedResult = await requestCondition(cleaned, nextRpm, nextMaxMassKg, 0);
        if (serial === requestSerial.current) {
          setConditioned(cleanedResult);
          committedRequirementsRef.current = cleaned;
          committedConditionedRef.current = cleanedResult;
        }
        return;
      }
      if (serial === requestSerial.current) {
        setConditioned(result);
        committedRequirementsRef.current = nextRequirements;
        committedConditionedRef.current = result;
      }
    } catch (caught) {
      if (serial === requestSerial.current) {
        setError(caught instanceof Error ? caught.message : 'Could not condition the ramp + mass domain.');
      }
    } finally {
      if (serial === requestSerial.current) setConditioningLoading(false);
    }
  }, [maxMassKg, requestCondition, rpm]);

  useEffect(() => {
    if (initializedDomainRef.current === domain.domain_id) return;
    initializedDomainRef.current = domain.domain_id;
    const boundedMass = Math.min(maxMassKg, architecture.max_tip_mass_per_flyweight_kg);
    setRequirements([]);
    committedRequirementsRef.current = [];
    committedConditionedRef.current = null;
    setView('requirements');
    setYRange(null);
    setMaxMassKg(boundedMass);
    void solve([], rpm, boundedMass);
  }, [architecture.max_tip_mass_per_flyweight_kg, domain.domain_id]); // Domain change is the reset boundary.

  const updateRpm = (nextRpm: number) => {
    const bounded = Math.max(100, Math.min(7000, nextRpm));
    setRpm(bounded);
    const next = requirements.map((item) => ({ ...item, shaft_speed_rad_s: bounded * RAD_S_PER_RPM }));
    setRequirements(next);
    setYRange(null);
    window.setTimeout(() => void solve(next, bounded, maxMassKg), 0);
  };

  const updateMaxMass = (nextGrams: number) => {
    const next = Math.max(0, Math.min(architecture.max_tip_mass_per_flyweight_kg, nextGrams / G));
    setMaxMassKg(next);
    setYRange(null);
    window.setTimeout(() => void solve(requirements, rpm, next), 0);
  };

  const fullCapability = conditioned?.force_capability.full ?? null;
  const conditionedCapability = conditioned?.force_capability.conditioned ?? null;
  const profileGuides = useMemo(() => requirements.filter(isProfileGuide), [requirements]);
  const hardLocks = useMemo(() => requirements.filter((item) => !isProfileGuide(item)), [requirements]);
  const targetProfile = useMemo(() => buildTargetProfile(profileGuides, 129), [profileGuides]);
  const profileSummary = conditioned?.summary as ConditionedPathDomainAnalysis['summary'] & {
    profile_guide_count?: number;
    hard_lock_count?: number;
    best_profile_rms_error_N?: number | null;
    best_profile_max_error_N?: number | null;
  } | undefined;
  const previewOnly = Boolean(
    conditioned &&
    (conditioned.summary as ConditionedPathDomainAnalysis['summary'] & { representative_solutions_preview_only?: boolean })
      .representative_solutions_preview_only,
  );
  const autoYRange = useMemo(() => capabilityYRange(fullCapability), [fullCapability]);
  const plot = useMemo(
    () => createForcePlot(fullCapability, architecture.required_travel_m, yRange ?? autoYRange),
    [fullCapability, architecture.required_travel_m, yRange, autoYRange],
  );

  if (view === 'solutions' && conditioned && conditioned.representative_solutions.length > 0 && !previewOnly) {
    return (
      <ConditionedSolutionsExplorer
        architecture={architecture}
        analysis={conditioned}
        requirements={requirements}
        onBack={() => setView('requirements')}
      />
    );
  }

  const svgPoint = (clientX: number, clientY: number): { x: number; y: number } | null => {
    const svg = forceSvgRef.current;
    const matrix = svg?.getScreenCTM();
    if (!svg || !matrix) return null;
    const point = svg.createSVGPoint();
    point.x = clientX;
    point.y = clientY;
    const local = point.matrixTransform(matrix.inverse());
    return { x: local.x, y: local.y };
  };

  const eventToRequirement = (
    event: React.PointerEvent<SVGSVGElement>,
  ): { shiftM: number; forceN: number; insideCapability: boolean } | null => {
    if (!plot || !fullCapability) return null;
    const local = svgPoint(event.clientX, event.clientY);
    if (!local) return null;
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
      insideCapability: containing !== null,
    };
  };

  const addRequirement = (event: React.PointerEvent<SVGSVGElement>) => {
    if (drag || !fullCapability || conditioningLoading) return;
    const value = eventToRequirement(event);
    if (!value?.insideCapability) return;
    const requirement: ForceRequirement = {
      id: `guide-${Date.now().toString(36)}-${requirements.length}`,
      shift_m: value.shiftM,
      force_N: value.forceN,
      shaft_speed_rad_s: rpm * RAD_S_PER_RPM,
      tolerance_N: toleranceN,
    };
    const next = [...requirements, requirement].sort((a, b) => a.shift_m - b.shift_m);
    setRequirements(next);
    void solve(next, rpm, maxMassKg, true);
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
      window.setTimeout(() => void solve(current, rpm, maxMassKg, true), 0);
      return current;
    });
  };

  const zoomY = (event: React.WheelEvent<SVGSVGElement>) => {
    if (!plot || !autoYRange) return;
    event.preventDefault();
    const local = svgPoint(event.clientX, event.clientY);
    if (!local) return;
    const current = { min: plot.yMin, max: plot.yMax };
    const span = Math.max(1e-9, current.max - current.min);
    const autoSpan = Math.max(1, autoYRange.max - autoYRange.min);

    if (event.shiftKey) {
      const wheel = Math.abs(event.deltaY) >= Math.abs(event.deltaX) ? event.deltaY : event.deltaX;
      const deltaForce = wheel / 500 * span;
      setYRange(constrainYRange({ min: current.min + deltaForce, max: current.max + deltaForce }, autoSpan));
      return;
    }

    const anchor = plot.force(local.y);
    const anchorFraction = clamp((anchor - current.min) / span, 0, 1);
    const scale = Math.exp(event.deltaY * 0.0016);
    const nextSpan = clamp(span * scale, Math.max(4, autoSpan * 0.025), autoSpan * 3);
    const next = {
      min: anchor - anchorFraction * nextSpan,
      max: anchor + (1 - anchorFraction) * nextSpan,
    };
    setYRange(constrainYRange(next, autoSpan));
  };

  const deleteRequirement = (id: string) => {
    const next = requirements.filter((item) => item.id !== id);
    setRequirements(next);
    void solve(next, rpm, maxMassKg, false);
  };

  const setPointMode = (id: string, mode: 'guide' | 'hard') => {
    const next = requirements.map((item) => {
      if (item.id !== id) return item;
      const suffix = item.id.replace(/^(guide|hard)-/, '');
      return { ...item, id: `${mode}-${suffix}` };
    });
    setRequirements(next);
    void solve(next, rpm, maxMassKg, false);
  };

  const clearRequirements = () => {
    setRequirements([]);
    void solve([]);
  };

  const openSolutions = async () => {
    if (!conditioned?.summary.jointly_feasible || requirements.length === 0) return;
    if (conditioned.representative_solutions.length > 0 && !previewOnly) {
      setView('solutions');
      return;
    }
    setSolutionsLoading(true);
    setError(null);
    try {
      const result = await requestCondition(requirements, rpm, maxMassKg, 12);
      setConditioned(result);
      if (result.representative_solutions.length > 0) {
        setView('solutions');
      } else {
        setError('The graph is feasible, but this representative search did not find a history-certified ramp to inspect.');
      }
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Could not extract representative ramp solutions.');
    } finally {
      setSolutionsLoading(false);
    }
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
          <span>Guide corridor / lock tolerance</span>
          <div><input type="number" value={toleranceN} min={0} step={1} onChange={(event) => setToleranceN(Math.max(0, Number(event.target.value)))} /><em>N</em></div>
        </label>
        <div className={styles.requirementControlActions}>
          <button type="button" className={styles.toolButton} disabled={requirements.length === 0 || conditioningLoading} onClick={clearRequirements}>Clear profile</button>
          {conditioningLoading && <span className={styles.dirty}>updating domain…</span>}
        </div>
      </div>

      {error && <div className={styles.requirementError}>{error}</div>}

      <div className={styles.requirementPairedViews}>
        <section className={styles.requirementPanel}>
          <div className={styles.rampFamilyHeader}>
            <div>
              <strong>Target force profile</strong>
              <span>Click to sketch desired behavior. New points are soft profile handles by default; lock only the points that must be met within tolerance.</span>
            </div>
            <span>{requirements.filter((item) => isProfileGuide(item)).length} guide{requirements.filter((item) => isProfileGuide(item)).length === 1 ? '' : 's'} · {requirements.filter((item) => !isProfileGuide(item)).length} lock{requirements.filter((item) => !isProfileGuide(item)).length === 1 ? '' : 's'}</span>
          </div>
          <div className={styles.requirementControlActions} style={{ justifyContent: 'space-between' }}>
            <span className={styles.helpText} style={{ margin: 0 }}>
              Wheel: zoom Y · Shift+wheel: pan Y
            </span>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              {plot && <span className={styles.muted} style={{ margin: 0 }}>{plot.yMin.toFixed(0)}–{plot.yMax.toFixed(0)} N</span>}
              <button type="button" className={styles.toolButton} disabled={yRange === null} onClick={() => setYRange(null)}>Fit Y</button>
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
              onWheel={zoomY}
              role="img"
              aria-label="Force capability and requirements through shift"
            >
              <rect width={WIDTH} height={HEIGHT} rx="12" className={styles.requirementCanvasBackground} />
              <ForceGrid plot={plot} travelM={architecture.required_travel_m} />
              <CapabilitySlices capability={fullCapability} plot={plot} className={styles.requirementFullBand} />
              {conditionedCapability && hardLocks.length > 0 && <CapabilitySlices capability={conditionedCapability} plot={plot} className={styles.requirementConditionedBand} discrete={capabilityProjectionKind(conditionedCapability) === 'graph_stations'} />}
              {targetProfile && targetProfile.shiftM.length > 1 && (
                <>
                  <path d={profileBandPath(targetProfile, plot)} style={{ fill: 'rgba(255, 208, 122, 0.10)', stroke: 'none', pointerEvents: 'none' }} />
                  <path d={curvePath(targetProfile.shiftM, targetProfile.forceN, plot)} style={{ fill: 'none', stroke: 'rgba(255, 208, 122, 0.95)', strokeWidth: 2.6, pointerEvents: 'none' }} />
                </>
              )}
              {conditioned?.representative_solutions.map((solution, index) => (
                <path
                  key={`preview-force-${index}`}
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
                    r={isProfileGuide(requirement) ? 7 : 8}
                    className={styles.requirementPoint}
                    style={isProfileGuide(requirement) ? undefined : { fill: '#ff9f9f', strokeWidth: 3 }}
                    onPointerDown={(event) => beginDrag(event, requirement.id)}
                  />
                </g>
              ))}
              <text x={PAD_LEFT} y={HEIGHT - 12} className={styles.requirementAxisTitle}>shift (mm)</text>
              <text x={12} y={PAD_TOP + 4} className={styles.requirementAxisTitle}>closing force (N)</text>
            </svg>
          ) : <div className={styles.loading}>Building force capability…</div>}
          <div className={styles.requirementLegend}>
            <span><i className={styles.requirementLegendFull} />full architecture capability</span>
            <span><i className={styles.requirementLegendConditioned} />hard-lock constrained domain</span>
            {conditioned && conditioned.representative_solutions.length > 0 && (
              <span><i className={styles.requirementLegendCurve} />{previewOnly ? 'best-fit complete-path previews' : 'ranked certified ramps'}</span>
            )}
          </div>
        </section>

        <section className={styles.requirementPanel}>
          <div className={styles.rampFamilyHeader}>
            <div>
              <strong>Physical ramp consequence</strong>
              <span>Soft guides rank complete ramps without deleting the design space. Only explicit hard locks narrow the physical domain; overlaid curves are the current best whole-profile matches.</span>
            </div>
            <span>{conditioned?.summary.conditioned_domain_point_count ?? 0} states</span>
          </div>
          <RampDomainPair full={domain} conditioned={conditioned} showConditionedDomain={hardLocks.length > 0} />
          <div className={styles.requirementLegend}>
            <span><i className={styles.requirementLegendRampFull} />full physical path domain</span>
            {hardLocks.length > 0 && <span><i className={styles.requirementLegendRampConditioned} />hard-lock constrained domain</span>}
            {conditioned && conditioned.representative_solutions.length > 0 && (
              <span><i className={styles.requirementLegendCurve} />{previewOnly ? 'best-fit complete-path previews' : 'ranked certified ramps'}</span>
            )}
          </div>
        </section>
      </div>

      <div className={styles.requirementSummaryGrid}>
        <Summary label="Hard locks" value={hardLocks.length === 0 ? 'none' : (conditioned?.summary.jointly_feasible ? `${hardLocks.length} feasible` : 'incompatible')} kind={conditioned?.summary.jointly_feasible ? 'good' : 'neutral'} />
        <Summary label="Best preview RMS" value={profileSummary?.best_profile_rms_error_N == null ? '—' : `${profileSummary.best_profile_rms_error_N.toFixed(1)} N`} />
        <Summary label="Best max deviation" value={profileSummary?.best_profile_max_error_N == null ? '—' : `${profileSummary.best_profile_max_error_N.toFixed(1)} N`} />
        <Summary label="Available mass range" value={conditioned?.mass.surviving_mass_min_kg == null ? '—' : `${(conditioned.mass.surviving_mass_min_kg * G).toFixed(1)}–${((conditioned.mass.surviving_mass_max_kg ?? 0) * G).toFixed(1)} g`} />
      </div>

      {requirements.length > 0 && (
        <div style={{ display: 'grid', gap: 8 }}>
          <div className={styles.rampFamilyHeader}>
            <div>
              <strong>Profile handles</strong>
              <span>Guide = desired behavior used for whole-curve ranking. Lock = exact physical constraint within the shown tolerance.</span>
            </div>
          </div>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
            {requirements.map((requirement, index) => (
              <div key={requirement.id} className={styles.requirementSolutionCard} style={{ minWidth: 190 }}>
                <strong>{isProfileGuide(requirement) ? `Guide ${index + 1}` : `Hard lock ${index + 1}`}</strong>
                <span>{(requirement.shift_m * 1000).toFixed(2)} mm · {requirement.force_N.toFixed(0)} N · ±{requirement.tolerance_N.toFixed(0)} N</span>
                <div style={{ display: 'flex', gap: 6, marginTop: 5 }}>
                  <button type="button" className={isProfileGuide(requirement) ? styles.toolActive : styles.toolButton} disabled={conditioningLoading} onClick={() => setPointMode(requirement.id, 'guide')}>Guide</button>
                  <button type="button" className={!isProfileGuide(requirement) ? styles.toolActive : styles.toolButton} disabled={conditioningLoading} onClick={() => setPointMode(requirement.id, 'hard')}>Lock</button>
                  <button type="button" className={styles.toolButton} disabled={conditioningLoading} onClick={() => deleteRequirement(requirement.id)}>Delete</button>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {conditioned && conditioned.validity.findings.length > 0 && (
        <div className={styles.requirementFinding}>
          {conditioned.validity.findings.map((finding, index) => <span key={index}>{String(finding.message ?? finding.code ?? 'Requirements are incompatible.')}</span>)}
        </div>
      )}

      {conditioned?.summary.jointly_feasible && requirements.length > 0 && (
        <div className={styles.requirementControlActions}>
          <button type="button" className={styles.primaryButton} disabled={solutionsLoading || conditioningLoading} onClick={() => void openSolutions()}>
            {solutionsLoading ? 'Searching best-fit ramps…' : 'Find best-fit ramps →'}
          </button>
        </div>
      )}

      <p className={styles.helpText}>Profile handles are a behavioral sketch, not binary filters. The backend builds a shape-preserving target curve through the guides and searches complete ramp paths for minimum force error over the whole covered shift range with one constant tip mass. Hard locks remain available when a point genuinely must be met. Preview ramps skip nonlocal history certification for responsiveness; the Solutions search certifies and ranks the final gallery.</p>
    </div>
  );
}

function Summary({ label, value, kind = 'neutral' }: { label: string; value: string; kind?: 'good' | 'neutral' }) {
  return <div className={styles.requirementSummary}><span>{label}</span><strong className={kind === 'good' ? styles.requirementGood : undefined}>{value}</strong></div>;
}

function RampDomainPair({
  full,
  conditioned,
  showConditionedDomain,
}: {
  full: PrimaryPathDomainAnalysis;
  conditioned: ConditionedPathDomainAnalysis | null;
  showConditionedDomain: boolean;
}) {
  const fullPoints = full.domain_projection.ramp_surface_points;
  const conditionedPoints = showConditionedDomain ? (conditioned?.domain_projection.ramp_surface_points ?? null) : null;
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
  const sx = (x: number) => PAD_LEFT + (x - bounds.xMin) / xSpan * (WIDTH - PAD_LEFT - PAD_RIGHT);
  const sy = (r: number) => PAD_TOP + (bounds.rMax - r) / rSpan * (HEIGHT - PAD_TOP - PAD_BOTTOM);
  const radius = Math.max(1.4, Math.min(4.5, full.domain_projection.visual_radius_m / xSpan * (WIDTH - PAD_LEFT - PAD_RIGHT)));

  return (
    <svg viewBox={`0 0 ${WIDTH} ${HEIGHT}`} className={styles.requirementRampCanvas} role="img" aria-label="Full and force-conditioned physical ramp domains">
      <rect width={WIDTH} height={HEIGHT} rx="12" className={styles.requirementCanvasBackground} />
      {sampleIndices(fullPoints.x_m.length, 1800).map((index) => <circle key={`f-${index}`} cx={sx(fullPoints.x_m[index])} cy={sy(fullPoints.r_m[index])} r={radius} className={styles.requirementRampFullPoint} />)}
      {conditionedPoints && sampleIndices(conditionedPoints.x_m.length, 1800).map((index) => <circle key={`c-${index}`} cx={sx(conditionedPoints.x_m[index])} cy={sy(conditionedPoints.r_m[index])} r={radius} className={styles.requirementRampConditionedPoint} />)}
      {conditioned?.representative_solutions.map((solution, index) => (
        <path
          key={`path-${index}`}
          d={solution.ramp_surface.x_m.map((x, pointIndex) => `${pointIndex === 0 ? 'M' : 'L'} ${sx(x)} ${sy(solution.ramp_surface.r_m[pointIndex])}`).join(' ')}
          className={styles.requirementRampSolutionCurve}
        />
      ))}
      <text x={PAD_LEFT} y={HEIGHT - 12} className={styles.requirementAxisTitle}>ramp axial position</text>
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

function capabilityYRange(capability: AbsoluteForceCapability | null): YRange | null {
  if (!capability) return null;
  const values = capability.stations.flatMap((station) => station.force_intervals_N.flat()).filter(Number.isFinite);
  if (!values.length) return null;
  const rawMin = Math.min(...values, 0);
  const rawMax = Math.max(...values, 1);
  const margin = Math.max(10, 0.07 * (rawMax - rawMin));
  return { min: Math.max(0, rawMin - margin), max: rawMax + margin };
}

function createForcePlot(capability: AbsoluteForceCapability | null, travelM: number, range: YRange | null): ForcePlot | null {
  if (!capability || !range) return null;
  const yMin = range.min;
  const yMax = Math.max(range.min + 1e-6, range.max);
  const innerW = WIDTH - PAD_LEFT - PAD_RIGHT;
  const innerH = HEIGHT - PAD_TOP - PAD_BOTTOM;
  const x = (shiftM: number) => PAD_LEFT + clamp(shiftM / Math.max(1e-12, travelM), 0, 1) * innerW;
  const y = (forceN: number) => PAD_TOP + (yMax - forceN) / (yMax - yMin) * innerH;
  const shift = (screenX: number) => clamp((screenX - PAD_LEFT) / innerW, 0, 1) * travelM;
  const force = (screenY: number) => yMax - (screenY - PAD_TOP) / innerH * (yMax - yMin);
  return { x, y, shift, force, yMin, yMax };
}

function constrainYRange(range: YRange, autoSpan: number): YRange {
  let min = range.min;
  let max = range.max;
  const span = Math.max(4, max - min);
  if (min < 0) {
    max -= min;
    min = 0;
  }
  if (max - min > autoSpan * 3) max = min + autoSpan * 3;
  if (max <= min) max = min + span;
  return { min, max };
}

function ForceGrid({ plot, travelM }: { plot: ForcePlot; travelM: number }) {
  const forceTicks = niceTicks(plot.yMin, plot.yMax, 6);
  const shiftTicks = Array.from({ length: 5 }, (_, index) => index / 4);
  return (
    <g>
      {forceTicks.map((value) => (
        <g key={value}>
          <line x1={PAD_LEFT} x2={WIDTH - PAD_RIGHT} y1={plot.y(value)} y2={plot.y(value)} className={styles.requirementGrid} />
          <text x={8} y={plot.y(value) + 4} className={styles.requirementTick}>{formatTick(value)}</text>
        </g>
      ))}
      {shiftTicks.map((fraction) => {
        const shiftM = fraction * travelM;
        const x = plot.x(shiftM);
        return (
          <g key={fraction}>
            <line x1={x} x2={x} y1={PAD_TOP} y2={HEIGHT - PAD_BOTTOM} className={styles.requirementGrid} />
            <text x={x} y={HEIGHT - 15} textAnchor="middle" className={styles.requirementTick}>{(shiftM * 1000).toFixed(fraction === 1 ? 1 : 0)}</text>
          </g>
        );
      })}
    </g>
  );
}

function CapabilitySlices({ capability, plot, className, discrete = false }: { capability: AbsoluteForceCapability; plot: ForcePlot; className: string; discrete?: boolean }) {
  const rows = capability.stations;
  if (rows.length === 0) return null;
  return (
    <g className={className}>
      {rows.flatMap((station, stationIndex) => {
        const centerX = plot.x(station.shift_m);
        const leftShift = stationIndex === 0 ? station.shift_m : 0.5 * (rows[stationIndex - 1].shift_m + station.shift_m);
        const rightShift = stationIndex === rows.length - 1 ? station.shift_m : 0.5 * (station.shift_m + rows[stationIndex + 1].shift_m);
        const x0 = discrete ? centerX - 3 : plot.x(leftShift);
        const x1 = discrete ? centerX + 3 : plot.x(rightShift);
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
  return shifts
    .map((shift, index) => `${index === 0 ? 'M' : 'L'} ${plot.x(shift)} ${plot.y(forces[index])}`)
    .join(' ');
}

function capabilityProjectionKind(capability: AbsoluteForceCapability): string | undefined {
  return (capability as AbsoluteForceCapability & { projection_kind?: string }).projection_kind;
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

function niceTicks(min: number, max: number, targetCount: number): number[] {
  const span = Math.max(1e-9, max - min);
  const rough = span / Math.max(2, targetCount - 1);
  const magnitude = 10 ** Math.floor(Math.log10(rough));
  const residual = rough / magnitude;
  const nice = residual <= 1 ? 1 : residual <= 2 ? 2 : residual <= 5 ? 5 : 10;
  const step = nice * magnitude;
  const first = Math.ceil(min / step) * step;
  const values: number[] = [];
  for (let value = first; value <= max + 1e-9; value += step) values.push(value);
  return values;
}

function formatTick(value: number): string {
  const abs = Math.abs(value);
  if (abs >= 100) return value.toFixed(0);
  if (abs >= 10) return value.toFixed(1).replace(/\.0$/, '');
  return value.toFixed(2).replace(/0+$/, '').replace(/\.$/, '');
}

function sampleIndices(length: number, maximum: number): number[] {
  if (length <= maximum) return Array.from({ length }, (_, index) => index);
  const step = length / maximum;
  const result: number[] = [];
  let last = -1;
  for (let sample = 0; sample < maximum; sample += 1) {
    const index = Math.min(length - 1, Math.floor(sample * step));
    if (index !== last) result.push(index);
    last = index;
  }
  if (result[result.length - 1] !== length - 1) result.push(length - 1);
  return result;
}


function isProfileGuide(requirement: ForceRequirement): boolean {
  return requirement.id.startsWith('guide-');
}

type TargetProfile = { shiftM: number[]; forceN: number[]; toleranceN: number[] };

function buildTargetProfile(guides: ForceRequirement[], count: number): TargetProfile | null {
  if (guides.length === 0) return null;
  const sorted = [...guides].sort((a, b) => a.shift_m - b.shift_m);
  const unique: ForceRequirement[] = [];
  for (const item of sorted) {
    const previous = unique[unique.length - 1];
    if (previous && Math.abs(previous.shift_m - item.shift_m) < 1e-9) {
      previous.force_N = 0.5 * (previous.force_N + item.force_N);
      previous.tolerance_N = 0.5 * (previous.tolerance_N + item.tolerance_N);
    } else {
      unique.push({ ...item });
    }
  }
  if (unique.length === 1) {
    return { shiftM: [unique[0].shift_m], forceN: [unique[0].force_N], toleranceN: [unique[0].tolerance_N] };
  }
  const xs = unique.map((item) => item.shift_m);
  const ys = unique.map((item) => item.force_N);
  const ts = unique.map((item) => Math.max(1, item.tolerance_N));
  const ySlopes = pchipSlopes(xs, ys);
  const tSlopes = pchipSlopes(xs, ts);
  const shiftM = Array.from({ length: Math.max(3, count) }, (_, index) => xs[0] + index / (Math.max(3, count) - 1) * (xs[xs.length - 1] - xs[0]));
  return {
    shiftM,
    forceN: shiftM.map((x) => pchipValue(xs, ys, ySlopes, x)),
    toleranceN: shiftM.map((x) => Math.max(1, pchipValue(xs, ts, tSlopes, x))),
  };
}

function pchipSlopes(xs: number[], ys: number[]): number[] {
  const n = xs.length;
  if (n === 2) {
    const d = (ys[1] - ys[0]) / Math.max(1e-12, xs[1] - xs[0]);
    return [d, d];
  }
  const h = Array.from({ length: n - 1 }, (_, i) => Math.max(1e-12, xs[i + 1] - xs[i]));
  const delta = Array.from({ length: n - 1 }, (_, i) => (ys[i + 1] - ys[i]) / h[i]);
  const m = Array(n).fill(0) as number[];
  for (let i = 1; i < n - 1; i += 1) {
    if (delta[i - 1] === 0 || delta[i] === 0 || Math.sign(delta[i - 1]) !== Math.sign(delta[i])) {
      m[i] = 0;
    } else {
      const w1 = 2 * h[i] + h[i - 1];
      const w2 = h[i] + 2 * h[i - 1];
      m[i] = (w1 + w2) / (w1 / delta[i - 1] + w2 / delta[i]);
    }
  }
  const endpoint = (h0: number, h1: number, d0: number, d1: number) => {
    let value = ((2 * h0 + h1) * d0 - h0 * d1) / (h0 + h1);
    if (Math.sign(value) !== Math.sign(d0)) value = 0;
    else if (Math.sign(d0) !== Math.sign(d1) && Math.abs(value) > Math.abs(3 * d0)) value = 3 * d0;
    return value;
  };
  m[0] = endpoint(h[0], h[1], delta[0], delta[1]);
  m[n - 1] = endpoint(h[n - 2], h[n - 3], delta[n - 2], delta[n - 3]);
  return m;
}

function pchipValue(xs: number[], ys: number[], slopes: number[], x: number): number {
  if (x <= xs[0]) return ys[0];
  if (x >= xs[xs.length - 1]) return ys[ys.length - 1];
  let lo = 0;
  let hi = xs.length - 1;
  while (hi - lo > 1) {
    const mid = Math.floor((lo + hi) / 2);
    if (xs[mid] <= x) lo = mid;
    else hi = mid;
  }
  const h = Math.max(1e-12, xs[hi] - xs[lo]);
  const t = (x - xs[lo]) / h;
  const h00 = 2 * t ** 3 - 3 * t ** 2 + 1;
  const h10 = t ** 3 - 2 * t ** 2 + t;
  const h01 = -2 * t ** 3 + 3 * t ** 2;
  const h11 = t ** 3 - t ** 2;
  return h00 * ys[lo] + h10 * h * slopes[lo] + h01 * ys[hi] + h11 * h * slopes[hi];
}

function profileBandPath(profile: TargetProfile, plot: ForcePlot): string {
  if (profile.shiftM.length < 2) return '';
  const top = profile.shiftM.map((shift, index) => `${index === 0 ? 'M' : 'L'} ${plot.x(shift)} ${plot.y(profile.forceN[index] + profile.toleranceN[index])}`);
  const bottom = profile.shiftM.slice().reverse().map((shift, reverseIndex) => {
    const index = profile.shiftM.length - 1 - reverseIndex;
    return `L ${plot.x(shift)} ${plot.y(profile.forceN[index] - profile.toleranceN[index])}`;
  });
  return [...top, ...bottom, 'Z'].join(' ');
}

function clamp(value: number, min: number, max: number): number {
  return Math.max(min, Math.min(max, value));
}
