import { useNavigate } from 'react-router-dom';
import { useEffect, useCallback, useRef } from 'react';
import styles from './Playback.module.scss';
import { Button } from '@components/button/Button';
import { Graph2D } from '@components/graph2D/graph2D';
import { Scene3DViewer } from '@components/scene3DViewer/Scene3DViewer';
import { Playbar } from '@components/playbar/Playbar';
import Home from '@assets/icons/home.svg?react';
import Edit from '@assets/icons/edit.svg?react';
import { usePlaybackData } from '@hooks/usePlaybackData';


export const Playback = () => {
    const navigate = useNavigate();
    const playbackData = usePlaybackData();
    const replayRef = useRef(playbackData?.replayController ?? null);

    // Handle redirect if no simulation data is available
    useEffect(() => {
        if (!playbackData) {
            // TODO: Replace with proper toast notification
            console.warn('No simulation data available. Redirecting to input page.');
            navigate('/input');
        }
    }, [playbackData, navigate]);

    useEffect(() => {
        replayRef.current = playbackData?.replayController ?? null;
    }, [playbackData?.replayController]);

    const onHomeClick = useCallback(() => {
        if (replayRef.current) {
            replayRef.current.pause();
        }
        navigate('/');
    }, [navigate]);

    const onEditClick = useCallback(() => {
        if (replayRef.current) {
            replayRef.current.pause();
        }
        navigate('/input');
    }, [navigate]);

    // If no data is available, show loading or return null while redirect happens
    if (!playbackData) {
        return null;
    }

    const { graphs, replayController, times } = playbackData;

    return (
        <div className={styles.playback}>
            <div className={styles.buttonsContainer}>
            <Button
                text={'Home'}
                icon={Home}
                className={styles.navigateButton}
                onClick={onHomeClick}
            />
            <Button
                text={'Edit'}
                icon={Edit}
                className={styles.navigateButton}
                onClick={onEditClick}
            />
            </div>

            <div className={styles.displayGrid}>
                <Scene3DViewer replayController={replayController} />
                {graphs.map((graph, index) => (
                    <Graph2D
                        key={index}
                        {...graph}
                        replayController={replayController}
                    />
                ))}
            </div>
            <div className={styles.playbarContainer}>
                <Playbar 
                    replayController={replayController}
                    times={times}
                />
            </div>
        </div>
    );
};