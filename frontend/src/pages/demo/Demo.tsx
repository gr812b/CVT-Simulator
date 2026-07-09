import { useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { LoadingOverlay } from '@components/loadingOverlay/LoadingOverlay';
import { useLoading } from '@contexts/LoadingContext';
import { getDefaultRunSetup } from '@api/client';
import { useRunSimulation } from '@hooks/useRunSimulation';
import styles from '@pages/input/Input.module.scss';

/** Runs the seeded Baja database baseline using the default tune/load/execution choices. */
export const Demo = () => {
  const navigate = useNavigate();
  const { isLoading, loadingMessage, setLoading } = useLoading();
  const { runLibrarySetup } = useRunSimulation();
  const started = useRef(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (started.current) return;
    started.current = true;
    void (async () => {
      try {
        setLoading(true, 'Loading seeded Baja demo setup…');
        const setup = await getDefaultRunSetup();
        const completed = await runLibrarySetup(setup.selection);
        if (!completed) setError('The seeded Baja demo did not complete. See the simulation error above.');
      } catch (caught) {
        setError(caught instanceof Error ? caught.message : String(caught));
        setLoading(false);
      }
    })();
  }, [runLibrarySetup, setLoading]);

  if (error !== null) {
    return (
      <div className={styles.input}>
        <div className={styles.parameterInformationContainer}>
          <h1>Demo unavailable</h1>
          <p>{error}</p>
          <button type="button" onClick={() => navigate('/input')}>Open run setup</button>
        </div>
      </div>
    );
  }

  return <div className={styles.input}><LoadingOverlay isVisible={isLoading} message={loadingMessage} /></div>;
};
