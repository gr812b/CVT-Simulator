import { useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { convertSimulationData, UNIT_PRESETS } from '@utils/conversion';
import type { RunResponse } from '@utils/api';
import demoRaw from '@assets/data/demo.json';

// Pre-convert once at module load — avoids re-processing on every render
const demoResult: RunResponse = convertSimulationData(
    demoRaw as unknown as RunResponse,
    UNIT_PRESETS.BAJA
);

export const Demo = () => {
    const navigate = useNavigate();

    useEffect(() => {
        navigate('/playback', {
            replace: true,
            state: { simulationResult: demoResult },
        });
    }, [navigate]);

    return null;
};
