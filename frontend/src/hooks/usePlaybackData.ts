import { useMemo, useState, useEffect } from 'react';
import { useLocation } from 'react-router-dom';
import type { RunResponse } from '@utils/api';
import { buildGraphs } from '@utils/graph';
import { ReplayController, ReplayEventType } from '@utils/ReplayController';
import { timeAccessor } from '@types';

// Type the location state
interface PlaybackLocationState {
  simulationResult: RunResponse;
}

interface UsePlaybackDataReturn {
  graphs: ReturnType<typeof buildGraphs>;
  replayController: ReplayController;
  times: number[];
  activeIndex: number;
}

export const usePlaybackData = (): UsePlaybackDataReturn | null => {
  const location = useLocation();
  const simulationResult = (location.state as PlaybackLocationState | null)?.simulationResult;

  const [activeIndex, setActiveIndex] = useState<number>(0);

  const replayController = useMemo(() => {
    return simulationResult ? new ReplayController(simulationResult.data) : null;
  }, [simulationResult]);

  const times = useMemo(() => {
    return simulationResult ? simulationResult.data.map(timeAccessor) : [];
  }, [simulationResult]);

  const graphs = useMemo(() => {
    return simulationResult ? buildGraphs(simulationResult) : [];
  }, [simulationResult]);

  useEffect(() => {
    if (!replayController) return;
    const cleanup = replayController.on((event) => {
      if (event.type === ReplayEventType.Progress) {
        setActiveIndex(event.currentIndex);
      }
    });
    return cleanup;
  }, [replayController]);

  // Return null if simulation data is not available
  if (!simulationResult || !replayController) {
    return null;
  }

  return {
    graphs,
    replayController,
    times,
    activeIndex,
  };
};