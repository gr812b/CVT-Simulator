import { Text } from '@mantine/core';
import type { TuneProfileTrace } from './api';
import { displayAngle, type Ramp } from './profileStages';

/** Plot sampled CINDER surface angles, not a second copy of the 3D ramp shape. */
export function ProfileSketch({ trace, profile, selected, onSelect, contact, helix, ranges: requestedRanges }: {
  trace: TuneProfileTrace | null | undefined;
  profile: Ramp;
  selected: number;
  onSelect: (index: number) => void;
  contact?: number | null;
  helix: boolean;
  ranges?: [number, number][];
}) {
  if (!trace?.coordinates_m.length) return <Text size="xs" c="dimmed">The angle plot appears when a profile preview is available.</Text>;
  const xs = trace.coordinates_m;
  const lo = helix ? trace.used_start_m ?? xs[0] : xs[0];
  const hi = helix ? trace.used_end_m ?? xs.at(-1)! : xs.at(-1)!;
  const span = Math.max(hi - lo, 1e-12);
  const values = trace.slope_angles_rad.map(angle => displayAngle(angle, helix) * 180 / Math.PI);
  const indices = xs.flatMap((coordinate, i) => coordinate >= lo - 1e-12 && coordinate <= hi + 1e-12 && Number.isFinite(values[i]) ? [i] : []);
  if (!indices.length) return <Text size="xs" c="dimmed">No sampled angles are available in the displayed travel interval.</Text>;
  const angles = indices.map(i => values[i]);
  const minimum = Math.min(...angles), maximum = Math.max(...angles);
  const centre = (minimum + maximum) / 2;
  const extent = Math.max(maximum - minimum, 5) * 1.2;
  const ymin = centre - extent / 2, ymax = centre + extent / 2;
  const x = (coordinate: number) => 58 + (coordinate - lo) / span * 340;
  const y = (angle: number) => 142 - (angle - ymin) / extent * 112;
  let start = 0;
  const ranges = requestedRanges ?? profile.segments.map(segment => {
    const left = start; start += segment.length_m;
    return [left, start] as [number, number];
  });
  const points = (entries: number[]) => entries.map(i => `${x(xs[i])},${y(values[i])}`).join(' ');
  const [a, b] = ranges[selected] ?? [lo, hi];
  const active = indices.filter(i => xs[i] >= a && xs[i] <= b);
  const currentX = contact == null ? null : x(contact);
  const axisLabel = helix ? 'Helix angle (°)' : 'Ramp angle (°)';
  return <svg viewBox="0 0 440 193" style={{ width: '100%', display: 'block' }} role="group"
    aria-label={helix ? 'Helix angle through secondary opening' : 'Ramp surface angle along the primary profile'}>
    <title>{helix ? 'Helix angle from the circumferential direction' : 'Ramp surface angle from its axial profile coordinate, not the flyweight arm angle'}</title>
    <text x={12} y={86} transform="rotate(-90 12 86)" textAnchor="middle" fill="currentColor" fontSize={11}>{axisLabel}</text>
    {[ymin, centre, ymax].map(tick => <g key={tick}>
      <line x1={58} x2={398} y1={y(tick)} y2={y(tick)} stroke="currentColor" opacity={0.12}/>
      <text x={50} y={y(tick) + 3} textAnchor="end" fill="currentColor" fontSize={10}>{tick.toFixed(1)}</text>
    </g>)}
    <path d="M58 25 V148 H403" fill="none" stroke="currentColor" opacity={0.4}/>
    <polyline points={points(indices)} fill="none" stroke="currentColor" strokeWidth={2}/>
    <polyline points={points(active)} fill="none" stroke="var(--mantine-primary-color-filled)" strokeWidth={4}/>
    {ranges.map(([left, right], i) => {
      const l = Math.max(left, lo), r = Math.min(right, hi);
      if (!(r > l)) return null;
      return <g key={i} role="button" tabIndex={0} aria-label={`Select angle stage ${i + 1}`} aria-pressed={i === selected}
        onClick={() => onSelect(i)} onKeyDown={event => {
          if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); onSelect(i); }
        }} style={{ cursor: 'pointer' }}>
        <rect x={x(l)} y={25} width={Math.max(1, x(r) - x(l))} height={123} fill="transparent"/>
        {l > lo && <line x1={x(l)} x2={x(l)} y1={25} y2={148} stroke="currentColor" strokeDasharray="2 4" opacity={0.3} pointerEvents="none"/>}
        <text x={x((l + r) / 2)} y={16} textAnchor="middle" fill="currentColor" fontSize={10}>Stage {i + 1}</text>
      </g>;
    })}
    {currentX !== null && currentX >= 58 && currentX <= 398 && <g pointerEvents="none">
      <line x1={currentX} x2={currentX} y1={25} y2={148} stroke="var(--mantine-primary-color-filled)" strokeDasharray="4 3"/>
      <title>Current {helix ? 'opening' : 'roller contact'} position</title>
    </g>}
    {[0, 0.5, 1].map(fraction => <text key={fraction} x={x(lo + fraction * span)} y={164}
      textAnchor={fraction === 0 ? 'start' : fraction === 1 ? 'end' : 'middle'} fill="currentColor" fontSize={10}>
      {helix ? `${fraction * 100}%` : ((lo + fraction * span) * 1000).toFixed(1)}
    </text>)}
    <text x={228} y={184} textAnchor="middle" fill="currentColor" fontSize={11}>
      {helix ? 'Secondary opening travel' : 'Position along ramp (axial coordinate, mm)'}
    </text>
  </svg>;
}
