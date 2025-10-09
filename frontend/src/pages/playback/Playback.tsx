import { useEffect } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import { Page } from '@components/graph2D/page';
import type { RunResponse } from '@utils/api';

// Type the location state
interface PlaybackLocationState {
  simulationResult: RunResponse;
}

export const Playback = () => {
    const navigate = useNavigate();
    const location = useLocation();
    const simulationResult = (location.state as PlaybackLocationState | null)?.simulationResult;

    // Redirect to input page if no simulation data is available
    useEffect(() => {
        if (!simulationResult) {
            console.warn('No simulation data available. Redirecting to input page.');
            navigate('/input');
        }
    }, [simulationResult, navigate]);

    // Don't render anything if no simulation data
    if (!simulationResult) {
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