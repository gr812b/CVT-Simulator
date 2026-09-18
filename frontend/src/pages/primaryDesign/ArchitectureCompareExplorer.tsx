import { useMemo, useRef, useState } from 'react';
import {
  analyzePrimaryPathDomain,
  comparePrimaryPathDomains,
  comparePrimaryPathDomainsToTarget,
  type ArchitectureComparisonAnalysis,
  type ArchitectureTargetComparisonAnalysis,
  type ArchitectureTargetMatch,
  type FixedPivotArchitecture,
  type PackagingZone,
  type PrimaryPathDomainAnalysis,
} from '@api/primaryDesign';
import styles from './ArchitectureCompareExplorer.module.scss';

const MM = 1000;
type TargetPoint = { shift_fraction: number; relative_force: number };
type DragState = { index: number; pointerId: number } | null;
type Witness = ArchitectureComparisonAnalysis['witnesses']['a_not_b'][number];

const PRESETS: Record<string, TargetPoint[]> = {
  Flat: [{ shift_fraction: 0, relative_force: 100 }, { shift_fraction: 1, relative_force: 100 }],
  Rising: [{ shift_fraction: 0, relative_force: 70 }, { shift_fraction: .25, relative_force: 82 }, { shift_fraction: .5, relative_force: 100 }, { shift_fraction: .75, relative_force: 122 }, { shift_fraction: 1, relative_force: 145 }],
  Falling: [{ shift_fraction: 0, relative_force: 145 }, { shift_fraction: .25, relative_force: 122 }, { shift_fraction: .5, relative_force: 100 }, { shift_fraction: .75, relative_force: 82 }, { shift_fraction: 1, relative_force: 70 }],
  Convex: [{ shift_fraction: 0, relative_force: 78 }, { shift_fraction: .25, relative_force: 84 }, { shift_fraction: .5, relative_force: 96 }, { shift_fraction: .75, relative_force: 116 }, { shift_fraction: 1, relative_force: 148 }],
  Concave: [{ shift_fraction: 0, relative_force: 65 }, { shift_fraction: .25, relative_force: 94 }, { shift_fraction: .5, relative_force: 114 }, { shift_fraction: .75, relative_force: 127 }, { shift_fraction: 1, relative_force: 134 }],
  'S-shape': [{ shift_fraction: 0, relative_force: 76 }, { shift_fraction: .2, relative_force: 91 }, { shift_fraction: .45, relative_force: 96 }, { shift_fraction: .65, relative_force: 119 }, { shift_fraction: .82, relative_force: 124 }, { shift_fraction: 1, relative_force: 142 }],
};

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
  const [targetPoints, setTargetPoints] = useState<TargetPoint[]>(() => normalizePoints(PRESETS.Rising));
  const [targetMatch, setTargetMatch] = useState<ArchitectureTargetComparisonAnalysis | null>(null);
  const [discovery, setDiscovery] = useState<ArchitectureComparisonAnalysis | null>(null);
  const [loading, setLoading] = useState(false);
  const [discovering, setDiscovering] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const update = (patch: Partial<FixedPivotArchitecture>) => {
    setCandidate((value) => ({ ...value, ...patch }));
    setCandidateDomain(null);
    setTargetMatch(null);
    setDiscovery(null);
  };

  const ensureCandidateDomain = async () => {
    if (candidateDomain) return candidateDomain;
    const next = await analyzePrimaryPathDomain(candidate, includeZones ? zones : [], {
      shift_station_count: 9,
      q_sample_count: 61,
      alpha_sample_count: 9,
      representative_path_count: 8,
      edge_audit_sample_count: 65,
      history_trace_sample_count: 65,
    });
    setCandidateDomain(next);
    return next;
  };

  const compareTarget = async () => {
    setLoading(true);
    setError(null);
    try {
      const b = await ensureCandidateDomain();
      const next = await comparePrimaryPathDomainsToTarget(domain.domain_id, b.domain_id, targetPoints, {
        mass_mix_count: 11,
        sample_count: 121,
      });
      setTargetMatch(next);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Target-shape comparison failed.');
    } finally {
      setLoading(false);
    }
  };

  const discover = async () => {
    setDiscovering(true);
    setError(null);
    try {
      const b = await ensureCandidateDomain();
      const next = await comparePrimaryPathDomains(domain.domain_id, b.domain_id, { atlas_path_count: 40, mass_mix_count: 11 });
      setDiscovery(next);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Architecture difference search failed.');
    } finally {
      setDiscovering(false);
    }
  };

  return <div className={styles.root}>
    <aside className={styles.controls}>
      <div className={styles.heading}>
        <strong>Architecture B</strong>
        <p>Architecture A is the one you already analyzed. Change B here. The main comparison asks a literal question: <b>which architecture can make the force shape I draw?</b></p>
      </div>
      <Field label="Pivot radius" value={candidate.pivot_radius_m * MM} suffix="mm" onChange={(value) => update({ pivot_radius_m: value / MM })} />
      <Field label="Arm length" value={candidate.arm_length_m * MM} suffix="mm" onChange={(value) => update({ arm_length_m: value / MM })} />
      <Field label="Roller radius" value={candidate.roller_radius_m * MM} suffix="mm" onChange={(value) => update({ roller_radius_m: value / MM })} />
      <Field label="Travel" value={candidate.required_travel_m * MM} suffix="mm" onChange={(value) => update({ required_travel_m: value / MM })} />
      <label className={styles.checkbox}>
        <input type="checkbox" checked={includeZones} onChange={(event) => { setIncludeZones(event.target.checked); setCandidateDomain(null); setTargetMatch(null); setDiscovery(null); }} />
        <span>Apply A's packaging zones to B</span>
      </label>
      <button type="button" onClick={() => { setCandidate({ ...architecture }); setCandidateDomain(null); setTargetMatch(null); setDiscovery(null); }}>Copy A → B</button>
      <div className={styles.scaleNote}>
        <strong>Why the force axis is relative</strong>
        <span>Overall force can be retuned with RPM and flyweight mass. For architecture comparison we remove that scale and compare only the shape through shift. <b>100% = that curve's own average force.</b></span>
      </div>
      {candidateDomain && <div className={styles.domainReady}>B complete-path domain ready.</div>}
      {error && <div className={styles.error}>{error}</div>}
    </aside>

    <main className={styles.workspace}>
      <section className={styles.card}>
        <div className={styles.cardHeader}>
          <div>
            <strong>1 · Draw a force shape you care about</strong>
            <span>Gold is your requested progression. After comparison, A and B's closest complete physical ramps overlay on this exact plot.</span>
          </div>
          <div className={styles.presetRow}>
            {Object.entries(PRESETS).map(([name, rows]) => <button key={name} type="button" onClick={() => { setTargetPoints(normalizePoints(rows)); setTargetMatch(null); }}>{name}</button>)}
          </div>
        </div>
        <TargetShapePicker points={targetPoints} onChange={(next) => { setTargetPoints(normalizePoints(next)); setTargetMatch(null); }} comparison={targetMatch} />
        <div className={styles.compareActions}>
          <button type="button" className={styles.primary} disabled={loading} onClick={() => void compareTarget()}>{loading ? 'Solving both architectures continuously…' : 'Compare this force shape'}</button>
          <span>The continuous inverse should sit on top of gold whenever the shape is physically realizable. A visible gap means geometry, packaging, or contact history blocked an exact realization.</span>
        </div>
      </section>

      {targetMatch && <TargetComparisonResult analysis={targetMatch} />}

      <section className={styles.card}>
        <div className={styles.cardHeader}>
          <div>
            <strong>2 · Ask the reverse question</strong>
            <span>Instead of choosing a target, let the tool search for complete force shapes that expose the largest sampled difference between A and B.</span>
          </div>
          <button type="button" disabled={discovering} onClick={() => void discover()}>{discovering ? 'Searching complete ramp families…' : 'Find strongest architecture differences'}</button>
        </div>
        {!discovery ? <p className={styles.help}>This is optional. Use it when you want the tool to answer “show me something A can make that B struggles to copy,” and then the reverse.</p> : <DifferenceDiscovery analysis={discovery} />}
      </section>
    </main>
  </div>;
}

function TargetShapePicker({
  points,
  onChange,
  comparison,
}: {
  points: TargetPoint[];
  onChange: (rows: TargetPoint[]) => void;
  comparison: ArchitectureTargetComparisonAnalysis | null;
}) {
  const svgRef = useRef<SVGSVGElement | null>(null);
  const [drag, setDrag] = useState<DragState>(null);
  const width = 980;
  const height = 430;
  const pad = { left: 72, right: 24, top: 24, bottom: 52 };
  const sampled = useMemo(() => sampleShape(points, 161), [points]);
  const values = [60, 80, 100, 120, 140, 160, ...sampled.force, ...(comparison?.target.normalized_shape.map((v) => 100 * v) ?? []), ...(comparison?.architecture_a?.normalized_shape.map((v) => 100 * v) ?? []), ...(comparison?.architecture_b?.normalized_shape.map((v) => 100 * v) ?? [])];
  const yMin = Math.max(10, Math.floor((Math.min(...values) - 10) / 10) * 10);
  const yMax = Math.ceil((Math.max(...values) + 10) / 10) * 10;
  const sx = (v: number) => pad.left + v * (width - pad.left - pad.right);
  const sy = (v: number) => pad.top + (yMax - v) / Math.max(yMax - yMin, 1) * (height - pad.top - pad.bottom);
  const invX = (x: number) => clamp((x - pad.left) / (width - pad.left - pad.right), 0, 1);
  const invY = (y: number) => clamp(yMax - (y - pad.top) / (height - pad.top - pad.bottom) * (yMax - yMin), 10, 300);
  const local = (clientX: number, clientY: number) => {
    const svg = svgRef.current; const matrix = svg?.getScreenCTM(); if (!svg || !matrix) return null;
    const p = svg.createSVGPoint(); p.x = clientX; p.y = clientY; const q = p.matrixTransform(matrix.inverse()); return { x: q.x, y: q.y };
  };
  const begin = (event: React.PointerEvent<SVGCircleElement>, index: number) => { event.stopPropagation(); svgRef.current?.setPointerCapture(event.pointerId); setDrag({ index, pointerId: event.pointerId }); };
  const move = (event: React.PointerEvent<SVGSVGElement>) => {
    if (!drag || drag.pointerId !== event.pointerId) return; const p = local(event.clientX, event.clientY); if (!p) return;
    onChange(points.map((row, index) => index === drag.index ? { shift_fraction: invX(p.x), relative_force: invY(p.y) } : row));
  };
  const end = (event: React.PointerEvent<SVGSVGElement>) => {
    if (!drag || drag.pointerId !== event.pointerId) return; if (svgRef.current?.hasPointerCapture(event.pointerId)) svgRef.current.releasePointerCapture(event.pointerId);
    onChange([...points].sort((a, b) => a.shift_fraction - b.shift_fraction)); setDrag(null);
  };
  const add = (event: React.PointerEvent<SVGSVGElement>) => {
    if (drag) return; const p = local(event.clientX, event.clientY); if (!p || p.x < pad.left || p.x > width - pad.right || p.y < pad.top || p.y > height - pad.bottom) return;
    onChange([...points, { shift_fraction: invX(p.x), relative_force: invY(p.y) }].sort((a, b) => a.shift_fraction - b.shift_fraction));
  };
  const ticksY = niceTicks(yMin, yMax, 6);
  const ticksX = [0, .25, .5, .75, 1];
  return <>
    <svg ref={svgRef} className={styles.targetPlot} viewBox={`0 0 ${width} ${height}`} onPointerDown={add} onPointerMove={move} onPointerUp={end} onPointerCancel={end}>
      <rect x={pad.left} y={pad.top} width={width - pad.left - pad.right} height={height - pad.top - pad.bottom} className={styles.plotBackground} />
      {ticksY.map((tick) => <g key={tick}><line x1={pad.left} x2={width - pad.right} y1={sy(tick)} y2={sy(tick)} className={styles.grid} /><text x={pad.left - 9} y={sy(tick) + 4} textAnchor="end" className={styles.axisText}>{tick.toFixed(0)}%</text></g>)}
      {ticksX.map((tick) => <g key={tick}><line x1={sx(tick)} x2={sx(tick)} y1={pad.top} y2={height - pad.bottom} className={styles.grid} /><text x={sx(tick)} y={height - 21} textAnchor="middle" className={styles.axisText}>{Math.round(tick * 100)}%</text></g>)}
      <line x1={pad.left} x2={width - pad.right} y1={sy(100)} y2={sy(100)} className={styles.averageLine} />
      <path d={line(sampled.x, sampled.force, sx, sy)} className={styles.targetLine} />
      {comparison?.architecture_a && <path d={line(comparison.architecture_a.shift_fraction, comparison.architecture_a.normalized_shape.map((v) => 100 * v), sx, sy)} className={styles.lineA} />}
      {comparison?.architecture_b && <path d={line(comparison.architecture_b.shift_fraction, comparison.architecture_b.normalized_shape.map((v) => 100 * v), sx, sy)} className={styles.lineB} />}
      {points.map((point, index) => <circle key={`${point.shift_fraction}-${index}`} cx={sx(point.shift_fraction)} cy={sy(point.relative_force)} r={7} className={styles.handle} onPointerDown={(event) => begin(event, index)} onDoubleClick={(event) => { event.stopPropagation(); if (points.length > 2) onChange(points.filter((_, i) => i !== index)); }} />)}
      <text transform={`translate(18 ${height / 2}) rotate(-90)`} textAnchor="middle" className={styles.axisTitle}>relative force · 100% = average</text>
      <text x={(pad.left + width - pad.right) / 2} y={height - 4} textAnchor="middle" className={styles.axisTitle}>shift progress</text>
    </svg>
    <div className={styles.legend}>
      <span className={styles.legendTarget}>requested shape</span>
      {comparison?.architecture_a && <span className={styles.legendA}>Architecture A · continuous inverse ramp</span>}
      {comparison?.architecture_b && <span className={styles.legendB}>Architecture B · continuous inverse ramp</span>}
      <strong>100% line = each curve's own average force</strong>
    </div>
  </>;
}

function TargetComparisonResult({ analysis }: { analysis: ArchitectureTargetComparisonAnalysis }) {
  const a = analysis.architecture_a;
  const b = analysis.architecture_b;
  return <section className={styles.card}>
    <div className={styles.cardHeader}><div><strong>What the comparison says</strong><span>These are continuous inverse solutions. A near-zero mismatch means the requested shape was reproduced directly, not selected from a sampled ramp atlas.</span></div></div>
    <div className={styles.resultMetrics}>
      <MatchMetric label="Architecture A" match={a} />
      <MatchMetric label="Architecture B" match={b} />
    </div>
    <PlainConclusion a={a} b={b} />
    <div className={styles.rampPair}>
      <MatchRamp title="Architecture A · closest ramp" match={a} />
      <MatchRamp title="Architecture B · closest ramp" match={b} />
    </div>
  </section>;
}

function MatchMetric({ label, match }: { label: string; match: ArchitectureTargetMatch | null }) {
  return <div className={styles.matchMetric}>
    <strong>{label}</strong>
    {match ? <><b>{(100 * match.rms_shape_error).toFixed(2)}% average mismatch</b><span>worst local miss {(100 * match.max_shape_error).toFixed(1)}% near {(100 * match.max_error_shift_fraction).toFixed(0)}% shift</span><em>scale-free mass distribution: tip fraction {(100 * match.mass_mix_fraction).toFixed(0)}%</em></> : <span>No history-certified continuous inverse returned.</span>}
  </div>;
}

function PlainConclusion({ a, b }: { a: ArchitectureTargetMatch | null; b: ArchitectureTargetMatch | null }) {
  if (!a && !b) return <div className={styles.conclusion}>Neither architecture produced a history-certified continuous inverse for this target shape.</div>;
  if (!a) return <div className={styles.conclusion}>Architecture B produced a certified continuous inverse; A hit a geometry, packaging, or contact-history boundary.</div>;
  if (!b) return <div className={styles.conclusion}>Architecture A produced a certified continuous inverse; B hit a geometry, packaging, or contact-history boundary.</div>;
  const better = a.rms_shape_error <= b.rms_shape_error ? 'A' : 'B';
  const worse = Math.max(a.rms_shape_error, b.rms_shape_error);
  if (worse < .01) return <div className={styles.conclusion}><strong>For this requested shape, the architectures are functionally very similar.</strong> Both continuous inverses reproduce it within 1% RMS after force scale is removed.</div>;
  return <div className={styles.conclusion}><strong>For this requested shape, Architecture {better} reproduces the progression more closely.</strong> The smaller number is the whole-curve mismatch; the plot above shows exactly where the other architecture departs.</div>;
}

function MatchRamp({ title, match }: { title: string; match: ArchitectureTargetMatch | null }) {
  if (!match) return <div className={styles.rampCard}><strong>{title}</strong><span>No physical match.</span></div>;
  return <div className={styles.rampCard}><strong>{title}</strong><RampPlot x={match.ramp.ramp_surface.x_m} r={match.ramp.ramp_surface.r_m} /><div className={styles.rampStats}><span>q {match.ramp.q_deg[0]?.toFixed(1)}° → {match.ramp.q_deg.at(-1)?.toFixed(1)}°</span><span>tip/total mass fraction {(100 * match.mass_mix_fraction).toFixed(0)}%</span></div></div>;
}

function DifferenceDiscovery({ analysis }: { analysis: ArchitectureComparisonAnalysis }) {
  const a = analysis.witnesses.a_not_b[0] ?? null;
  const b = analysis.witnesses.b_not_a[0] ?? null;
  return <div className={styles.discoveryGrid}>
    <DiscoveryCard title="A behavior that B struggles most to copy" witness={a} />
    <DiscoveryCard title="B behavior that A struggles most to copy" witness={b as Witness | null} />
  </div>;
}

function DiscoveryCard({ title, witness }: { title: string; witness: Witness | null }) {
  if (!witness) return <div className={styles.discoveryCard}><strong>{title}</strong><span>No witness returned.</span></div>;
  const width = 560; const height = 260; const pad = { left: 54, right: 18, top: 18, bottom: 38 };
  const source = witness.source.normalized_shape.map((v) => 100 * v); const near = witness.nearest.normalized_shape.map((v) => 100 * v);
  const vals = [...source, ...near, 100]; const lo = Math.floor((Math.min(...vals) - 8) / 10) * 10; const hi = Math.ceil((Math.max(...vals) + 8) / 10) * 10;
  const sx = (v: number) => pad.left + v * (width - pad.left - pad.right); const sy = (v: number) => pad.top + (hi - v) / Math.max(hi - lo, 1) * (height - pad.top - pad.bottom);
  return <div className={styles.discoveryCard}>
    <strong>{title}</strong>
    <span>The source curve is physically realizable by {witness.source_architecture}; the dashed curve is the closest complete sampled answer from {witness.nearest_architecture}.</span>
    <svg viewBox={`0 0 ${width} ${height}`}>
      <line x1={pad.left} x2={width - pad.right} y1={sy(100)} y2={sy(100)} className={styles.averageLine} />
      <path d={line(witness.source.shift_fraction, source, sx, sy)} className={styles.discoverySource} />
      <path d={line(witness.nearest.shift_fraction, near, sx, sy)} className={styles.discoveryNearest} />
      <text x={width / 2} y={height - 5} textAnchor="middle" className={styles.axisText}>0% → 100% shift</text>
    </svg>
    <b>{(100 * witness.shape_distance).toFixed(1)}% whole-curve mismatch</b>
    <em>largest local difference {(100 * witness.max_pointwise_shape_gap).toFixed(1)}% near {(100 * witness.gap_shift_fraction).toFixed(0)}% shift</em>
  </div>;
}

function RampPlot({ x, r }: { x: number[]; r: number[] }) {
  if (!x.length || !r.length) return <div className={styles.help}>No geometry.</div>;
  const width = 520; const height = 230; const pad = 26; const xMin = Math.min(...x), xMax = Math.max(...x), rMin = Math.min(...r), rMax = Math.max(...r);
  const scale = Math.min((width - 2 * pad) / Math.max(xMax - xMin, 1e-4), (height - 2 * pad) / Math.max(rMax - rMin, 1e-4));
  const sx = (v: number) => pad + (v - xMin) * scale; const sy = (v: number) => height - pad - (v - rMin) * scale;
  return <svg viewBox={`0 0 ${width} ${height}`}><path d={line(x, r, sx, sy)} className={styles.rampLine} /></svg>;
}

function Field({ label, value, suffix, onChange }: { label: string; value: number; suffix: string; onChange: (v: number) => void }) {
  return <label className={styles.field}><span>{label}</span><div><input type="number" value={value.toFixed(2)} step={.5} onChange={(event) => onChange(Number(event.target.value))} /><em>{suffix}</em></div></label>;
}

function normalizePoints(points: TargetPoint[]) {
  if (points.length < 2) return points;
  const sampled = sampleShapeRaw(points, 401);
  const mean = sampled.force.reduce((sum, value) => sum + value, 0) / Math.max(sampled.force.length, 1);
  if (!Number.isFinite(mean) || mean <= 1e-9) return points;
  const scale = 100 / mean;
  return points.map((point) => ({ ...point, relative_force: point.relative_force * scale }));
}

function sampleShapeRaw(points: TargetPoint[], count: number) {
  const sorted = [...points].sort((a, b) => a.shift_fraction - b.shift_fraction);
  const xs = sorted.map((p) => p.shift_fraction); const ys = sorted.map((p) => p.relative_force);
  if (xs[0] > 0) { xs.unshift(0); ys.unshift(ys[0]); } if (xs.at(-1)! < 1) { xs.push(1); ys.push(ys.at(-1)!); }
  const slopes = pchipSlopes(xs, ys); const outX = Array.from({ length: count }, (_, i) => i / (count - 1)); return { x: outX, force: outX.map((v) => hermiteAt(xs, ys, slopes, v)) };
}

function sampleShape(points: TargetPoint[], count: number) { return sampleShapeRaw(points, count); }
function pchipSlopes(x: number[], y: number[]) { const n = x.length; if (n === 2) { const d = (y[1] - y[0]) / (x[1] - x[0]); return [d, d]; } const h = Array.from({ length: n - 1 }, (_, i) => x[i + 1] - x[i]); const d = Array.from({ length: n - 1 }, (_, i) => (y[i + 1] - y[i]) / h[i]); const m = Array(n).fill(0); for (let i = 1; i < n - 1; i += 1) { if (d[i - 1] === 0 || d[i] === 0 || Math.sign(d[i - 1]) !== Math.sign(d[i])) m[i] = 0; else { const w1 = 2 * h[i] + h[i - 1]; const w2 = h[i] + 2 * h[i - 1]; m[i] = (w1 + w2) / (w1 / d[i - 1] + w2 / d[i]); } } m[0] = endpointSlope(h[0], h[1], d[0], d[1]); m[n - 1] = endpointSlope(h[n - 2], h[n - 3], d[n - 2], d[n - 3]); return m; }
function endpointSlope(h0: number, h1: number, d0: number, d1: number) { let m = ((2 * h0 + h1) * d0 - h0 * d1) / (h0 + h1); if (Math.sign(m) !== Math.sign(d0)) m = 0; else if (Math.sign(d0) !== Math.sign(d1) && Math.abs(m) > 3 * Math.abs(d0)) m = 3 * d0; return m; }
function hermiteAt(x: number[], y: number[], m: number[], value: number) { let i = x.length - 2; for (let j = 0; j < x.length - 1; j += 1) if (value <= x[j + 1]) { i = j; break; } const h = x[i + 1] - x[i]; const t = clamp((value - x[i]) / h, 0, 1); const t2 = t * t; const t3 = t2 * t; return (2 * t3 - 3 * t2 + 1) * y[i] + (t3 - 2 * t2 + t) * h * m[i] + (-2 * t3 + 3 * t2) * y[i + 1] + (t3 - t2) * h * m[i + 1]; }
function line(xs: number[], ys: number[], sx: (x: number) => number, sy: (y: number) => number) { return xs.map((x, i) => `${i ? 'L' : 'M'} ${sx(x).toFixed(2)} ${sy(ys[i]).toFixed(2)}`).join(' '); }
function niceTicks(min: number, max: number, count: number) { const raw = (max - min) / Math.max(1, count - 1); const mag = 10 ** Math.floor(Math.log10(Math.max(raw, 1e-9))); const norm = raw / mag; const step = (norm <= 1 ? 1 : norm <= 2 ? 2 : norm <= 5 ? 5 : 10) * mag; const start = Math.ceil(min / step) * step; const rows: number[] = []; for (let v = start; v <= max + 1e-9; v += step) rows.push(v); return rows; }
function clamp(value: number, min: number, max: number) { return Math.max(min, Math.min(max, value)); }
