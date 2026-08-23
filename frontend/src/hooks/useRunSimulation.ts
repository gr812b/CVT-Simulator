import { useNavigate } from 'react-router-dom';
import { useLoading } from '@contexts/LoadingContext';
import { useSimulationRun } from '@contexts/SimulationRunContext';
import {
  getSimulationResult,
  submitLibraryRun,
  submitSimulationRun,
  waitForSimulationRun,
  type LibraryRunSelection,
  type SimulationCaseDocument,
} from '@api/client';

/** Submit a database-backed library selection, wait for completion, then navigate to playback. */
export function useRunSimulation() {
  const navigate = useNavigate();
  const { setLoading } = useLoading();
  const { setActiveRun, setCompletedRun } = useSimulationRun();

  const runLibrarySetup = async (selection: LibraryRunSelection): Promise<boolean> => {
    try {
      setLoading(true, 'Starting database-backed simulation...');
      const submitted = await submitLibraryRun(selection);
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

  const runSimulationDocument = async (document: SimulationCaseDocument): Promise<boolean> => {
    try {
      setLoading(true, 'Starting custom simulation...');
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

  return { runLibrarySetup, runSimulationDocument };
}
