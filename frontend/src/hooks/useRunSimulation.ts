import { useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { useLoading } from '@contexts/LoadingContext';
import { useSimulationRun } from '@contexts/SimulationRunContext';
import {
  submitLibraryRun,
  submitSimulationRun,
  type LibraryRunSelection,
  type RunStatus,
  type SimulationCaseDocument,
} from '@api/client';
import { useRunActivity } from '../features/experiments/RunActivity';

/** Signed-in dashboard shortcuts hand off to the same durable run page. */
export function useRunSimulation() {
  const navigate = useNavigate();
  const { setLoading } = useLoading();
  const { setActiveRun } = useSimulationRun();
  const { refresh } = useRunActivity();
  const pending = useRef<{ fingerprint: string; key: string } | null>(null);
  const submit = async (
    fingerprint: string,
    action: (key: string) => Promise<RunStatus>,
  ): Promise<boolean> => {
    if (pending.current?.fingerprint !== fingerprint)
      pending.current = { fingerprint, key: crypto.randomUUID() };
    try {
      setLoading(true, 'Checking and queuing simulation…');
      const run = await action(pending.current.key);
      setActiveRun(run);
      pending.current = null;
      await refresh();
      navigate(`/runs/${run.id}`);
      return true;
    } catch (cause) {
      window.alert(
        cause instanceof Error
          ? cause.message
          : 'The simulation could not be queued.',
      );
      return false;
    } finally {
      setLoading(false);
    }
  };
  return {
    runLibrarySetup: (selection: LibraryRunSelection) =>
      submit(JSON.stringify(selection), (key) =>
        submitLibraryRun(selection, key),
      ),
    runSimulationDocument: (document: SimulationCaseDocument) =>
      submit(JSON.stringify(document), (key) =>
        submitSimulationRun(document, key),
      ),
  };
}
