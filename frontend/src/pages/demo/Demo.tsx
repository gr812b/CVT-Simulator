import { useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { LoadingOverlay } from '@components/loadingOverlay/LoadingOverlay';
import { useLoading } from '@contexts/LoadingContext';
import { useSimulationCase } from '@contexts/SimulationCaseContext';
import { loadPreset } from '@api/client';
import { useRunSimulation } from '@hooks/useRunSimulation';
import styles from '@pages/input/Input.module.scss';

const BASELINE_PRESET_ID = 'baja-launch-baseline';

/** Runs the same CINDER document exposed as the Baja tuned-launch baseline. */
export const Demo = () => {
  const navigate = useNavigate();
  const { isLoading, loadingMessage, setLoading } = useLoading();
  const { replaceDocument } = useSimulationCase();
  const { runSimulation } = useRunSimulation();
  const started = useRef(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (started.current) return;
    started.current = true;
    void (async () => {
      try {
        setLoading(true, 'Loading Baja tuned-launch demo…');
        const preset = await loadPreset(BASELINE_PRESET_ID);
        replaceDocument(preset.simulationCase, {
          presetId: preset.id,
          name: preset.name,
          description: preset.description,
        });
        const completed = await runSimulation(preset.simulationCase);
        if (!completed) setError('The Baja tuned-launch demo did not complete. See the simulation error above.');
      } catch (caught) {
        setError(caught instanceof Error ? caught.message : String(caught));
        setLoading(false);
      }
    })();
  }, [replaceDocument, runSimulation, setLoading]);

  if (error !== null) {
    return (
      <div className={styles.input}>
        <div className={styles.parameterInformationContainer}>
          <h1>Demo unavailable</h1>
          <p>{error}</p>
          <button type="button" onClick={() => navigate('/input')}>Open simulator</button>
        </div>
      </div>
    );
  }

  return <div className={styles.input}><LoadingOverlay isVisible={isLoading} message={loadingMessage} /></div>;
};
