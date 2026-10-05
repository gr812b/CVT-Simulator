import { useEffect, useState } from 'react';
import { Group, Paper, Stack, Text, Title } from '@mantine/core';
import type { components } from '@api/generated/backend';
import type { ReportTable } from '@api/client';
import { CourseChart } from '@components/course/CourseChart';
import { ReportReplayController, ReplayEventType } from '@utils/reportReplay';
import { valueAt } from '@utils/reportTable';

export function CoursePlayback({
  course,
  table,
  replayController,
}: {
  course: components['schemas']['CourseProfile'];
  table: ReportTable;
  replayController: ReportReplayController;
}) {
  const [index, setIndex] = useState(0);
  useEffect(() => {
    setIndex(replayController.visualSample().lowerIndex);
    return replayController.on((event) => {
      if (event.type === ReplayEventType.Progress) setIndex(event.currentIndex);
    });
  }, [replayController]);
  const distance = valueAt(table, course.distance_column_key, index);
  return (
    <Paper
      component="section"
      withBorder
      p={{ base: 'sm', sm: 'lg' }}
      aria-label="Course view"
    >
      <Stack gap="xs">
        <Group justify="space-between">
          <div>
            <Title order={2} size="h3">
              Course
            </Title>
            <Text size="sm" c="dimmed">
              {course.name}
            </Text>
          </div>
          <Text size="sm">
            {distance === null
              ? 'Position unavailable'
              : `Vehicle: ${distance.toFixed(1)} m`}
          </Text>
        </Group>
        <CourseChart
          points={course.points}
          position={distance}
          label="Recorded course elevation"
        />
        <Text size="xs" c="dimmed">
          From this run’s saved road profile. Elevation is relative to distance
          zero; axes are scaled independently.
        </Text>
      </Stack>
    </Paper>
  );
}
