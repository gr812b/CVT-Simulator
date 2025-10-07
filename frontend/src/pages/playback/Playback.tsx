import { useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { Page } from '@components/graph2D/page';
import { useSimulation } from '@contexts/SimulationContext';

export const Playback = () => {
    const navigate = useNavigate();
    const { simulationResult, isSimulationReady } = useSimulation();

    // Redirect to input page if no simulation data is available
    useEffect(() => {
        if (!isSimulationReady) {
            console.warn('No simulation data available. Redirecting to input page.');
            navigate('/input');
        }
    }, [isSimulationReady, navigate]);

    // Don't render anything if no simulation data
    if (!isSimulationReady || !simulationResult) {
        return null;
    }

    // Log simulation data to console
    console.log('Simulation Result:', simulationResult);
    console.log('Number of data points:', simulationResult.data.length);

    return (
        <div>
            <Page />
        </div>
    );
};