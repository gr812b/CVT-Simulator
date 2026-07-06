import { useNavigate } from 'react-router-dom';
import { useLoading } from '@contexts/LoadingContext';
import { useSimulationCase } from '@contexts/SimulationCaseContext';
import { useSimulationRun } from '@contexts/SimulationRunContext';
import { getSimulationResult, submitSimulationRun, validateSimulationCase, waitForSimulationRun, type SimulationCaseDocument } from '@api/client';

/** Submit one complete CINDER document, wait for its run resource, then navigate to playback. */
export function useRunSimulation() {
  const navigate = useNavigate();
  const { setLoading } = useLoading();
  const { setValidation } = useSimulationCase();
  const { setActiveRun, setCompletedRun } = useSimulationRun();

  const runSimulation = async (document: SimulationCaseDocument): Promise<boolean> => {
    try {
      setLoading(true, 'Validating complete simulation case...');
      const validation = await validateSimulationCase(document);
      setValidation(validation);
      if (!validation.isValid) {
        throw new Error('CINDER found validation errors. Fix the highlighted fields before running.');
      }

      setLoading(true, 'Starting simulation...');
      const submitted = await submitSimulationRun(document);
      setActiveRun(submitted);
      setLoading(true, 'Running simulation...');
      const completedStatus = await waitForSimulationRun(submitted.id);
      setActiveRun(completedStatus);

      setLoading(true, 'Preparing playback data...');
      const completedRun = await getSimulationResult(submitted.id);
      setCompletedRun(completedRun);
      navigate('/playback');
      return true;
    } catch (error) {
      alert(`Simulation failed: ${error instanceof Error ? error.message : String(error)}`);
      return false;
    } finally {
      setLoading(false);
    }
  };

  return { runSimulation };
}
