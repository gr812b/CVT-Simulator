import { useMemo } from 'react';
import { useLocation } from 'react-router-dom';
import type { RunResponse } from '@utils/api';
import { buildGraphs } from '@utils/graph';
import { ReplayController } from '@utils/ReplayController';
import { timeAccessor } from '@types';

// Type the location state
interface PlaybackLocationState {
  simulationResult: RunResponse;
}

interface UsePlaybackDataReturn {
  graphs: ReturnType<typeof buildGraphs>;
  replayController: ReplayController;
  times: number[];
}

export const usePlaybackData = (): UsePlaybackDataReturn | null => {
  const location = useLocation();
  const simulationResult = (location.state as PlaybackLocationState | null)?.simulationResult;

  const replayController = useMemo(() => {
    return simulationResult ? new ReplayController(simulationResult.data) : null;
  }, [simulationResult]);

  const times = useMemo(() => {
    return simulationResult ? simulationResult.data.map(timeAccessor) : [];
  }, [simulationResult]);

  const graphs = useMemo(() => {
    return simulationResult ? buildGraphs(simulationResult) : [];
  }, [simulationResult]);

  // Return null if simulation data is not available
  if (!simulationResult || !replayController) {
    return null;
  }

  return {
    graphs,
    replayController,
    times,
  };
};