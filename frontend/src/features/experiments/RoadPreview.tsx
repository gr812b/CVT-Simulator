import { useEffect, useState } from 'react';
import { Alert, Group, Loader, Stack, Text } from '@mantine/core';
import { resolveRoad, message, type Road, type RoadResolution } from './api';

export function RoadPreview({ road }: { road: Road }) {
  const [data, setData] = useState<RoadResolution | null>(null);
  const [error, setError] = useState<string | null>(null);
  const key = JSON.stringify(road);
  useEffect(() => {
    const controller = new AbortController();
    setData(null);
    setError(null);
    void resolveRoad(JSON.parse(key) as Road, controller.signal)
      .then((next) => {
        if (!controller.signal.aborted) setData(next);
      })
      .catch((cause) => {
        if (!controller.signal.aborted) setError(message(cause));
      });
    return () => controller.abort();
  }, [key]);
  if (error) return <Alert color="red">{error}</Alert>;
  if (!data) return <Loader size="sm" aria-label="Loading road preview" />;
  const span = Math.max(data.maximum_elevation_m - data.minimum_elevation_m, 1);
  const points = data.points
    .map(
      (p) =>
        `${40 + (620 * p.distance_m) / Math.max(data.length_m, 1)},${160 - (120 * (p.elevation_m - data.minimum_elevation_m)) / span}`,
    )
    .join(' ');
  return (
    <Stack gap="xs">
      <svg
        viewBox="0 0 700 200"
        role="img"
        aria-label="Road elevation preview"
        style={{ width: '100%', maxHeight: 230 }}
      >
        <line
          x1="40"
          y1="170"
          x2="660"
          y2="170"
          stroke="var(--mantine-color-dimmed)"
        />
        <polyline
          points={points}
          fill="none"
          stroke="var(--mantine-primary-color-filled)"
          strokeWidth="3"
        />
        <text x="40" y="192" fill="currentColor" fontSize="12">
          0 m
        </text>
        <text
          x="660"
          y="192"
          textAnchor="end"
          fill="currentColor"
          fontSize="12"
        >
          {data.length_m.toFixed(0)} m along road
        </text>
      </svg>
      <Group justify="space-between">
        <Text size="sm">
          {road.features.length} road section
          {road.features.length === 1 ? '' : 's'}
        </Text>
        <Text size="sm">
          Maximum angle{' '}
          {((data.maximum_absolute_grade_rad * 180) / Math.PI).toFixed(1)}°
        </Text>
      </Group>
      <Text size="xs" c="dimmed">
        Elevation is scaled to fit.{' '}
        {road.endpoint === 'continue_grade'
          ? 'The final grade continues after the route.'
          : 'The road becomes flat after the route.'}
      </Text>
    </Stack>
  );
}
