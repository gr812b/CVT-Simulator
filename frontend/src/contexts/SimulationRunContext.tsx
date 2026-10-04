import { createContext, useCallback, useContext, useMemo, useState, type ReactNode } from 'react';
import {
  getSimulationResult,
  getSimulationRun,
  rerunSimulationRun,
  waitForSimulationRun,
  type CompletedSimulationRun,
  type RunStatus,
} from '@api/client';

interface SimulationRunContextValue {
  completedRun: CompletedSimulationRun | null;
  activeRun: RunStatus | null;
  setCompletedRun: (run: CompletedSimulationRun) => void;
  setActiveRun: (run: RunStatus | null) => void;
  restoreCompletedRun: () => Promise<CompletedSimulationRun | null>;
  rerunCompletedRun: (runId?: string) => Promise<CompletedSimulationRun>;
  clearRun: () => void;
}

const SimulationRunContext = createContext<SimulationRunContextValue | undefined>(undefined);

export const SimulationRunProvider = ({ children }: { children: ReactNode }) => {
  const [completedRun, setCompletedRunState] = useState<CompletedSimulationRun | null>(null);
  const [activeRun, setActiveRunState] = useState<RunStatus | null>(null);

  const setCompletedRun = useCallback((next: CompletedSimulationRun) => {
    setCompletedRunState(next);
    setActiveRunState(next.run);
  }, []);

  const setActiveRun = useCallback((next: RunStatus | null) => {
    setActiveRunState(next);
  }, []);

  const restoreCompletedRun = useCallback(async (): Promise<CompletedSimulationRun | null> => {
    if (completedRun !== null) return completedRun;
    const runId = activeRun?.id ?? null;
    if (runId === null) return null;
    const status = await getSimulationRun(runId);
    setActiveRunState(status);
    if (status.status !== 'completed') return null;
    const restored = await getSimulationResult(runId);
    setCompletedRunState(restored);
    return restored;
  }, [completedRun, activeRun?.id]);

  const rerunCompletedRun = useCallback(
    async (runId?: string): Promise<CompletedSimulationRun> => {
      const sourceRunId = runId ?? activeRun?.id ?? completedRun?.run.id ?? null;
      if (!sourceRunId) throw new Error('No completed library run is available to rerun.');
      const submitted = await rerunSimulationRun(sourceRunId);
      setActiveRunState(submitted);
      const completedStatus = await waitForSimulationRun(submitted.id);
      setActiveRunState(completedStatus);
      const rerun = await getSimulationResult(submitted.id);
      setCompletedRunState(rerun);
      return rerun;
    },
    [activeRun?.id, completedRun?.run.id],
  );

  const clearRun = useCallback(() => {
    setCompletedRunState(null);
    setActiveRunState(null);
  }, []);

  const value = useMemo<SimulationRunContextValue>(
    () => ({
      completedRun,
      activeRun,
      setCompletedRun,
      setActiveRun,
      restoreCompletedRun,
      rerunCompletedRun,
      clearRun,
    }),
    [
      completedRun,
      activeRun,
      setCompletedRun,
      setActiveRun,
      restoreCompletedRun,
      rerunCompletedRun,
      clearRun,
    ],
  );

  return <SimulationRunContext.Provider value={value}>{children}</SimulationRunContext.Provider>;
};

// eslint-disable-next-line react-refresh/only-export-components
export function useSimulationRun(): SimulationRunContextValue {
  const context = useContext(SimulationRunContext);
  if (context === undefined)
    throw new Error('useSimulationRun must be used inside SimulationRunProvider.');
  return context;
}
