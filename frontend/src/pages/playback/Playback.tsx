import { useEffect, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import styles from './Playback.module.scss';
import { LoadingOverlay } from '@components/loadingOverlay/LoadingOverlay';
import { useLoading } from '@contexts/LoadingContext';
import { useSimulationRun } from '@contexts/SimulationRunContext';
import { SimulationPlayback } from './SimulationPlayback';

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

  return (
    <SimulationPlayback
      result={displayedRun.result}
      document={displayedRun.inputDocumentSnapshot}
      navigation={[
        { label: 'Run details', to: `/runs/${displayedRun.run.id}` },
        { label: 'Run history', to: '/runs' },
      ]}
    />
  );
};
