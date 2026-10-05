import { useId } from 'react';
import type { components } from '@api/generated/backend';

type Point = components['schemas']['CoursePoint'];
/** Display-only chart shared by road previews and recorded playback. */
export function CourseChart({
  points,
  position,
  label = 'Road elevation preview',
}: {
  points: readonly Point[];
  position?: number | null;
  label?: string;
}) {
  const id = useId();
  if (!points.length) return null;
  const first = points[0],
    last = points[points.length - 1];
  const elevations = points.map((point) => point.elevation_m);
  const minY = Math.min(...elevations),
    maxY = Math.max(...elevations);
  const spanY = Math.max(maxY - minY, 1);
  const baseY = minY - (spanY - (maxY - minY)) / 2;
  const x = (distance: number) =>
    68 +
    (610 * (distance - first.distance_m)) /
      Math.max(last.distance_m - first.distance_m, 1e-6);
  const y = (elevation: number) => 180 - (135 * (elevation - baseY)) / spanY;
  let marker: Point | undefined;
  if (position != null && Number.isFinite(position)) {
    const distance = Math.min(
      last.distance_m,
      Math.max(first.distance_m, position),
    );
    const right = points.findIndex((point) => point.distance_m >= distance);
    const a = points[Math.max(0, right - 1)],
      b = points[Math.max(0, right)];
    const fraction =
      b.distance_m === a.distance_m
        ? 0
        : (distance - a.distance_m) / (b.distance_m - a.distance_m);
    marker = {
      distance_m: distance,
      elevation_m: a.elevation_m + fraction * (b.elevation_m - a.elevation_m),
    };
  }
  return (
    <svg
      viewBox="0 0 710 245"
      role="img"
      aria-labelledby={id}
      style={{ width: '100%', display: 'block', maxHeight: 290 }}
    >
      <title id={id}>
        {label}
        {marker
          ? `; vehicle at ${marker.distance_m.toFixed(1)} m, elevation ${marker.elevation_m.toFixed(1)} m`
          : ''}
      </title>
      {[0, 0.5, 1].map((fraction) => {
        const elevation = baseY + fraction * spanY;
        return (
          <g key={fraction}>
            <line
              x1="68"
              x2="678"
              y1={y(elevation)}
              y2={y(elevation)}
              stroke="var(--mantine-color-default-border)"
            />
            <text
              x="58"
              y={y(elevation) + 4}
              textAnchor="end"
              fill="currentColor"
              fontSize="12"
            >
              {elevation.toFixed(1)}
            </text>
          </g>
        );
      })}
      <text x="68" y="24" fill="currentColor" fontSize="13">
        Elevation (m)
      </text>
      <polyline
        points={points
          .map((p) => `${x(p.distance_m)},${y(p.elevation_m)}`)
          .join(' ')}
        fill="none"
        stroke="var(--mantine-primary-color-filled)"
        strokeWidth="3"
      />
      {marker && (
        <g data-testid="course-position" data-distance={marker.distance_m}>
          <line
            x1={x(marker.distance_m)}
            x2={x(marker.distance_m)}
            y1="40"
            y2="185"
            stroke="var(--mantine-color-text)"
            strokeDasharray="4 4"
          />
          <circle
            cx={x(marker.distance_m)}
            cy={y(marker.elevation_m)}
            r="6"
            fill="var(--mantine-primary-color-filled)"
            stroke="var(--mantine-color-body)"
            strokeWidth="2"
          />
        </g>
      )}
      <text x="68" y="205" fill="currentColor" fontSize="12">
        {first.distance_m.toFixed(1)}
      </text>
      <text x="678" y="205" textAnchor="end" fill="currentColor" fontSize="12">
        {last.distance_m.toFixed(1)}
      </text>
      <text
        x="373"
        y="233"
        textAnchor="middle"
        fill="currentColor"
        fontSize="13"
      >
        Distance along road (m)
      </text>
    </svg>
  );
}
