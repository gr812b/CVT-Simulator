import { useNavigate } from 'react-router-dom';
import { useLoading } from '@contexts/LoadingContext';
import type { ParameterState } from '@types';
import { runSimulationStreaming } from '@utils/api';
import { mapParametersToApiBody } from '@utils/parameterMapping';
import { convertSimulationData, UNIT_PRESETS } from '@utils/conversion';

/**
 * Custom hook for running simulations with loading state and navigation
 * Encapsulates the entire simulation execution flow including:
 * - Loading state management
 * - API call with progress updates
 * - Unit conversion
 * - Navigation to playback on success
 * - Error handling
 */
export const useRunSimulation = () => {
  const navigate = useNavigate();
  const { setLoading } = useLoading();

  const runSimulation = async (parameters: ParameterState): Promise<void> => {
    try {
      setLoading(true, 'Running simulation...');

      const apiBody = mapParametersToApiBody(parameters);
      const result = await runSimulationStreaming(
        apiBody,
        (percent) => {
          setLoading(true, `Running simulation... ${percent.toFixed(1)}%`);
        }
      );
      const unitConversion = convertSimulationData(result, UNIT_PRESETS.BAJA);

      navigate('/playback', { 
        state: { simulationResult: unitConversion }
      });
    } catch (error) {
      console.error('Simulation failed:', error);
      alert('Simulation failed. Please check your parameters and try again.');
      throw error;
    } finally {
      setLoading(false);
    }
  };

  return { runSimulation };
};
