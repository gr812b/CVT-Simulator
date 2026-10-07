import { projectCourse } from './courseGeometry';
import { useId } from 'react';
import type { components } from '@api/generated/backend';
import { useAuth } from '@contexts/AuthContext';
import { normalizeUnitPreferences, preferredDisplayUnit, siToDisplay, type UnitScope } from '@utils/units';

type Point = components['schemas']['CoursePoint'];
/** Display-only chart shared by road previews and recorded playback. */
export function CourseChart({
  points: roadPoints,
  position,
  label = 'Road elevation preview',
  scope = 'course',
}: {
  points: readonly Point[];
  position?: number | null;
  label?: string;
  scope?: UnitScope;
}) {
  const id = useId();
  const { unitPreferences } = useAuth();
  const preferences = normalizeUnitPreferences(unitPreferences);
  const lengthUnit = preferredDisplayUnit('length', scope, preferences, 'm');
  if (!roadPoints.length) return null;
  const points = projectCourse(roadPoints);
  const first = points[0],
    last = points[points.length - 1];
  const elevations = points.map((point) => point.elevation_m);
  const minY = Math.min(...elevations),
    maxY = Math.max(...elevations);
  const width = 610,
    height = 135;
  const scale = Math.min(
    width / Math.max(last.horizontal_m - first.horizontal_m, 1),
    height / Math.max(maxY - minY, 1),
  );
  const spanY = height / scale;
  const baseY = (minY + maxY - spanY) / 2;
  const leftX = (first.horizontal_m + last.horizontal_m - width / scale) / 2;
  const x = (horizontal: number) => 68 + (horizontal - leftX) * scale;
  const y = (elevation: number) => 180 - (elevation - baseY) * scale;
  let marker: (typeof points)[number] | undefined;
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
      horizontal_m:
        a.horizontal_m + fraction * (b.horizontal_m - a.horizontal_m),
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
          ? `; vehicle at ${siToDisplay(marker.distance_m, lengthUnit).toFixed(1)} ${lengthUnit}, elevation ${siToDisplay(marker.elevation_m, lengthUnit).toFixed(1)} ${lengthUnit}`
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
              {siToDisplay(elevation, lengthUnit).toFixed(1)}
            </text>
          </g>
        );
      })}
      <text x="68" y="24" fill="currentColor" fontSize="13">
        Elevation ({lengthUnit})
      </text>
      <polyline
        points={points
          .map((p) => `${x(p.horizontal_m)},${y(p.elevation_m)}`)
          .join(' ')}
        fill="none"
        stroke="var(--mantine-primary-color-filled)"
        strokeWidth="3"
      />
      {marker && (
        <g data-testid="course-position" data-distance={marker.distance_m}>
          <line
            x1={x(marker.horizontal_m)}
            x2={x(marker.horizontal_m)}
            y1="40"
            y2="185"
            stroke="var(--mantine-color-text)"
            strokeDasharray="4 4"
          />
          <circle
            cx={x(marker.horizontal_m)}
            cy={y(marker.elevation_m)}
            r="6"
            fill="var(--mantine-primary-color-filled)"
            stroke="var(--mantine-color-body)"
            strokeWidth="2"
          />
        </g>
      )}
      <text x="68" y="205" fill="currentColor" fontSize="12">
        {siToDisplay(leftX, lengthUnit).toFixed(1)}
      </text>
      <text x="678" y="205" textAnchor="end" fill="currentColor" fontSize="12">
        {siToDisplay(leftX + width / scale, lengthUnit).toFixed(1)}
      </text>
      <text
        x="373"
        y="233"
        textAnchor="middle"
        fill="currentColor"
        fontSize="13"
      >
        Horizontal distance ({lengthUnit})
      </text>
    </svg>
  );
}
