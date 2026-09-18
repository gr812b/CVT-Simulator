import { useMemo, useState } from 'react';
import type { PrimaryPathDomainAnalysis } from '@api/primaryDesign';
import styles from './PrimaryDesign.module.scss';

const WIDTH = 980;
const HEIGHT = 350;
const PAD_L = 62;
const PAD_R = 22;
const PAD_T = 22;
const PAD_B = 44;

type CapabilityMetric = 'tip' | 'arm' | 'maxTotal';

interface MetricSpec {
  label: string;
  shortLabel: string;
  unit: string;
  minKey:
    | 'tip_force_per_omega2_per_kg_min'
    | 'arm_force_per_omega2_min'
    | 'max_tip_total_force_per_omega2_min';
  maxKey:
    | 'tip_force_per_omega2_per_kg_max'
    | 'arm_force_per_omega2_max'
    | 'max_tip_total_force_per_omega2_max';
  pathKey:
    | 'tip_force_per_omega2_per_kg'
    | 'arm_force_per_omega2'
    | 'max_tip_total_force_per_omega2';
}

const METRICS: Record<CapabilityMetric, MetricSpec> = {
  tip: {
    label: 'Tip-mass force gain',
    shortLabel: 'Ktip',
    unit: 'N/(rad/s)²/kg',
    minKey: 'tip_force_per_omega2_per_kg_min',
    maxKey: 'tip_force_per_omega2_per_kg_max',
    pathKey: 'tip_force_per_omega2_per_kg',
  },
  arm: {
    label: 'Configured arm-mass force gain',
    shortLabel: 'Karm',
    unit: 'N/(rad/s)²',
    minKey: 'arm_force_per_omega2_min',
    maxKey: 'arm_force_per_omega2_max',
    pathKey: 'arm_force_per_omega2',
  },
  maxTotal: {
    label: 'Total gain at max tip mass',
    shortLabel: 'Ktotal,max',
    unit: 'N/(rad/s)²',
    minKey: 'max_tip_total_force_per_omega2_min',
    maxKey: 'max_tip_total_force_per_omega2_max',
    pathKey: 'max_tip_total_force_per_omega2',
  },
};

interface EnvelopePoint {
  f: number;
  min: number;
  max: number;
}

export function CapabilityExplorer({
  current,
  baseline,
  selectedRepresentativeIndex,
}: {
  current: PrimaryPathDomainAnalysis;
  baseline: PrimaryPathDomainAnalysis | null;
  selectedRepresentativeIndex: number;
}) {
  const [metric, setMetric] = useState<CapabilityMetric>('tip');
  const spec = METRICS[metric];
  const currentEnvelope = useMemo(() => envelope(current, spec), [current, spec]);
  const baselineEnvelope = useMemo(() => baseline ? envelope(baseline, spec) : [], [baseline, spec]);
  const comparison = useMemo(
    () => baseline ? compareEnvelopes(currentEnvelope, baselineEnvelope) : null,
    [baseline, currentEnvelope, baselineEnvelope],
  );

  const allValues = [
    ...currentEnvelope.flatMap((point) => [point.min, point.max]),
    ...baselineEnvelope.flatMap((point) => [point.min, point.max]),
  ].filter(Number.isFinite);
  const rawMin = allValues.length ? Math.min(...allValues) : 0;
  const rawMax = allValues.length ? Math.max(...allValues) : 1;
  const span = Math.max(1e-9, rawMax - rawMin);
  const yMin = Math.min(0, rawMin - 0.08 * span);
  const yMax = rawMax + 0.10 * span;
  const innerW = WIDTH - PAD_L - PAD_R;
  const innerH = HEIGHT - PAD_T - PAD_B;
  const sx = (f: number) => PAD_L + Math.min(1, Math.max(0, f)) * innerW;
  const sy = (value: number) => PAD_T + (yMax - value) / Math.max(1e-12, yMax - yMin) * innerH;

  const currentBand = bandPath(currentEnvelope, sx, sy);
  const baselineBand = bandPath(baselineEnvelope, sx, sy);
  const selected = current.representative_paths[Math.min(selectedRepresentativeIndex, current.representative_paths.length - 1)] ?? null;
  const yTicks = tickValues(yMin, yMax, 5);

  return (
    <div className={styles.capabilityExplorer}>
      <div className={styles.capabilityHeader}>
        <div>
          <strong>Normalized force-capability domain</strong>
          <span>Geometry and motion-ratio capability before choosing RPM; Ktip also removes the chosen tip mass.</span>
        </div>
        <label className={styles.compactField}>
          <span>Capability</span>
          <select value={metric} onChange={(event) => setMetric(event.target.value as CapabilityMetric)}>
            <option value="tip">Tip-mass gain Ktip</option>
            <option value="arm">Arm-mass gain Karm</option>
            <option value="maxTotal">Total at max tip mass</option>
          </select>
        </label>
      </div>

      <svg viewBox={`0 0 ${WIDTH} ${HEIGHT}`} className={styles.capabilityPlot} role="img" aria-label="Normalized force capability envelope">
        <rect width={WIDTH} height={HEIGHT} rx="12" fill="var(--primary-design-canvas, #0d1319)" />
        {yTicks.map((value) => (
          <g key={value}>
            <line x1={PAD_L} y1={sy(value)} x2={WIDTH - PAD_R} y2={sy(value)} className={styles.domainGrid} />
            <text x={PAD_L - 8} y={sy(value) + 4} textAnchor="end" className={styles.domainAxisLabel}>{formatValue(value)}</text>
          </g>
        ))}
        {[0, 0.25, 0.5, 0.75, 1].map((fraction) => (
          <g key={fraction}>
            <line x1={sx(fraction)} y1={PAD_T} x2={sx(fraction)} y2={PAD_T + innerH} className={styles.domainGridVertical} />
            <text x={sx(fraction)} y={HEIGHT - 14} textAnchor="middle" className={styles.domainAxisLabel}>{Math.round(fraction * 100)}%</text>
          </g>
        ))}

        {baselineBand && <path d={baselineBand} className={styles.capabilityBaselineBand} />}
        {currentBand && <path d={currentBand} className={styles.capabilityCurrentBand} />}

        {current.representative_paths.map((path, index) => {
          const values = path.capability[spec.pathKey];
          const d = path.shift_m.map((shift, pointIndex) => {
            const fraction = current.architecture.required_travel_m <= 0 ? 0 : shift / current.architecture.required_travel_m;
            return `${pointIndex === 0 ? 'M' : 'L'} ${sx(fraction)} ${sy(values[pointIndex])}`;
          }).join(' ');
          return (
            <path
              key={index}
              d={d}
              className={index === selectedRepresentativeIndex ? styles.capabilitySelectedCurve : styles.capabilityRepresentativeCurve}
            />
          );
        })}

        {selected && (
          <text x={WIDTH - PAD_R - 4} y={PAD_T + 14} textAnchor="end" className={styles.capabilitySelectedLabel}>
            selected ramp {Math.min(selectedRepresentativeIndex + 1, current.representative_paths.length)}
          </text>
        )}

        <text x={PAD_L} y={HEIGHT - 14} className={styles.domainAxisTitle}>required-travel fraction</text>
        <text x={PAD_L} y={PAD_T - 7} className={styles.domainAxisTitle}>{spec.shortLabel} · {spec.unit}</text>
      </svg>

      <div className={styles.capabilityLegend}>
        <span><i className={styles.capabilityLegendCurrent} />current complete-path-viable envelope</span>
        {baseline && <span><i className={styles.capabilityLegendBaseline} />pinned baseline envelope</span>}
        <span><i className={styles.capabilityLegendPaths} />history-certified representative curves</span>
        <span><i className={styles.capabilityLegendSelected} />selected ramp</span>
      </div>

      <p className={styles.helpText}>{current.capability.definition}</p>

      {comparison && (
        <div className={styles.capabilityComparisonGrid}>
          <ComparisonMetric
            label="Peak upper capability"
            baseline={comparison.baselinePeak}
            current={comparison.currentPeak}
            suffix={` ${spec.unit}`}
          />
          <ComparisonMetric
            label="Mean attainable width"
            baseline={comparison.baselineWidth}
            current={comparison.currentWidth}
            suffix={` ${spec.unit}`}
          />
          <div className={styles.metric}>
            <span>Pointwise baseline envelope retained</span>
            <strong>{(comparison.retainedFraction * 100).toFixed(1)} %</strong>
          </div>
          <div className={styles.metric}>
            <span>Pointwise new envelope outside baseline</span>
            <strong>{(comparison.gainedFraction * 100).toFixed(1)} %</strong>
          </div>
        </div>
      )}
    </div>
  );
}

function ComparisonMetric({
  label,
  baseline,
  current,
  suffix,
}: {
  label: string;
  baseline: number;
  current: number;
  suffix: string;
}) {
  const delta = current - baseline;
  const percent = Math.abs(baseline) > 1e-12 ? 100 * delta / Math.abs(baseline) : null;
  return (
    <div className={styles.metric}>
      <span>{label}</span>
      <strong>{formatValue(current)}{suffix}</strong>
      <em className={delta >= 0 ? styles.capabilityGain : styles.capabilityLoss}>
        {delta >= 0 ? '+' : ''}{formatValue(delta)}{percent === null ? '' : ` (${percent >= 0 ? '+' : ''}${percent.toFixed(1)}%)`} vs baseline
      </em>
    </div>
  );
}

function envelope(analysis: PrimaryPathDomainAnalysis, spec: MetricSpec): EnvelopePoint[] {
  const result: EnvelopePoint[] = [];
  for (const station of analysis.capability.stations) {
    const min = station[spec.minKey];
    const max = station[spec.maxKey];
    if (typeof min !== 'number' || typeof max !== 'number') continue;
    result.push({ f: station.shift_fraction, min, max });
  }
  return result;
}

function bandPath(
  points: EnvelopePoint[],
  sx: (value: number) => number,
  sy: (value: number) => number,
): string {
  if (points.length < 2) return '';
  const top = points.map((point, index) => `${index === 0 ? 'M' : 'L'} ${sx(point.f)} ${sy(point.max)}`);
  const bottom = points.slice().reverse().map((point) => `L ${sx(point.f)} ${sy(point.min)}`);
  return [...top, ...bottom, 'Z'].join(' ');
}

function compareEnvelopes(current: EnvelopePoint[], baseline: EnvelopePoint[]) {
  const fractions = current.map((point) => point.f);
  let overlapArea = 0;
  let baselineArea = 0;
  let gainedArea = 0;
  let currentWidthSum = 0;
  let baselineWidthSum = 0;
  let currentPeak = Number.NEGATIVE_INFINITY;
  let baselinePeak = Number.NEGATIVE_INFINITY;

  for (const [index, point] of current.entries()) {
    const other = interpolateEnvelope(baseline, point.f);
    if (!other) continue;
    const currentWidth = Math.max(0, point.max - point.min);
    const baselineWidth = Math.max(0, other.max - other.min);
    const overlap = Math.max(0, Math.min(point.max, other.max) - Math.max(point.min, other.min));
    const weight = index === 0 || index === fractions.length - 1 ? 0.5 : 1.0;
    overlapArea += weight * overlap;
    baselineArea += weight * baselineWidth;
    gainedArea += weight * Math.max(0, currentWidth - overlap);
    currentWidthSum += currentWidth;
    baselineWidthSum += baselineWidth;
    currentPeak = Math.max(currentPeak, point.max);
    baselinePeak = Math.max(baselinePeak, other.max);
  }

  const count = Math.max(1, current.length);
  return {
    currentPeak: Number.isFinite(currentPeak) ? currentPeak : 0,
    baselinePeak: Number.isFinite(baselinePeak) ? baselinePeak : 0,
    currentWidth: currentWidthSum / count,
    baselineWidth: baselineWidthSum / count,
    retainedFraction: baselineArea > 1e-12 ? Math.min(1, overlapArea / baselineArea) : 1,
    gainedFraction: baselineArea > 1e-12 ? gainedArea / baselineArea : 0,
  };
}

function interpolateEnvelope(points: EnvelopePoint[], f: number): EnvelopePoint | null {
  if (!points.length) return null;
  if (f <= points[0].f) return points[0];
  if (f >= points[points.length - 1].f) return points[points.length - 1];
  let lo = 0;
  let hi = points.length - 1;
  while (hi - lo > 1) {
    const mid = Math.floor((lo + hi) / 2);
    if (points[mid].f <= f) lo = mid;
    else hi = mid;
  }
  const span = points[hi].f - points[lo].f;
  const t = span <= 0 ? 0 : (f - points[lo].f) / span;
  return {
    f,
    min: points[lo].min + t * (points[hi].min - points[lo].min),
    max: points[lo].max + t * (points[hi].max - points[lo].max),
  };
}

function tickValues(min: number, max: number, count: number): number[] {
  if (count <= 1 || Math.abs(max - min) < 1e-12) return [min];
  return Array.from({ length: count }, (_, index) => min + index * (max - min) / (count - 1));
}

function formatValue(value: number): string {
  const magnitude = Math.abs(value);
  if (magnitude >= 100) return value.toFixed(0);
  if (magnitude >= 10) return value.toFixed(1);
  if (magnitude >= 1) return value.toFixed(2);
  if (magnitude >= 0.01) return value.toFixed(3);
  return value.toExponential(2);
}
