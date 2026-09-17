import { useState } from 'react';
import {
  analyzePrimaryPathDomain,
  comparePrimaryPathDomains,
  type ArchitectureComparisonAnalysis,
  type FixedPivotArchitecture,
  type PackagingZone,
  type PrimaryPathDomainAnalysis,
} from '@api/primaryDesign';
import styles from './ArchitectureCompareExplorer.module.scss';

const MM = 1000;

type Witness = ArchitectureComparisonAnalysis['witnesses']['a_not_b'][number];

export function ArchitectureCompareExplorer({
  architecture,
  zones,
  domain,
}: {
  architecture: FixedPivotArchitecture;
  zones: PackagingZone[];
  domain: PrimaryPathDomainAnalysis;
}) {
  const [candidate, setCandidate] = useState<FixedPivotArchitecture>({ ...architecture });
  const [includeZones, setIncludeZones] = useState(true);
  const [candidateDomain, setCandidateDomain] = useState<PrimaryPathDomainAnalysis | null>(null);
  const [comparison, setComparison] = useState<ArchitectureComparisonAnalysis | null>(null);
  const [selectedWitness, setSelectedWitness] = useState<Witness | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const update = (patch: Partial<FixedPivotArchitecture>) => {
    setCandidate((value) => ({ ...value, ...patch }));
    setCandidateDomain(null);
    setComparison(null);
    setSelectedWitness(null);
  };

  const analyze = async () => {
    setLoading(true);
    setError(null);
    try {
      const b = await analyzePrimaryPathDomain(candidate, includeZones ? zones : [], {
        shift_station_count: 9,
        q_sample_count: 61,
        alpha_sample_count: 9,
        representative_path_count: 8,
        edge_audit_sample_count: 65,
        history_trace_sample_count: 65,
      });
      setCandidateDomain(b);
      const next = await comparePrimaryPathDomains(domain.domain_id, b.domain_id, { atlas_path_count: 32, mass_mix_count: 7 });
      setComparison(next);
      setSelectedWitness(next.witnesses.a_not_b[0] ?? next.witnesses.b_not_a[0] ?? null);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Architecture comparison failed.');
    } finally {
      setLoading(false);
    }
  };

  return <div className={styles.root}>
    <aside className={styles.controls}>
      <div className={styles.heading}>
        <strong>Architecture B</strong>
        <p>A is the currently analyzed architecture. Change B, then compare the complete force-shape behaviours each geometry can physically produce.</p>
      </div>
      <Field label="Pivot radius" value={candidate.pivot_radius_m * MM} suffix="mm" onChange={(value) => update({ pivot_radius_m: value / MM })} />
      <Field label="Arm length" value={candidate.arm_length_m * MM} suffix="mm" onChange={(value) => update({ arm_length_m: value / MM })} />
      <Field label="Roller radius" value={candidate.roller_radius_m * MM} suffix="mm" onChange={(value) => update({ roller_radius_m: value / MM })} />
      <Field label="Travel" value={candidate.required_travel_m * MM} suffix="mm" onChange={(value) => update({ required_travel_m: value / MM })} />
      <div className={styles.smallStatus}>Absolute RPM and flyweight mass scale are removed from the comparison. The question is whether one architecture can reproduce the same <em>shape</em> of force through shift as the other.</div>
      <label className={styles.checkbox}><input type="checkbox" checked={includeZones} onChange={(event) => { setIncludeZones(event.target.checked); setCandidateDomain(null); setComparison(null); setSelectedWitness(null); }} /><span>Apply Architecture A's packaging zones to B</span></label>
      <div className={styles.buttons}>
        <button type="button" onClick={() => { setCandidate({ ...architecture }); setCandidateDomain(null); setComparison(null); setSelectedWitness(null); }}>Copy A → B</button>
        <button type="button" className={styles.primary} disabled={loading} onClick={() => void analyze()}>{loading ? 'Building complete-path comparison…' : 'Compare architectures'}</button>
      </div>
      {candidateDomain && <div className={styles.smallStatus}>B domain built: {candidateDomain.history.certified_representative_path_count} initial certified representatives · {candidateDomain.graph.viable_layer_edge_counts.reduce((a, b) => a + b, 0).toLocaleString()} viable graph edges.</div>}
      {error && <div className={styles.error}>{error}</div>}
    </aside>

    <main className={styles.workspace}>
      {!comparison ? (
        <div className={styles.empty}>
          <strong>Compare the force shapes, not abstract coefficients</strong>
          <p>For every sampled complete ramp in one architecture, the tool searches the other architecture for the closest complete force-shape match after overall force scale is removed. The useful result is therefore a pair of curves and the two physical ramps behind them.</p>
        </div>
      ) : (
        <ComparisonView analysis={comparison} selectedWitness={selectedWitness} onSelectWitness={setSelectedWitness} />
      )}
    </main>
  </div>;
}

function ComparisonView({
  analysis,
  selectedWitness,
  onSelectWitness,
}: {
  analysis: ArchitectureComparisonAnalysis;
  selectedWitness: Witness | null;
  onSelectWitness: (w: Witness) => void;
}) {
  return <>
    <section className={styles.explainer}>
      <strong>How to read this comparison</strong>
      <p>Every force curve below is divided by its own mean force, so <b>1.0 means that curve's average force</b>. RPM and overall flyweight-mass scale therefore do not matter. A 5% RMS mismatch means the closest curve from the other architecture differs by about 5% of the source curve's mean force, on average, over the full shift.</p>
    </section>

    <div className={styles.summary}>
      <Metric label="Typical A behavior → closest B" value={formatPercent(analysis.summary.a_to_b_median_shape_distance)} />
      <Metric label="Hardest sampled A behavior → B" value={formatPercent(analysis.summary.a_to_b_max_shape_distance)} />
      <Metric label="Typical B behavior → closest A" value={formatPercent(analysis.summary.b_to_a_median_shape_distance)} />
      <Metric label="Hardest sampled B behavior → A" value={formatPercent(analysis.summary.b_to_a_max_shape_distance)} />
    </div>

    <section className={styles.card}>
      <div className={styles.cardHeader}>
        <div>
          <strong>Where the architectures actually differ</strong>
          <span>Select a complete behavior from one architecture and compare it with the closest complete behavior the other architecture can make.</span>
        </div>
      </div>

      <div className={styles.directionBlock}>
        <div className={styles.directionHeader}>
          <strong>A behaviours hardest for B to reproduce</strong>
          <span>These are not pointwise envelope differences; every example is a complete history-certified ramp.</span>
        </div>
        <div className={styles.witnessStrip}>
          {analysis.witnesses.a_not_b.map((w, i) => (
            <WitnessButton key={`a-${i}`} label={`A example ${i + 1}`} witness={w} selected={selectedWitness === w} onClick={() => onSelectWitness(w)} />
          ))}
          {!analysis.witnesses.a_not_b.length && <span className={styles.noWitness}>No A→B witness examples returned.</span>}
        </div>
      </div>

      <div className={styles.directionBlock}>
        <div className={styles.directionHeader}>
          <strong>B behaviours hardest for A to reproduce</strong>
          <span>This is the reverse question; the comparison is intentionally directional.</span>
        </div>
        <div className={styles.witnessStrip}>
          {analysis.witnesses.b_not_a.map((w, i) => (
            <WitnessButton key={`b-${i}`} label={`B example ${i + 1}`} witness={w as Witness} selected={selectedWitness === w} onClick={() => onSelectWitness(w as Witness)} />
          ))}
          {!analysis.witnesses.b_not_a.length && <span className={styles.noWitness}>No B→A witness examples returned.</span>}
        </div>
      </div>

      {selectedWitness && <WitnessInspector witness={selectedWitness} />}
    </section>

    <details className={styles.advanced}>
      <summary>Advanced capability diagnostics</summary>
      <p>The plots below are useful for numerical/research diagnosis, but they are not needed to answer the design question above. The coefficient footprint is a compressed map of curve shapes; the leverage plot shows normalized force-generating magnitude through shift before overall mass/RPM scaling.</p>
      <div className={styles.advancedGrid}>
        <section className={styles.advancedCard}>
          <strong>Compressed shape-space footprint</strong>
          <span>c₁ and c₂ are only visualization coordinates. Full-curve RMS is still used for the actual A↔B matching.</span>
          <ShapeFootprint analysis={analysis} />
        </section>
        <section className={styles.advancedCard}>
          <strong>Specific leverage envelope</strong>
          <span>Normalized force gain per kg and per ω² through shift.</span>
          <LeveragePlot analysis={analysis} />
        </section>
      </div>
      <p className={styles.note}>{analysis.definition.sampling_note}</p>
    </details>
  </>;
}

function WitnessButton({
  label,
  witness,
  selected,
  onClick,
}: {
  label: string;
  witness: Witness;
  selected: boolean;
  onClick: () => void;
}) {
  return <button type="button" className={selected ? styles.witnessSelected : styles.witness} onClick={onClick}>
    <strong>{label}</strong>
    <span>{formatPercent(witness.shape_distance)} RMS mismatch</span>
    <em>worst point {(100 * witness.max_pointwise_shape_gap).toFixed(1)}% · near {(100 * witness.gap_shift_fraction).toFixed(0)}% shift</em>
  </button>;
}

function WitnessInspector({ witness }: { witness: Witness }) {
  const width = 820;
  const height = 330;
  const pad = { left: 60, right: 24, top: 24, bottom: 46 };
  const values = [...witness.source.normalized_shape, ...witness.nearest.normalized_shape, 1];
  const min = Math.min(...values);
  const max = Math.max(...values);
  const span = Math.max(max - min, .05);
  const lo = Math.max(0, min - .12 * span);
  const hi = max + .12 * span;
  const sx = (v: number) => pad.left + v * (width - pad.left - pad.right);
  const sy = (v: number) => height - pad.bottom - (v - lo) / Math.max(hi - lo, .05) * (height - pad.top - pad.bottom);
  const yTicks = niceTicks(lo, hi, 5);
  const xTicks = [0, .25, .5, .75, 1];

  return <div className={styles.witnessInspector}>
    <div className={styles.witnessText}>
      <strong>{witness.source_architecture} behavior vs closest {witness.nearest_architecture} behavior</strong>
      <span>Whole-curve RMS mismatch {formatPercent(witness.shape_distance)} · largest local difference {(100 * witness.max_pointwise_shape_gap).toFixed(1)}% of mean force near {(100 * witness.gap_shift_fraction).toFixed(0)}% shift.</span>
      <p>If the solid and dashed curves nearly overlap, the two architectures can make essentially the same force progression after retuning mass/RPM scale. Where they separate, the geometry is imposing a real force-shape difference in the sampled complete-path domain.</p>
    </div>

    <div className={styles.witnessGrid}>
      <div>
        <div className={styles.miniTitle}>
          <strong>Force shape through shift</strong>
          <span>1.0 = each curve's own average force</span>
        </div>
        <svg viewBox={`0 0 ${width} ${height}`}>
          {yTicks.map((tick) => <g key={tick}>
            <line x1={pad.left} x2={width - pad.right} y1={sy(tick)} y2={sy(tick)} className={styles.gridLine} />
            <text x={pad.left - 9} y={sy(tick) + 4} textAnchor="end" className={styles.axisText}>{tick.toFixed(2)}</text>
          </g>)}
          {xTicks.map((tick) => <g key={tick}>
            <line x1={sx(tick)} x2={sx(tick)} y1={pad.top} y2={height - pad.bottom} className={styles.gridLine} />
            <text x={sx(tick)} y={height - 18} textAnchor="middle" className={styles.axisText}>{Math.round(tick * 100)}%</text>
          </g>)}
          <line x1={pad.left} x2={width - pad.right} y1={sy(1)} y2={sy(1)} className={styles.meanLine} />
          <path d={line(witness.source.shift_fraction, witness.source.normalized_shape, sx, sy)} className={styles.witnessSourceLine} />
          <path d={line(witness.nearest.shift_fraction, witness.nearest.normalized_shape, sx, sy)} className={styles.witnessNearestLine} />
          <text transform={`translate(17 ${height / 2}) rotate(-90)`} textAnchor="middle" className={styles.axisTitle}>force / mean force</text>
          <text x={(pad.left + width - pad.right) / 2} y={height - 3} textAnchor="middle" className={styles.axisTitle}>shift progress</text>
        </svg>
        <div className={styles.curveLegend}>
          <span className={styles.sourceLegend}>{witness.source_architecture} source behavior</span>
          <span className={styles.nearestLegend}>closest {witness.nearest_architecture} behavior</span>
        </div>
      </div>

      <div>
        <div className={styles.miniTitle}>
          <strong>Physical ramps behind those curves</strong>
          <span>same axial/radial scale</span>
        </div>
        <WitnessRampPlot witness={witness} />
        <div className={styles.curveLegend}>
          <span className={styles.sourceLegend}>{witness.source_architecture} ramp</span>
          <span className={styles.nearestLegend}>{witness.nearest_architecture} closest ramp</span>
        </div>
      </div>
    </div>
  </div>;
}

function WitnessRampPlot({ witness }: { witness: Witness }) {
  const width = 820;
  const height = 330;
  const pad = 42;
  const source = witness.source.ramp.ramp_surface;
  const nearest = witness.nearest.ramp.ramp_surface;
  const xs = [...source.x_m, ...nearest.x_m];
  const rs = [...source.r_m, ...nearest.r_m];
  if (!xs.length || !rs.length) return <div className={styles.empty}>No physical witness geometry.</div>;
  const xMin = Math.min(...xs);
  const xMax = Math.max(...xs);
  const rMin = Math.min(...rs);
  const rMax = Math.max(...rs);
  const xSpan = Math.max(xMax - xMin, 1e-4);
  const rSpan = Math.max(rMax - rMin, 1e-4);
  const scale = Math.min((width - 2 * pad) / xSpan, (height - 2 * pad) / rSpan);
  const sx = (v: number) => pad + (v - xMin) * scale;
  const sy = (v: number) => height - pad - (v - rMin) * scale;
  return <svg viewBox={`0 0 ${width} ${height}`}>
    <path d={line(source.x_m, source.r_m, sx, sy)} className={styles.witnessSourceLine} />
    <path d={line(nearest.x_m, nearest.r_m, sx, sy)} className={styles.witnessNearestLine} />
    <text x={width / 2} y={height - 7} textAnchor="middle" className={styles.axisText}>physical ramp geometry · common scale</text>
  </svg>;
}

function ShapeFootprint({ analysis }: { analysis: ArchitectureComparisonAnalysis }) {
  const width = 820, height = 360, pad = 44;
  const points = [...analysis.architecture_a.footprint.points, ...analysis.architecture_b.footprint.points];
  const c1 = points.map((p) => p.c1), c2 = points.map((p) => p.c2);
  const minX = Math.min(...c1, -0.1), maxX = Math.max(...c1, 0.1), minY = Math.min(...c2, -0.1), maxY = Math.max(...c2, 0.1);
  const dx = Math.max(maxX - minX, .1), dy = Math.max(maxY - minY, .1);
  const sx = (v: number) => pad + (v - (minX - .08 * dx)) / (1.16 * dx) * (width - 2 * pad);
  const sy = (v: number) => height - pad - (v - (minY - .08 * dy)) / (1.16 * dy) * (height - 2 * pad);
  const hull = (rows: number[][]) => rows.length ? `${rows.map((row, i) => `${i ? 'L' : 'M'} ${sx(row[0])} ${sy(row[1])}`).join(' ')} Z` : '';
  return <svg className={styles.shapePlot} viewBox={`0 0 ${width} ${height}`}>
    <line x1={sx(0)} x2={sx(0)} y1={pad} y2={height - pad} className={styles.axis} />
    <line x1={pad} x2={width - pad} y1={sy(0)} y2={sy(0)} className={styles.axis} />
    <path d={hull(analysis.architecture_a.footprint.hull_c1_c2)} className={styles.hullA} />
    <path d={hull(analysis.architecture_b.footprint.hull_c1_c2)} className={styles.hullB} />
    {analysis.architecture_a.footprint.points.map((point, i) => <circle key={`a-${i}`} cx={sx(point.c1)} cy={sy(point.c2)} r={2.3} className={styles.pointA} />)}
    {analysis.architecture_b.footprint.points.map((point, i) => <circle key={`b-${i}`} cx={sx(point.c1)} cy={sy(point.c2)} r={2.3} className={styles.pointB} />)}
    <text x={width / 2} y={height - 8} textAnchor="middle" className={styles.axisText}>compressed progression coordinate c₁</text>
    <text transform={`translate(14 ${height / 2}) rotate(-90)`} textAnchor="middle" className={styles.axisText}>compressed curvature coordinate c₂</text>
  </svg>;
}

function LeveragePlot({ analysis }: { analysis: ArchitectureComparisonAnalysis }) {
  const width = 820, height = 300, pad = 44;
  const a = analysis.architecture_a.specific_leverage_envelope;
  const b = analysis.architecture_b.specific_leverage_envelope;
  const values = [...a.min, ...a.max, ...b.min, ...b.max].filter(Number.isFinite);
  if (!values.length) return <div className={styles.empty}>No leverage samples.</div>;
  const min = Math.min(...values), max = Math.max(...values), span = Math.max(max - min, 1e-9);
  const sx = (v: number) => pad + v * (width - 2 * pad);
  const sy = (v: number) => height - pad - (v - min) / span * (height - 2 * pad);
  return <svg className={styles.leveragePlot} viewBox={`0 0 ${width} ${height}`}>
    <path d={area(a.shift_fraction, a.min, a.max, sx, sy)} className={styles.bandA} />
    <path d={area(b.shift_fraction, b.min, b.max, sx, sy)} className={styles.bandB} />
    <path d={line(a.shift_fraction, a.median, sx, sy)} className={styles.lineA} />
    <path d={line(b.shift_fraction, b.median, sx, sy)} className={styles.lineB} />
    <text x={width / 2} y={height - 8} textAnchor="middle" className={styles.axisText}>normalized shift</text>
  </svg>;
}

function Field({
  label,
  value,
  suffix,
  step = .5,
  onChange,
}: {
  label: string;
  value: number;
  suffix: string;
  step?: number;
  onChange: (v: number) => void;
}) {
  return <label className={styles.field}>
    <span>{label}</span>
    <div><input type="number" value={Number.isInteger(step) ? value.toFixed(0) : value.toFixed(2)} step={step} onChange={(event) => onChange(Number(event.target.value))} /><em>{suffix}</em></div>
  </label>;
}

function Metric({ label, value }: { label: string; value: string }) {
  return <div><span>{label}</span><strong>{value}</strong></div>;
}

function formatPercent(value: number | null) {
  return value == null ? '—' : `${(100 * value).toFixed(value < .01 ? 2 : 1)}%`;
}

function line(xs: number[], ys: number[], sx: (x: number) => number, sy: (y: number) => number) {
  return xs.map((x, i) => `${i ? 'L' : 'M'} ${sx(x)} ${sy(ys[i])}`).join(' ');
}

function area(xs: number[], lo: number[], hi: number[], sx: (x: number) => number, sy: (y: number) => number) {
  if (!xs.length) return '';
  return `${line(xs, hi, sx, sy)} ${[...xs].reverse().map((x, ri) => {
    const i = xs.length - 1 - ri;
    return `L ${sx(x)} ${sy(lo[i])}`;
  }).join(' ')} Z`;
}

function niceTicks(min: number, max: number, count: number) {
  const raw = (max - min) / Math.max(1, count - 1);
  const mag = 10 ** Math.floor(Math.log10(Math.max(raw, 1e-9)));
  const norm = raw / mag;
  const step = (norm <= 1 ? 1 : norm <= 2 ? 2 : norm <= 5 ? 5 : 10) * mag;
  const start = Math.ceil(min / step) * step;
  const rows: number[] = [];
  for (let value = start; value <= max + 1e-9; value += step) rows.push(value);
  return rows;
}
