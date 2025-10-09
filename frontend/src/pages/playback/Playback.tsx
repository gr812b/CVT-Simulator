import { useNavigate, useLocation } from 'react-router-dom';
import type { RunResponse } from '@utils/api';
import styles from './Playback.module.scss';
import { Button } from '@components/button/Button';
import { Graph2D, type Graph2DProps } from '@components/graph2D/graph2D';
import Home from '@assets/icons/home.svg?react';
import Edit from '@assets/icons/edit.svg?react';
import { useEffect, useState } from 'react';
import { buildGraphs } from '@utils/graph';


// Type the location state
interface PlaybackLocationState {
  simulationResult: RunResponse;
}

export const Playback = () => {

    const navigate = useNavigate();
    const location = useLocation();
    const simulationResult = (location.state as PlaybackLocationState | null)?.simulationResult;
    const [graphs, setGraphs] = useState<Graph2DProps[]>([]);

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

    useEffect(() => {
        setGraphs(buildGraphs(simulationResult));
    }, [simulationResult]);

    return (
        <div className={styles.playback}>
            <div className={styles.buttonsContainer}>
            <Button
                text={'Home'}
                icon={Home}
                className={styles.navigateButton}
                onClick={() => navigate('/')}
            />
            <Button
                text={'Edit'}
                icon={Edit}
                className={styles.navigateButton}
                onClick={() => navigate('/input')}
            />
            </div>
            <div className={styles.displayGrid}>
                {graphs.map((graph, index) => (
                    <Graph2D
                        key={index}
                        {...graph}
                    />
                ))}
            </div>
            <div className={styles.playbarContainer}></div>
        </div>
    );
};