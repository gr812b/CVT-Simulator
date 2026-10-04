import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import styles from './Playback.module.scss';
import { Button } from '@components/button/Button';
import { Graph2D } from '@components/graph2D/graph2D';
import { Scene3DViewer } from '@components/scene3DViewer/Scene3DViewer';
import { Playbar } from '@components/playbar/Playbar';
import { LoadingOverlay } from '@components/loadingOverlay/LoadingOverlay';
import { useLoading } from '@contexts/LoadingContext';
import { useSimulationRun } from '@contexts/SimulationRunContext';
import { ReportReplayController } from '@utils/reportReplay';
import { downloadReportTableCsv } from '@utils/csvExport';
import { reportAxisTimes } from '@utils/reportTable';
import { buildReportGraphs } from './reportGraphs';
import Home from '@assets/icons/home.svg?react';
import Edit from '@assets/icons/edit.svg?react';
import Download from '@assets/icons/arrow_down_circle.svg?react';

const PlaybackContent = ({
  run,
}: {
  run: NonNullable<ReturnType<typeof useSimulationRun>['completedRun']>;
}) => {
  const navigate = useNavigate();
  const table = run.result.report_table;
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
    <div className={styles.playback}>
      <div className={styles.buttonsContainer}>
        <div className={styles.leftButtons}>
          <Button
            text="Run details"
            icon={Home}
            className={styles.navigateButton}
            onClick={() => pauseNavigate(`/runs/${run.run.id}`)}
          />
          <Button
            text="Run history"
            icon={Edit}
            className={styles.navigateButton}
            onClick={() => pauseNavigate('/runs')}
          />
        </div>
        <div className={styles.rightButtons}>
          <Button
            text="Download CSV"
            icon={Download}
            className={styles.navigateButton}
            onClick={() => downloadReportTableCsv(table, 'playback_data')}
          />
        </div>
      </div>

      <div className={styles.displayGrid}>
        <div className={styles.sceneContainer}>
          <Scene3DViewer
            replayController={replayController}
            result={run.result}
            document={run.inputDocumentSnapshot}
          />
        </div>
        {categories.map((category) => (
          <div key={category.title} className={styles.graphCategory}>
            <h2 className={styles.categoryTitle}>{category.title}</h2>
            <div className={styles.categoryGraphs}>
              {category.graphs.map((graph) => (
                <Graph2D
                  key={graph.config.title}
                  {...graph}
                  replayController={replayController}
                />
              ))}
            </div>
          </div>
        ))}
      </div>

      <div className={styles.playbarContainer}>
        <Playbar replayController={replayController} times={timeValues} />
      </div>
    </div>
  );
};

export const Playback = () => {
  const navigate = useNavigate();
  const { completedRun, restoreCompletedRun, activeRun } = useSimulationRun();
  const [params] = useSearchParams();
  const requestedId = params.get('run') ?? undefined;
  const displayedRun =
    completedRun && (!requestedId || completedRun.run.id === requestedId)
      ? completedRun
      : null;
  const { isLoading, loadingMessage, setLoading } = useLoading();
  const [restoreError, setRestoreError] = useState<string | null>(null);

  useEffect(() => {
    if (displayedRun !== null) return;
    let disposed = false;
    setRestoreError(null);
    setLoading(true, 'Restoring completed simulation...');
    void restoreCompletedRun(requestedId)
      .then((run) => {
        if (run === null && !disposed) {
          setRestoreError(
            'Choose a completed run from Activity to open its playback.',
          );
        }
      })
      .catch((error) => {
        if (!disposed)
          setRestoreError(
            error instanceof Error ? error.message : String(error),
          );
      })
      .finally(() => {
        if (!disposed) setLoading(false);
      });
    return () => {
      disposed = true;
      setLoading(false);
    };
  }, [displayedRun, restoreCompletedRun, setLoading, requestedId]);

  if (displayedRun === null) {
    return (
      <div className={styles.playback}>
        <LoadingOverlay isVisible={isLoading} message={loadingMessage} />
        <div className={styles.emptyState}>
          <h1>Playback unavailable</h1>
          <p>{restoreError ?? 'Looking for a completed simulation run...'}</p>
          <button type="button" onClick={() => navigate('/input')}>
            Back to run setup
          </button>
          {(requestedId || activeRun?.id) && (
            <button
              type="button"
              onClick={() => navigate(`/runs/${requestedId ?? activeRun!.id}`)}
            >
              View run status or rerun
            </button>
          )}
        </div>
      </div>
    );
  }

  return <PlaybackContent run={displayedRun} />;
};
