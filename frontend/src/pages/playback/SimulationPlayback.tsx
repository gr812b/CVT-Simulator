import type { components } from '@api/generated/backend';
import { CoursePlayback } from './CoursePlayback';
import { useCallback, useEffect, useMemo, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import type { ResolvedSceneGeometry } from '@components/scene3DViewer/sceneSpec';
import type { SimulationCaseDocument, SimulationResult } from '@api/client';
import { Alert, Group, Paper, SimpleGrid, Stack, Title } from '@mantine/core';
import { ActionButton as Button } from '@components/button/ActionButton';
import { Graph2D } from '@components/graph2D/graph2D';
import { Scene3DViewer } from '@components/scene3DViewer/Scene3DViewer';
import { Playbar } from '@components/playbar/Playbar';
import { ReportReplayController } from '@utils/reportReplay';
import { downloadReportTableCsv } from '@utils/csvExport';
import { reportAxisTimes } from '@utils/reportTable';
import { buildReportGraphs } from './reportGraphs';
import styles from './Playback.module.scss';

/** Shared playback for owned results and the anonymous retained demo. */
export function SimulationPlayback({
  result,
  document,
  sceneGeometry,
  course,
  navigation,
}: {
  result: SimulationResult;
  document: SimulationCaseDocument;
  sceneGeometry: ResolvedSceneGeometry;
  course: components['schemas']['RunResultResponse']['course'];
  navigation: { label: string; to: string }[];
}) {
  const navigate = useNavigate();
  const rootRef = useRef<HTMLDivElement>(null);
  const footerRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const footer = footerRef.current;
    if (!footer) return;
    const observer = new ResizeObserver(() =>
      rootRef.current?.style.setProperty(
        '--playbar-height',
        `${footer.getBoundingClientRect().height}px`,
      ),
    );
    observer.observe(footer);
    return () => observer.disconnect();
  }, []);
  const table = result.report_table;
  const timeValues = useMemo(() => reportAxisTimes(table), [table]);
  const replayController = useMemo(
    () => new ReportReplayController(timeValues),
    [timeValues],
  );
  const replayRef = useRef(replayController);
  const categories = useMemo(() => buildReportGraphs(table), [table]);
  useEffect(() => {
    replayRef.current = replayController;
    return () => replayController.dispose();
  }, [replayController]);
  const pauseNavigate = useCallback(
    (path: string) => {
      replayRef.current.pause();
      navigate(path);
    },
    [navigate],
  );
  return (
    <div ref={rootRef} className={styles.playback}>
      {result.metrics.completed === false && <Alert color="yellow" title="Partial run" mx="lg" mt="md">
        Saved through {result.metrics.duration_s.toFixed(2)} simulated seconds. Stop: {result.metrics.termination_reason.replace(/_/g, ' ')}.
        Playback and CSV contain the saved portion.
      </Alert>}
      <Group justify="space-between" className={styles.buttonsContainer}>
        <Group gap="sm">
          {navigation.map((item) => (
            <Button
              key={item.to}
              variant="default"
              onClick={() => pauseNavigate(item.to)}
            >
              {item.label}
            </Button>
          ))}
        </Group>
        <Button
          variant="light"
          onClick={() => downloadReportTableCsv(table, 'playback_data')}
        >
          Download CSV
        </Button>
      </Group>
      <Stack gap="lg">
        <Paper withBorder className={styles.sceneContainer}>
          <Scene3DViewer
            replayController={replayController}
            result={result}
            document={document}
            resolvedGeometry={sceneGeometry}
          />
        </Paper>
        {course && (
          <CoursePlayback
            course={course}
            table={table}
            replayController={replayController}
          />
        )}
        {categories.map((category) => (
          <Paper
            key={category.title}
            component="section"
            withBorder
            p={{ base: 'sm', sm: 'lg' }}
          >
            <Stack gap="md">
              <Title order={2} size="h3">
                {category.title}
              </Title>
              <SimpleGrid
                cols={{ base: 1, md: Math.min(2, category.graphs.length) }}
                spacing="lg"
              >
                {category.graphs.map((graph) => (
                  <Graph2D
                    key={graph.config.title}
                    {...graph}
                    className={styles.plotContainer}
                    replayController={replayController}
                  />
                ))}
              </SimpleGrid>
            </Stack>
          </Paper>
        ))}
      </Stack>
      <div
        ref={footerRef}
        className={styles.playbarContainer}
        role="region"
        aria-label="Playback controls"
      >
        <Playbar replayController={replayController} times={timeValues} />
      </div>
    </div>
  );
}
