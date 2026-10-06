import { Text } from '@mantine/core';
import { displayAngle, type Ramp } from './profileStages';
import type { TuneProfileTrace } from './api';

/** Only plots samples returned by CINDER; this does not evaluate profile mechanics. */
export function ProfileSketch({ trace, profile, selected, onSelect, contact, helix, ranges: requestedRanges }: {
  trace: TuneProfileTrace | null | undefined; profile: Ramp; selected: number;
  onSelect: (index: number) => void; contact?: number | null; helix: boolean; ranges?: [number, number][];
}) {
  if (!trace?.coordinates_m.length) return <Text size="xs" c="dimmed">The profile drawing appears when a preview is available.</Text>;
  const xs = trace.coordinates_m;
  const lo = helix ? trace.used_start_m ?? xs[0] : xs[0];
  const hi = helix ? trace.used_end_m ?? xs.at(-1)! : xs.at(-1)!;
  const span = Math.max(hi - lo, 1e-12);
  const values = helix ? trace.slope_angles_rad.map(a => displayAngle(a, true) * 180 / Math.PI) : trace.values_m.map(v => v * 1000);
  const ymin = Math.min(...values), ymax = Math.max(...values);
  const dy = Math.max(ymax - ymin, helix ? 5 : 1);
  const x = (n: number) => 46 + (n - lo) / span * 354;
  const y = (n: number) => 135 - (n - ymin + dy * 0.12) / (dy * 1.24) * 105;
  let start = 0;
  const ranges = requestedRanges ?? profile.segments.map(s => { const a = start; start += s.length_m; return [a, start]; });
  const pointString = (indices: number[]) => indices.map(i => `${x(xs[i])},${y(values[i])}`).join(' ');
  const indices = xs.flatMap((value, i) => value >= lo - 1e-12 && value <= hi + 1e-12 ? [i] : []);
  const [a, b] = ranges[selected] ?? [lo, hi];
  const active = indices.filter(i => xs[i] >= a && xs[i] <= b);
  const current = contact == null ? null : x(contact);
  return <svg viewBox="0 0 440 185" style={{ width: '100%', display: 'block' }} role="img" aria-label={helix ? 'Helix angle through secondary opening' : 'Primary ramp profile and contact position'}>
    <title>{helix ? 'Helix angle, measured from the circumferential direction' : 'Physical ramp: axial profile coordinate versus radial rise, in millimetres'}</title>
    <text x={10} y={86} transform="rotate(-90 10 86)" textAnchor="middle" fill="currentColor" fontSize={10}>{helix ? 'Helix angle (°)' : 'Radial rise (mm)'}</text>
    <path d="M46 20 V145 H405" fill="none" stroke="currentColor" opacity={0.4}/>
    <polyline points={pointString(indices)} fill="none" stroke="currentColor" strokeWidth={2}/>
    <polyline points={pointString(active)} fill="none" stroke="var(--mantine-primary-color-filled)" strokeWidth={4}/>
    {ranges.map(([left, right], i) => {
      const l = Math.max(left, lo), r = Math.min(right, hi);
      if (!(r > l)) return null;
      return <g key={i}>
        <rect x={x(l)} y={20} width={Math.max(1, x(r) - x(l))} height={125} fill="transparent"
          onClick={() => onSelect(i)} style={{ cursor: 'pointer' }}/>
        <text x={x((l + r) / 2)} y={16} textAnchor="middle" fill="currentColor" fontSize={10}>Stage {i + 1}</text>
      </g>;
    })}
    {current !== null && current >= 46 && current <= 400 && <line x1={current} x2={current} y1={20} y2={145} stroke="var(--mantine-primary-color-filled)" strokeDasharray="4 3" pointerEvents="none"/>}
    <text x={46} y={159} fill="currentColor" fontSize={10}>{helix ? '0%' : `${(lo * 1000).toFixed(1)}`}</text>
    <text x={400} y={159} textAnchor="end" fill="currentColor" fontSize={10}>{helix ? '100%' : `${(hi * 1000).toFixed(1)}`}</text>
    <text x={222} y={179} textAnchor="middle" fill="currentColor" fontSize={11}>{helix ? 'Secondary opening travel' : 'Position along ramp (axial coordinate, mm)'}</text>
    <text x={39} y={y(ymax) + 3} textAnchor="end" fill="currentColor" fontSize={10}>{ymax.toFixed(1)}{helix ? '°' : ''}</text>
    <text x={39} y={y(ymin) + 3} textAnchor="end" fill="currentColor" fontSize={10}>{ymin.toFixed(1)}{helix ? '°' : ''}</text>
  </svg>;
}
