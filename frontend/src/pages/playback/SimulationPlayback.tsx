import type { components } from '@api/generated/backend';
import { CoursePlayback } from './CoursePlayback';
import { useCallback, useEffect, useMemo, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import type { ResolvedSceneGeometry } from '@components/scene3DViewer/sceneSpec';
import type { SimulationCaseDocument, SimulationResult } from '@api/client';
import { Alert, Group, Paper, Stack } from '@mantine/core';
import { ActionButton as Button } from '@components/button/ActionButton';
import { PlotWorkspace } from './PlotWorkspace';
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
  forceSource,
  document,
  sceneGeometry,
  course,
  navigation,
  live = false,
}: {
  forceSource?: string;
  result: SimulationResult;
  document: SimulationCaseDocument;
  sceneGeometry: ResolvedSceneGeometry;
  course: components['schemas']['RunResultResponse']['course'];
  navigation: { label: string; to: string }[];
  live?: boolean;
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
      {result.metrics.completed === false && (
        <Alert
          color={live ? 'blue' : 'yellow'}
          title={live ? 'Live progress' : 'Partial run'}
          mx="lg"
          mt="md"
        >
          Saved through {result.metrics.duration_s.toFixed(2)} simulated
          seconds.{' '}
          {live
            ? 'The simulation is still running.'
            : `Stopped: ${result.metrics.termination_reason.replace(/_/g, ' ')}.`}
        </Alert>
      )}
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
      <div className={styles.workspace}>
        <Stack gap="md" className={styles.visualPanel}>
          <Paper withBorder className={styles.sceneContainer}>
            <Scene3DViewer
              forceSource={forceSource}
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
        </Stack>
        <PlotWorkspace categories={categories} controller={replayController} />
      </div>
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
