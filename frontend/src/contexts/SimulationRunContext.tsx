import { createContext, useCallback, useContext, useMemo, useState, type ReactNode } from 'react';
import { getSimulationResult, getSimulationRun, type CompletedSimulationRun, type RunStatus } from '@api/client';

const RUN_ID_STORAGE_KEY = 'cinder-active-run-id-v2';

interface SimulationRunContextValue {
  completedRun: CompletedSimulationRun | null;
  activeRun: RunStatus | null;
  setCompletedRun: (run: CompletedSimulationRun) => void;
  setActiveRun: (run: RunStatus | null) => void;
  restoreCompletedRun: () => Promise<CompletedSimulationRun | null>;
  clearRun: () => void;
}

const SimulationRunContext = createContext<SimulationRunContextValue | undefined>(undefined);

export const SimulationRunProvider = ({ children }: { children: ReactNode }) => {
  const [completedRun, setCompletedRunState] = useState<CompletedSimulationRun | null>(null);
  const [activeRun, setActiveRunState] = useState<RunStatus | null>(null);

  const setCompletedRun = useCallback((next: CompletedSimulationRun) => {
    setCompletedRunState(next);
    setActiveRunState(next.run);
    sessionStorage.setItem(RUN_ID_STORAGE_KEY, next.run.id);
  }, []);

  const setActiveRun = useCallback((next: RunStatus | null) => {
    setActiveRunState(next);
    if (next === null) sessionStorage.removeItem(RUN_ID_STORAGE_KEY);
    else sessionStorage.setItem(RUN_ID_STORAGE_KEY, next.id);
  }, []);

  const restoreCompletedRun = useCallback(async (): Promise<CompletedSimulationRun | null> => {
    if (completedRun !== null) return completedRun;
    const runId = sessionStorage.getItem(RUN_ID_STORAGE_KEY);
    if (runId === null) return null;
    const status = await getSimulationRun(runId);
    setActiveRunState(status);
    if (status.status !== 'completed') return null;
    const restored = await getSimulationResult(runId);
    setCompletedRunState(restored);
    return restored;
  }, [completedRun]);

  const clearRun = useCallback(() => {
    setCompletedRunState(null);
    setActiveRunState(null);
    sessionStorage.removeItem(RUN_ID_STORAGE_KEY);
  }, []);

  const value = useMemo<SimulationRunContextValue>(() => ({
    completedRun,
    activeRun,
    setCompletedRun,
    setActiveRun,
    restoreCompletedRun,
    clearRun,
  }), [completedRun, activeRun, setCompletedRun, setActiveRun, restoreCompletedRun, clearRun]);

  return <SimulationRunContext.Provider value={value}>{children}</SimulationRunContext.Provider>;
};

// eslint-disable-next-line react-refresh/only-export-components
export function useSimulationRun(): SimulationRunContextValue {
  const context = useContext(SimulationRunContext);
  if (context === undefined) throw new Error('useSimulationRun must be used inside SimulationRunProvider.');
  return context;
}
