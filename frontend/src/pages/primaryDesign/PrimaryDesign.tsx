import { useCallback, useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  analyzeConcretePrimaryDesign,
  analyzePrimaryArchitecture,
  analyzePrimaryPathDomain,
  evaluateConcretePrimaryDesign,
  getPrimaryDesignDefaults,
  type ArchitectureAnalysis,
  type ConcreteDesignAnalysis,
  type ConcreteDesignResponse,
  type FixedPivotArchitecture,
  type FixedPivotRamp,
  type HistoryCertifiedRampPath,
  type PackagingZone,
  type PrimaryDesignOperating,
  type PrimaryPathDomainAnalysis,
} from '@api/primaryDesign';
import { ArchitectureScene } from './ArchitectureScene';
import { ForceChart } from './ForceChart';
import { MechanismScene } from './MechanismScene';
import styles from './PrimaryDesign.module.scss';

const MM = 1000;
const G = 1000;
const RPM_PER_RAD_S = 60 / (2 * Math.PI);
const RAD_S_PER_RPM = 2 * Math.PI / 60;

type DesignMode = 'architecture' | 'concrete';

function interpolateNullable(
  axis: number[],
  values: Array<number | boolean | null>,
  x: number,
): number | null {
  const numeric = values.map((value) => typeof value === 'number' ? value : null);
  if (!axis.length || axis.length !== numeric.length) return null;
  if (x < axis[0] || x > axis[axis.length - 1]) return null;
  if (x === axis[0]) return numeric[0];
  if (x === axis[axis.length - 1]) return numeric[numeric.length - 1];
  let lo = 0;
  let hi = axis.length - 1;
  while (hi - lo > 1) {
    const mid = Math.floor((lo + hi) / 2);
    if (axis[mid] <= x) lo = mid;
    else hi = mid;
  }
  const a = numeric[lo];
  const b = numeric[hi];
  if (a === null || b === null) return null;
  const span = axis[hi] - axis[lo];
  const t = span === 0 ? 0 : (x - axis[lo]) / span;
  return a + t * (b - a);
}

function fmt(value: number | null, digits = 1): string {
  return value === null || !Number.isFinite(value) ? '—' : value.toFixed(digits);
}

function minmax(values: number[]): { min: number; max: number } | null {
  if (!values.length) return null;
  let min = values[0];
  let max = values[0];
  for (const value of values) {
    if (value < min) min = value;
    if (value > max) max = value;
  }
  return { min, max };
}

export const PrimaryDesign = () => {
  const navigate = useNavigate();
  const [mode, setMode] = useState<DesignMode>('architecture');
  const [architecture, setArchitecture] = useState<FixedPivotArchitecture | null>(null);
  const [ramp, setRamp] = useState<FixedPivotRamp | null>(null);
  const [zones, setZones] = useState<PackagingZone[]>([]);
  const [operating, setOperating] = useState<PrimaryDesignOperating | null>(null);
  const [architectureAnalysis, setArchitectureAnalysis] = useState<ArchitectureAnalysis | null>(null);
  const [pathDomain, setPathDomain] = useState<PrimaryPathDomainAnalysis | null>(null);
  const [analysis, setAnalysis] = useState<ConcreteDesignAnalysis | null>(null);
  const [response, setResponse] = useState<ConcreteDesignResponse | null>(null);
  const [selectedZoneId, setSelectedZoneId] = useState<string | null>(null);
  const [selectedRepresentativeIndex, setSelectedRepresentativeIndex] = useState(0);
  const [showLocalWorkspace, setShowLocalWorkspace] = useState(true);
  const [showRepresentativeFamily, setShowRepresentativeFamily] = useState(true);
  const [shiftM, setShiftM] = useState(0);
  const [architectureDirty, setArchitectureDirty] = useState(false);
  const [pathDomainDirty, setPathDomainDirty] = useState(true);
  const [geometryDirty, setGeometryDirty] = useState(false);
  const [architectureLoading, setArchitectureLoading] = useState(false);
  const [pathDomainLoading, setPathDomainLoading] = useState(false);
  const [geometryLoading, setGeometryLoading] = useState(false);
  const [responseLoading, setResponseLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const analyzeArchitecture = useCallback(async (
    nextArchitecture: FixedPivotArchitecture,
    nextZones: PackagingZone[],
  ) => {
    setArchitectureLoading(true);
    setError(null);
    try {
      const next = await analyzePrimaryArchitecture(nextArchitecture, nextZones, 361, 41);
      setArchitectureAnalysis(next);
      setArchitectureDirty(false);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Architecture analysis failed.');
    } finally {
      setArchitectureLoading(false);
    }
  }, []);

  const analyzePathDomain = useCallback(async (
    nextArchitecture: FixedPivotArchitecture,
    nextZones: PackagingZone[],
  ) => {
    setPathDomainLoading(true);
    setError(null);
    try {
      const next = await analyzePrimaryPathDomain(nextArchitecture, nextZones, {
        shift_station_count: 9,
        q_sample_count: 61,
        alpha_sample_count: 7,
        representative_path_count: 8,
        edge_audit_sample_count: 65,
        history_trace_sample_count: 65,
      });
      setPathDomain(next);
      setPathDomainDirty(false);
      setSelectedRepresentativeIndex(0);
    } catch (caught) {
      setPathDomain(null);
      setError(caught instanceof Error ? caught.message : 'Path-domain analysis failed.');
    } finally {
      setPathDomainLoading(false);
    }
  }, []);

  const analyzeConcrete = useCallback(async (
    nextArchitecture: FixedPivotArchitecture,
    nextRamp: FixedPivotRamp,
    nextOperating: PrimaryDesignOperating,
  ) => {
    setGeometryLoading(true);
    setError(null);
    try {
      const nextAnalysis = await analyzeConcretePrimaryDesign(nextArchitecture, nextRamp, 161);
      setAnalysis(nextAnalysis);
      setResponse(null);
      setGeometryDirty(false);
      setShiftM((value) => Math.min(value, nextArchitecture.required_travel_m));
      setResponseLoading(true);
      const nextResponse = await evaluateConcretePrimaryDesign(nextAnalysis.analysis_id, nextOperating);
      setResponse(nextResponse);
    } catch (caught) {
      setAnalysis(null);
      setResponse(null);
      setError(caught instanceof Error ? caught.message : 'Primary design analysis failed.');
    } finally {
      setGeometryLoading(false);
      setResponseLoading(false);
    }
  }, []);

  useEffect(() => {
    let active = true;
    void getPrimaryDesignDefaults()
      .then(async (defaults) => {
        if (!active) return;
        setArchitecture(defaults.architecture);
        setRamp(defaults.ramp);
        setZones(defaults.packaging_zones);
        setOperating(defaults.operating);
        await Promise.all([
          analyzeArchitecture(defaults.architecture, defaults.packaging_zones),
          analyzeConcrete(defaults.architecture, defaults.ramp, defaults.operating),
        ]);
      })
      .catch((caught: unknown) => {
        if (active) setError(caught instanceof Error ? caught.message : 'Could not load primary design defaults.');
      });
    return () => { active = false; };
  }, [analyzeArchitecture, analyzeConcrete]);

  useEffect(() => {
    if (!analysis || !operating || geometryDirty) return undefined;
    const handle = window.setTimeout(() => {
      setResponseLoading(true);
      void evaluateConcretePrimaryDesign(analysis.analysis_id, operating)
        .then(setResponse)
        .catch((caught: unknown) => setError(caught instanceof Error ? caught.message : 'Load response failed.'))
        .finally(() => setResponseLoading(false));
    }, 70);
    return () => window.clearTimeout(handle);
  }, [analysis, operating, geometryDirty]);

  useEffect(() => {
    const maxIndex = Math.max(0, (pathDomain?.representative_paths.length ?? 1) - 1);
    setSelectedRepresentativeIndex((current) => Math.min(current, maxIndex));
  }, [pathDomain]);

  const current = useMemo(() => {
    if (!analysis) return null;
    const axis = analysis.geometry.axis_values;
    const q = interpolateNullable(axis, analysis.geometry.fields.arm_angle_deg ?? [], shiftM);
    const tangent = interpolateNullable(axis, analysis.geometry.fields.ramp_tangent_deg ?? [], shiftM);
    const loads = response?.loads;
    return {
      q,
      tangent,
      closing: loads ? interpolateNullable(loads.axis_values, loads.fields.flyweight_total_closing_force_N ?? [], shiftM) : null,
      normal: loads ? interpolateNullable(loads.axis_values, loads.fields.ramp_force_normal_N ?? [], shiftM) : null,
      pivot: loads ? interpolateNullable(loads.axis_values, loads.fields.pivot_reaction_resultant_N ?? [], shiftM) : null,
    };
  }, [analysis, response, shiftM]);

  if (!architecture || !ramp || !operating) {
    return <div className={styles.page}><div className={styles.loading}>Loading primary design tool…</div></div>;
  }

  const updateArchitecture = (patch: Partial<FixedPivotArchitecture>) => {
    setArchitecture((value) => value ? { ...value, ...patch } : value);
    setArchitectureDirty(true);
    setPathDomainDirty(true);
    setGeometryDirty(true);
  };
  const updateRamp = (patch: Partial<FixedPivotRamp>) => {
    setRamp((value) => value ? { ...value, ...patch } : value);
    setGeometryDirty(true);
  };
  const updateZones = (nextZones: PackagingZone[]) => {
    setZones(nextZones);
    setArchitectureDirty(true);
    setPathDomainDirty(true);
  };
  const updateZone = (zoneId: string, patch: Partial<PackagingZone>) => {
    updateZones(zones.map((zone) => zone.id === zoneId ? { ...zone, ...patch } : zone));
  };
  const updateOperating = (patch: Partial<PrimaryDesignOperating>) => {
    setOperating((value) => value ? { ...value, ...patch } : value);
  };
  const contactActive = analysis
    ? shiftM <= analysis.contact_valid_travel_m + 1.0e-10
    : false;

  return (
    <div className={styles.page}>
      <header className={styles.header}>
        <div>
          <button type="button" className={styles.back} onClick={() => navigate('/')}>← Simulator</button>
          <h1>Fixed-Pivot Primary Design</h1>
          <p>Architecture packaging, exact roller contact, flyweight force, and structural-load inspection.</p>
        </div>
        <div className={styles.phaseBadge}>Path-domain exploration · Phase 3.3</div>
      </header>

      <div className={styles.modeTabs}>
        <button type="button" className={mode === 'architecture' ? styles.modeTabActive : styles.modeTab} onClick={() => setMode('architecture')}>
          Architecture
        </button>
        <button type="button" className={mode === 'concrete' ? styles.modeTabActive : styles.modeTab} onClick={() => setMode('concrete')}>
          Concrete design
        </button>
      </div>

      {error && <div className={styles.error}>{error}</div>}

      {mode === 'architecture' ? (
        <ArchitectureMode
          architecture={architecture}
          zones={zones}
          analysis={architectureAnalysis}
          pathDomain={pathDomain}
          dirty={architectureDirty}
          pathDomainDirty={pathDomainDirty}
          loading={architectureLoading}
          pathDomainLoading={pathDomainLoading}
          selectedZoneId={selectedZoneId}
          selectedRepresentativeIndex={selectedRepresentativeIndex}
          showLocalWorkspace={showLocalWorkspace}
          showRepresentativeFamily={showRepresentativeFamily}
          onArchitectureChange={updateArchitecture}
          onZonesChange={updateZones}
          onZoneChange={updateZone}
          onSelectedZoneChange={setSelectedZoneId}
          onSelectedRepresentativeIndexChange={setSelectedRepresentativeIndex}
          onShowLocalWorkspaceChange={setShowLocalWorkspace}
          onShowRepresentativeFamilyChange={setShowRepresentativeFamily}
          onAnalyze={() => void analyzeArchitecture(architecture, zones)}
          onAnalyzePathDomain={() => void analyzePathDomain(architecture, zones)}
        />
      ) : (
        <ConcreteMode
          architecture={architecture}
          ramp={ramp}
          operating={operating}
          analysis={analysis}
          response={response}
          shiftM={shiftM}
          geometryDirty={geometryDirty}
          geometryLoading={geometryLoading}
          responseLoading={responseLoading}
          contactActive={contactActive}
          current={current}
          onRampChange={updateRamp}
          onOperatingChange={updateOperating}
          onShiftChange={setShiftM}
          onAnalyze={() => void analyzeConcrete(architecture, ramp, operating)}
        />
      )}
    </div>
  );
};

function ArchitectureMode({
  architecture,
  zones,
  analysis,
  pathDomain,
  dirty,
  pathDomainDirty,
  loading,
  pathDomainLoading,
  selectedZoneId,
  selectedRepresentativeIndex,
  showLocalWorkspace,
  showRepresentativeFamily,
  onArchitectureChange,
  onZonesChange,
  onZoneChange,
  onSelectedZoneChange,
  onSelectedRepresentativeIndexChange,
  onShowLocalWorkspaceChange,
  onShowRepresentativeFamilyChange,
  onAnalyze,
  onAnalyzePathDomain,
}: {
  architecture: FixedPivotArchitecture;
  zones: PackagingZone[];
  analysis: ArchitectureAnalysis | null;
  pathDomain: PrimaryPathDomainAnalysis | null;
  dirty: boolean;
  pathDomainDirty: boolean;
  loading: boolean;
  pathDomainLoading: boolean;
  selectedZoneId: string | null;
  selectedRepresentativeIndex: number;
  showLocalWorkspace: boolean;
  showRepresentativeFamily: boolean;
  onArchitectureChange: (patch: Partial<FixedPivotArchitecture>) => void;
  onZonesChange: (zones: PackagingZone[]) => void;
  onZoneChange: (zoneId: string, patch: Partial<PackagingZone>) => void;
  onSelectedZoneChange: (zoneId: string | null) => void;
  onSelectedRepresentativeIndexChange: (value: number) => void;
  onShowLocalWorkspaceChange: (value: boolean) => void;
  onShowRepresentativeFamilyChange: (value: boolean) => void;
  onAnalyze: () => void;
  onAnalyzePathDomain: () => void;
}) {
  const selectedPath = pathDomain?.representative_paths[selectedRepresentativeIndex] ?? null;
  const selectedQRange = selectedPath ? minmax(selectedPath.q_deg) : null;
  const selectedTangentRange = selectedPath ? minmax(selectedPath.ramp_tangent_deg) : null;

  return (
    <main className={styles.layout}>
      <aside className={styles.sidebar}>
        <section className={styles.card}>
          <div className={styles.cardTitleRow}>
            <h2>Architecture</h2>
            {dirty && <span className={styles.dirty}>reanalyze</span>}
          </div>
          <div className={styles.twoCol}>
            <NumberField label="Pivot radius" suffix="mm" value={architecture.pivot_radius_m * MM} min={0.5} step={0.5} onChange={(value) => onArchitectureChange({ pivot_radius_m: value / MM })} />
            <Readout label="Axial reference" value="pivot at x = 0" />
          </div>
          <div className={styles.twoCol}>
            <NumberField label="Arm length" suffix="mm" value={architecture.arm_length_m * MM} min={2} step={0.5} onChange={(value) => onArchitectureChange({ arm_length_m: value / MM })} />
            <NumberField label="Roller radius" suffix="mm" value={architecture.roller_radius_m * MM} min={0.5} step={0.25} onChange={(value) => onArchitectureChange({ roller_radius_m: value / MM })} />
          </div>
          <div className={styles.twoCol}>
            <NumberField label="Required travel" suffix="mm" value={architecture.required_travel_m * MM} min={0.5} step={0.5} onChange={(value) => onArchitectureChange({ required_travel_m: value / MM })} />
            <NumberField label="Max tip mass" suffix="g" value={architecture.max_tip_mass_per_flyweight_kg * G} min={0} step={5} onChange={(value) => onArchitectureChange({ max_tip_mass_per_flyweight_kg: value / G })} />
          </div>
          <div className={styles.twoCol}>
            <NumberField label="Flyweights" suffix="#" value={architecture.number_of_flyweights} min={1} step={1} onChange={(value) => onArchitectureChange({ number_of_flyweights: Math.max(1, Math.round(value)) })} />
            <NumberField label="Arm mass / flyweight" suffix="g" value={architecture.arm_mass_per_flyweight_kg * G} min={0} step={0.25} onChange={(value) => onArchitectureChange({ arm_mass_per_flyweight_kg: value / G })} />
          </div>
          <button type="button" className={styles.primaryButton} disabled={loading} onClick={onAnalyze}>
            {loading ? 'Analyzing architecture…' : 'Analyze architecture'}
          </button>
          <p className={styles.helpText}>Architecture is ramp-independent: q spans -30° to 90° over the full required travel. Drag either dotted roller path to change only the arm radius; the backend refreshes the roller and possible-ramp workspaces when you analyze.</p>
        </section>

        <section className={styles.card}>
          <div className={styles.cardTitleRow}>
            <h2>Packaging zones</h2>
            <span>{zones.length}</span>
          </div>
          {zones.length === 0 && <p className={styles.helpText}>Draw allowed regions or keep-outs directly in the engineering view. Use a ramp keep-out around the pivot/hub or other hardware; the architecture layer intentionally does not invent a body thickness or pivot housing radius.</p>}
          <div className={styles.zoneList}>
            {zones.map((zone) => (
              <div key={zone.id} className={zone.id === selectedZoneId ? styles.zoneEditorSelected : styles.zoneEditor}>
                <button type="button" className={styles.zoneSelectButton} onClick={() => onSelectedZoneChange(zone.id)}>{zone.label}</button>
                <input className={styles.inlineInput} value={zone.label} onChange={(event) => onZoneChange(zone.id, { label: event.target.value })} />
                <div className={styles.twoCol}>
                  <label className={styles.field}>
                    <span>Subject</span>
                    <select value={zone.subject} onChange={(event) => onZoneChange(zone.id, { subject: event.target.value as PackagingZone['subject'] })}>
                      <option value="flyweight">Flyweight</option>
                      <option value="ramp">Ramp</option>
                    </select>
                  </label>
                  <label className={styles.field}>
                    <span>Rule</span>
                    <select value={zone.rule} onChange={(event) => onZoneChange(zone.id, { rule: event.target.value as PackagingZone['rule'] })}>
                      <option value="forbid">Keep-out</option>
                      <option value="contain">Must stay inside</option>
                    </select>
                  </label>
                </div>
                <NumberField label="Clearance" suffix="mm" value={zone.clearance_m * MM} min={0} step={0.25} onChange={(value) => onZoneChange(zone.id, { clearance_m: value / MM })} />
              </div>
            ))}
          </div>
        </section>

        <section className={styles.card}>
          <div className={styles.cardTitleRow}>
            <h2>Path-domain explorer</h2>
            {pathDomainDirty ? <span className={styles.dirty}>stale</span> : pathDomain ? <PathDomainBadge analysis={pathDomain} /> : <span className={styles.locked}>not analyzed</span>}
          </div>
          <button type="button" className={styles.primaryButton} disabled={pathDomainLoading} onClick={onAnalyzePathDomain}>
            {pathDomainLoading ? 'Analyzing ramp paths…' : 'Analyze ramp domain'}
          </button>
          <p className={styles.helpText}>This is the first exact-valid ramp-family exploration layer. It shows representative complete paths that survive the local graph plus the Phase-3.2 history checks, rather than only the Phase-2 local geometric workspace.</p>
          {pathDomain && (
            <>
              <div className={styles.archMetrics}>
                <Metric label="Certified paths" value={String(pathDomain.history.certified_representative_path_count)} />
                <Metric label="Candidate paths" value={String(pathDomain.history.candidate_complete_path_count)} />
                <Metric label="Local templates" value={String(pathDomain.graph.local_transition_template_count)} />
                <Metric label="History rejections" value={String(pathDomain.history.history_rejection_count)} />
              </div>
              {pathDomain.representative_paths.length > 0 && (
                <>
                  <label className={styles.field}>
                    <span>Representative path</span>
                    <select value={selectedRepresentativeIndex} onChange={(event) => onSelectedRepresentativeIndexChange(Number(event.target.value))}>
                      {pathDomain.representative_paths.map((path, index) => (
                        <option key={index} value={index}>
                          Path {index + 1} · q {path.q_deg[0].toFixed(1)}° → {path.q_deg[path.q_deg.length - 1].toFixed(1)}°
                        </option>
                      ))}
                    </select>
                  </label>
                  <div className={styles.checkboxStack}>
                    <label className={styles.checkboxRow}>
                      <input type="checkbox" checked={showLocalWorkspace} onChange={(event) => onShowLocalWorkspaceChange(event.target.checked)} />
                      <span>Show Phase-2 local workspace underneath</span>
                    </label>
                    <label className={styles.checkboxRow}>
                      <input type="checkbox" checked={showRepresentativeFamily} onChange={(event) => onShowRepresentativeFamilyChange(event.target.checked)} />
                      <span>Show all representative ramps</span>
                    </label>
                  </div>
                </>
              )}
              {selectedPath && (
                <div className={styles.readoutGrid}>
                  <Readout label="q range" value={selectedQRange ? `${selectedQRange.min.toFixed(1)}° → ${selectedQRange.max.toFixed(1)}°` : '—'} />
                  <Readout label="Tangent range" value={selectedTangentRange ? `${selectedTangentRange.min.toFixed(1)}° → ${selectedTangentRange.max.toFixed(1)}°` : '—'} />
                  <Readout label="Max math roots" value={String(selectedPath.history.max_contact_root_count)} />
                  <Readout label="Multi-root shifts" value={String(selectedPath.history.multiple_root_shift_count)} />
                </div>
              )}
            </>
          )}
        </section>
      </aside>

      <div className={styles.workspace}>
        <section className={styles.card}>
          <ArchitectureScene
            architecture={architecture}
            analysis={analysis}
            pathDomain={pathDomain}
            selectedRepresentativePathIndex={selectedRepresentativeIndex}
            showLocalWorkspace={showLocalWorkspace}
            showRepresentativeFamily={showRepresentativeFamily}
            zones={zones}
            stale={dirty}
            selectedZoneId={selectedZoneId}
            onArchitectureChange={onArchitectureChange}
            onZonesChange={onZonesChange}
            onSelectedZoneChange={onSelectedZoneChange}
          />
        </section>

        <section className={styles.card}>
          <div className={styles.cardTitleRow}>
            <h2>Architecture admissibility</h2>
            {analysis && <ArchitectureBadge analysis={analysis} stale={dirty} />}
          </div>
          {analysis ? (
            <>
              <div className={styles.archMetrics}>
                <Metric label="Flyweight poses admitted" value={`${(analysis.summary.admissible_pose_fraction * 100).toFixed(1)} %`} />
                <Metric label="Ramp workspace retained" value={`${(analysis.summary.ramp_workspace_fraction * 100).toFixed(1)} %`} />
                <Metric label="Angle range" value={`${analysis.limits.q_min_deg.toFixed(0)}° → ${analysis.limits.q_max_deg.toFixed(0)}°`} />
                <Metric label="Travel" value={`${(architecture.required_travel_m * MM).toFixed(2)} mm`} />
              </div>
              <p className={styles.helpText}>Gold is the purely geometric one-sided finite-roller ramp-surface opportunity region. Green is what remains after ramp packaging zones. When the path-domain explorer is turned on, the exact-valid representative ramps are shown on top of this as a stronger subset.</p>
              <div className={styles.legendRow}>
                <span><i className={styles.legendReach} />roller-centre workspace</span>
                <span><i className={styles.legendRamp} />potential ramp surface</span>
                <span><i className={styles.legendAdmissible} />packaging-feasible ramp surface</span>
                <span><i className={styles.legendBlocked} />packaging-restricted pose</span>
              </div>
            </>
          ) : <div className={styles.loading}>Analyze the architecture to build its reach and packaging workspace.</div>}
        </section>

        {pathDomain && (
          <section className={styles.card}>
            <div className={styles.cardTitleRow}>
              <h2>Ramp-path exploration</h2>
              <span>{pathDomain.representative_paths.length} representative valid ramps</span>
            </div>
            <PathDomainPlot analysis={pathDomain} selectedRepresentativeIndex={selectedRepresentativeIndex} />
          </section>
        )}

        {pathDomain && (
          <section className={styles.card}>
            <div className={styles.cardTitleRow}>
              <h2>History and manual-test notes</h2>
              <span>{pathDomain.history.selection_rule}</span>
            </div>
            <div className={styles.readoutGrid}>
              <Readout label="Shift stations" value={String(pathDomain.graph.shift_station_count)} />
              <Readout label="q samples" value={String(pathDomain.graph.q_sample_count)} />
              <Readout label="Tangent samples" value={String(pathDomain.graph.alpha_sample_count)} />
              <Readout label="Trace samples" value={String(pathDomain.numerics.history_trace_sample_count)} />
            </div>
            {pathDomain.history.rejections.length > 0 && (
              <div className={styles.rejectionList}>
                {pathDomain.history.rejections.map((rejection, index) => {
                  const failure = (rejection.failure ?? null) as { code?: string; message?: string; shift_m?: number | null } | null;
                  return (
                    <div key={index} className={styles.rejectionRow}>
                      <strong>{failure?.code ?? 'REJECTED'}</strong>
                      <span>{failure?.message ?? 'This complete path did not survive the Phase-3.2 history checks.'}</span>
                      <em>{failure?.shift_m == null ? 'shift —' : `near ${(failure.shift_m * MM).toFixed(2)} mm`}</em>
                    </div>
                  );
                })}
              </div>
            )}
            <ul className={styles.deferredList}>
              {pathDomain.deferred_checks.map((item, index) => <li key={index}>{item}</li>)}
            </ul>
          </section>
        )}

        {analysis && analysis.zone_diagnostics.length > 0 && (
          <section className={styles.card}>
            <h2>Zone diagnostics</h2>
            <div className={styles.diagnosticList}>
              {analysis.zone_diagnostics.map((diagnostic) => (
                <div key={diagnostic.zone_id} className={styles.diagnosticRow}>
                  <div><strong>{diagnostic.label}</strong><span>{diagnostic.subject} · {diagnostic.rule}</span></div>
                  <span className={diagnostic.status === 'pass' ? styles.valid : diagnostic.status === 'restricts' ? styles.dirty : styles.invalid}>{diagnostic.status}</span>
                </div>
              ))}
            </div>
          </section>
        )}
      </div>
    </main>
  );
}

function ConcreteMode({
  architecture,
  ramp,
  operating,
  analysis,
  response,
  shiftM,
  geometryDirty,
  geometryLoading,
  responseLoading,
  contactActive,
  current,
  onRampChange,
  onOperatingChange,
  onShiftChange,
  onAnalyze,
}: {
  architecture: FixedPivotArchitecture;
  ramp: FixedPivotRamp;
  operating: PrimaryDesignOperating;
  analysis: ConcreteDesignAnalysis | null;
  response: ConcreteDesignResponse | null;
  shiftM: number;
  geometryDirty: boolean;
  geometryLoading: boolean;
  responseLoading: boolean;
  contactActive: boolean;
  current: { q: number | null; tangent: number | null; closing: number | null; normal: number | null; pivot: number | null } | null;
  onRampChange: (patch: Partial<FixedPivotRamp>) => void;
  onOperatingChange: (patch: Partial<PrimaryDesignOperating>) => void;
  onShiftChange: (value: number) => void;
  onAnalyze: () => void;
}) {
  return (
    <main className={styles.layout}>
      <aside className={styles.sidebar}>
        <section className={styles.card}>
          <div className={styles.cardTitleRow}>
            <h2>Architecture</h2>
            {geometryDirty && <span className={styles.dirty}>changed</span>}
          </div>
          <div className={styles.readoutGrid}>
            <Readout label="Pivot radius" value={`${(architecture.pivot_radius_m * MM).toFixed(2)} mm`} />
            <Readout label="Arm length" value={`${(architecture.arm_length_m * MM).toFixed(2)} mm`} />
            <Readout label="Roller radius" value={`${(architecture.roller_radius_m * MM).toFixed(2)} mm`} />
            <Readout label="Required travel" value={`${(architecture.required_travel_m * MM).toFixed(2)} mm`} />
            <Readout label="Flyweights" value={String(architecture.number_of_flyweights)} />
            <Readout label="Arm mass / flyweight" value={`${(architecture.arm_mass_per_flyweight_kg * G).toFixed(3)} g`} />
          </div>
        </section>

        <section className={styles.card}>
          <div className={styles.cardTitleRow}>
            <h2>Ramp geometry</h2>
            {geometryDirty && <span className={styles.dirty}>reanalyze</span>}
          </div>
          <label className={styles.field}>
            <span>Profile</span>
            <select value={ramp.kind} onChange={(event) => onRampChange({ kind: event.target.value as FixedPivotRamp['kind'] })}>
              <option value="progressive">Linear + C³ blend + circular</option>
              <option value="constant">Constant tangent</option>
            </select>
          </label>
          <NumberField label={ramp.kind === 'constant' ? 'Tangent' : 'Linear tangent'} suffix="°" value={ramp.linear_angle_deg} min={1} max={89} step={0.5} onChange={(value) => onRampChange({ linear_angle_deg: value })} />
          {ramp.kind === 'progressive' && (
            <div className={styles.twoCol}>
              <NumberField label="Circular start tangent" suffix="°" value={ramp.circular_start_angle_deg} min={1} max={89} step={0.5} onChange={(value) => onRampChange({ circular_start_angle_deg: value })} />
              <NumberField label="Circular end tangent" suffix="°" value={ramp.circular_end_angle_deg} min={1} max={89} step={0.5} onChange={(value) => onRampChange({ circular_end_angle_deg: value })} />
            </div>
          )}
          <NumberField label="Initial flyweight angle q₀" suffix="°" value={ramp.initial_flyweight_angle_deg} min={-30} max={89.5} step={0.25} onChange={(value) => onRampChange({ initial_flyweight_angle_deg: value })} />
          <p className={styles.helpText}>Ramp placement is derived from q₀, the initial tangent, the fixed pivot/arm geometry, and the finite roller. Point A is no longer a placement input.</p>
          {ramp.kind === 'progressive' ? (
            <div className={styles.threeCol}>
              <NumberField label="Linear" suffix="mm" value={ramp.linear_length_m * MM} min={0.5} step={0.5} onChange={(value) => onRampChange({ linear_length_m: value / MM })} />
              <NumberField label="C³ blend" suffix="mm" value={ramp.blend_length_m * MM} min={0.5} step={0.5} onChange={(value) => onRampChange({ blend_length_m: value / MM })} />
              <NumberField label="Circular" suffix="mm" value={ramp.circular_length_m * MM} min={0.5} step={0.5} onChange={(value) => onRampChange({ circular_length_m: value / MM })} />
            </div>
          ) : (
            <NumberField label="Ramp length" suffix="mm" value={ramp.constant_length_m * MM} min={0.5} step={0.5} onChange={(value) => onRampChange({ constant_length_m: value / MM })} />
          )}
          <button type="button" className={styles.primaryButton} disabled={geometryLoading} onClick={onAnalyze}>
            {geometryLoading ? 'Analyzing geometry…' : 'Analyze ramp'}
          </button>
        </section>

        <section className={styles.card}>
          <h2>Operating condition</h2>
          <SliderField label="Tip mass / flyweight" suffix="g" value={operating.tip_mass_per_flyweight_kg * G} min={0} max={Math.max(1, architecture.max_tip_mass_per_flyweight_kg * G)} step={1} onChange={(value) => onOperatingChange({ tip_mass_per_flyweight_kg: value / G })} />
          <SliderField label="Primary speed" suffix="rpm" value={operating.shaft_speed_rad_s * RPM_PER_RAD_S} min={0} max={6000} step={25} onChange={(value) => onOperatingChange({ shaft_speed_rad_s: value * RAD_S_PER_RPM })} />
          <NumberField label="Shift speed" suffix="mm/s" value={operating.shift_speed_m_s * MM} step={1} onChange={(value) => onOperatingChange({ shift_speed_m_s: value / MM })} />
          <NumberField label="Shift acceleration" suffix="m/s²" value={operating.shift_acceleration_m_s2} step={0.1} onChange={(value) => onOperatingChange({ shift_acceleration_m_s2: value })} />
          {responseLoading && <div className={styles.muted}>updating loads…</div>}
        </section>
      </aside>

      <div className={styles.workspace}>
        <section className={styles.card}>
          {analysis ? <MechanismScene analysis={analysis} shiftM={shiftM} /> : <div className={styles.loading}>Analyze a ramp to build the mechanism.</div>}
        </section>
        <section className={styles.card}>
          <div className={styles.shiftHeader}>
            <div><h2>Shift position</h2><span>{(shiftM * MM).toFixed(2)} / {(architecture.required_travel_m * MM).toFixed(2)} mm requested</span></div>
            {analysis && (!contactActive
              ? <span className={styles.invalid}>No contact at selected shift</span>
              : current?.q !== null && current?.q !== undefined && current.q > 90
                ? <span className={styles.invalid}>q &gt; 90° at selected shift</span>
                : <ValidityBadge analysis={analysis} />)}
          </div>
          <input className={styles.shiftSlider} type="range" min={0} max={Math.max(0.001, architecture.required_travel_m * MM)} step={0.05} value={Math.min(shiftM, architecture.required_travel_m) * MM} onChange={(event) => onShiftChange(Number(event.target.value) / MM)} />
          <div className={styles.metrics}>
            <Metric label="Arm angle q" value={`${fmt(current?.q ?? null, 2)}°`} />
            <Metric label="Ramp tangent" value={`${fmt(current?.tangent ?? null, 2)}°`} />
            <Metric label="Flyweight closing" value={`${fmt(current?.closing ?? null)} N`} />
            <Metric label="Ramp normal / ramp" value={`${fmt(current?.normal ?? null)} N`} />
            <Metric label="Pivot resultant / flyweight" value={`${fmt(current?.pivot ?? null)} N`} />
          </div>
        </section>
        <section className={styles.card}>
          <div className={styles.chartHeader}><div><h2>Loads through shift</h2><span>Geometry is solved on the backend; moving the shift cursor is local and instantaneous.</span></div></div>
          <ForceChart response={response} shiftM={shiftM} requestedTravelM={architecture.required_travel_m} contactValidTravelM={analysis?.contact_valid_travel_m ?? null} />
        </section>
      </div>
    </main>
  );
}

function PathDomainPlot({
  analysis,
  selectedRepresentativeIndex,
}: {
  analysis: PrimaryPathDomainAnalysis;
  selectedRepresentativeIndex: number;
}) {
  const selectedPath = analysis.representative_paths[selectedRepresentativeIndex] ?? null;
  const width = 920;
  const height = 280;
  const padLeft = 50;
  const padRight = 18;
  const padTop = 16;
  const padBottom = 38;
  const qMin = -30;
  const qMax = 90;
  const innerWidth = width - padLeft - padRight;
  const innerHeight = height - padTop - padBottom;
  const xScale = (shiftM: number) => padLeft + (analysis.architecture.required_travel_m <= 0 ? 0 : (shiftM / analysis.architecture.required_travel_m) * innerWidth);
  const yScale = (qDeg: number) => padTop + (qMax - qDeg) / (qMax - qMin) * innerHeight;
  const guideTicks = [-30, 0, 30, 60, 90];

  const corridor = (() => {
    const valid = analysis.graph.station_projection.filter((station) => station.active_q_min_deg !== null && station.active_q_max_deg !== null);
    if (valid.length < 2) return '';
    const xs = valid.map((station) => xScale((station.station / (analysis.graph.shift_station_count - 1)) * analysis.architecture.required_travel_m));
    const top = valid.map((station, index) => `${index === 0 ? 'M' : 'L'} ${xs[index]} ${yScale(station.active_q_max_deg as number)}`);
    const bottom = valid.slice().reverse().map((station, reverseIndex) => {
      const index = valid.length - 1 - reverseIndex;
      return `L ${xs[index]} ${yScale(station.active_q_min_deg as number)}`;
    });
    return [...top, ...bottom, 'Z'].join(' ');
  })();

  const stationCountPath = (() => {
    const values = analysis.graph.station_projection.map((station) => station.viable_state_count);
    const max = Math.max(...values, 1);
    const baseY = padTop + innerHeight;
    return analysis.graph.station_projection.map((station, index) => {
      const shift = (station.station / (analysis.graph.shift_station_count - 1)) * analysis.architecture.required_travel_m;
      const x = xScale(shift);
      const y = baseY - (station.viable_state_count / max) * 28;
      return `${index === 0 ? 'M' : 'L'} ${x} ${y}`;
    }).join(' ');
  })();

  return (
    <div className={styles.domainPlotWrap}>
      <svg viewBox={`0 0 ${width} ${height}`} className={styles.domainPlot} role="img" aria-label="Validated ramp-path domain plot">
        <rect width={width} height={height} rx="12" fill="var(--primary-design-canvas, #0d1319)" />
        {guideTicks.map((tick) => (
          <g key={tick}>
            <line x1={padLeft} y1={yScale(tick)} x2={width - padRight} y2={yScale(tick)} className={styles.domainGrid} />
            <text x={12} y={yScale(tick) + 4} className={styles.domainAxisLabel}>{tick}°</text>
          </g>
        ))}
        {[0, 0.25, 0.5, 0.75, 1].map((fraction) => {
          const shift = fraction * analysis.architecture.required_travel_m;
          const x = xScale(shift);
          return (
            <g key={fraction}>
              <line x1={x} y1={padTop} x2={x} y2={padTop + innerHeight} className={styles.domainGridVertical} />
              <text x={x} y={height - 12} textAnchor="middle" className={styles.domainAxisLabel}>{(shift * MM).toFixed(1)}</text>
            </g>
          );
        })}
        {corridor && <path d={corridor} className={styles.domainCorridor} />}
        <path d={stationCountPath} className={styles.domainStationCount} />
        {analysis.representative_paths.map((path, index) => {
          const d = path.shift_m.map((shift, pointIndex) => `${pointIndex === 0 ? 'M' : 'L'} ${xScale(shift)} ${yScale(path.q_deg[pointIndex])}`).join(' ');
          const className = index === selectedRepresentativeIndex ? styles.domainPathSelectedPlot : styles.domainPathFaintPlot;
          return <path key={index} d={d} className={className} />;
        })}
        {selectedPath && selectedPath.history.trace_shift_m.length > 0 && (
          <polyline
            points={selectedPath.history.trace_shift_m.map((shift, index) => `${xScale(shift)},${yScale(selectedPath.history.trace_q_deg[index])}`).join(' ')}
            className={styles.domainBranchTrace}
          />
        )}
        <text x={padLeft} y={height - 12} className={styles.domainAxisTitle}>shift (mm)</text>
        <text x={18} y={padTop + 10} className={styles.domainAxisTitle}>q(x)</text>
      </svg>
      <div className={styles.domainLegend}>
        <span><i className={styles.domainLegendCorridor} />stationwise active-q corridor</span>
        <span><i className={styles.domainLegendFamily} />representative valid ramps</span>
        <span><i className={styles.domainLegendSelected} />selected representative ramp</span>
        <span><i className={styles.domainLegendTrace} />history-selected branch trace</span>
        <span><i className={styles.domainLegendCounts} />viable-state count trend</span>
      </div>
    </div>
  );
}

function Readout({ label, value }: { label: string; value: string }) {
  return <div className={styles.readout}><span>{label}</span><strong>{value}</strong></div>;
}

function Metric({ label, value }: { label: string; value: string }) {
  return <div className={styles.metric}><span>{label}</span><strong>{value}</strong></div>;
}

function NumberField({
  label,
  suffix,
  value,
  min,
  max,
  step = 0.1,
  onChange,
}: {
  label: string;
  suffix: string;
  value: number;
  min?: number;
  max?: number;
  step?: number;
  onChange: (value: number) => void;
}) {
  return (
    <label className={styles.field}>
      <span>{label}</span>
      <div className={styles.numberWrap}>
        <input type="number" value={Number.isFinite(value) ? value : 0} min={min} max={max} step={step} onChange={(event) => onChange(Number(event.target.value))} />
        <em>{suffix}</em>
      </div>
    </label>
  );
}

function SliderField({
  label,
  suffix,
  value,
  min,
  max,
  step,
  onChange,
}: {
  label: string;
  suffix: string;
  value: number;
  min: number;
  max: number;
  step: number;
  onChange: (value: number) => void;
}) {
  return (
    <div className={styles.sliderField}>
      <div><span>{label}</span><strong>{value.toFixed(step < 1 ? 1 : 0)} {suffix}</strong></div>
      <input type="range" min={min} max={max} step={step} value={value} onChange={(event) => onChange(Number(event.target.value))} />
    </div>
  );
}

function ValidityBadge({ analysis }: { analysis: ConcreteDesignAnalysis }) {
  if (analysis.validity.valid) {
    const runtimeWarning = analysis.validity.warnings.some((warning) => warning.code === 'RUNTIME_MAP_COMPILE_FAILED');
    if (runtimeWarning) return <span className={styles.dirty}>Exact path valid · runtime-map warning</span>;
    return <span className={styles.valid}>Admissible full travel</span>;
  }
  return <span className={styles.invalid}>{analysis.validity.failure?.code ?? 'Inadmissible'}</span>;
}

function ArchitectureBadge({ analysis, stale }: { analysis: ArchitectureAnalysis; stale: boolean }) {
  if (stale) return <span className={styles.dirty}>stale</span>;
  if (!analysis.validity.valid) return <span className={styles.invalid}>workspace blocked</span>;
  return <span className={styles.valid}>architecture workspace valid</span>;
}

function PathDomainBadge({ analysis }: { analysis: PrimaryPathDomainAnalysis }) {
  if (!analysis.validity.valid) return <span className={styles.invalid}>no certified path</span>;
  return <span className={styles.valid}>history-certified domain</span>;
}
