import { useNavigate, useLocation } from 'react-router-dom';
import type { RunResponse } from '@utils/api';
import styles from './Playback.module.scss';
import { Button } from '@components/button/Button';
import { Graph2D } from '@components/graph2D/graph2D';
import { Playbar } from '@components/playbar/Playbar';
import Home from '@assets/icons/home.svg?react';
import Edit from '@assets/icons/edit.svg?react';
import { useMemo, useState, useEffect } from 'react';
import { buildGraphs } from '@utils/graph';
import { ReplayController, ReplayEventType } from '@utils/ReplayController';
import { timeAccessor } from '@types';


// Type the location state
interface PlaybackLocationState {
  simulationResult: RunResponse;
}

export const Playback = () => {
    const navigate = useNavigate();
    const location = useLocation();
    const simulationResult = (location.state as PlaybackLocationState | null)?.simulationResult;

    const [activeIndex, setActiveIndex] = useState<number>(0);

    const replayController = useMemo(() => {
        return simulationResult ? new ReplayController(simulationResult.data) : null;
    }, [simulationResult]);

    const times = useMemo(() => {
        return simulationResult ? simulationResult.data.map(timeAccessor) : [];
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

    // Build graphs from simulation result using graph configs
    const graphs = useMemo(() => {
        return simulationResult ? buildGraphs(simulationResult) : [];
    }, [simulationResult]);

    // Redirect to input page if no simulation data is available
    if (!simulationResult) {
        console.warn('No simulation data available. Redirecting to input page.');
        navigate('/input');
        return null;
    }

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
                        activeIndex={activeIndex}
                    />
                ))}
            </div>
            <div className={styles.playbarContainer}>
                {replayController && (
                    <Playbar 
                        replayController={replayController}
                        times={times}
                    />
                )}
            </div>
        </div>
    );
};