import { CourseChart } from '@components/course/CourseChart';
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
  return (
    <Stack gap="xs">
      <CourseChart points={data.points} />
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
