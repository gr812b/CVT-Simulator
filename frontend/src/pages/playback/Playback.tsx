import { useNavigate } from 'react-router-dom';
import { useEffect } from 'react';
import styles from './Playback.module.scss';
import { Button } from '@components/button/Button';
import { Graph2D } from '@components/graph2D/graph2D';
import { Playbar } from '@components/playbar/Playbar';
import Home from '@assets/icons/home.svg?react';
import Edit from '@assets/icons/edit.svg?react';
import { usePlaybackData } from '@hooks/usePlaybackData';

export const Playback = () => {
    const navigate = useNavigate();
    const playbackData = usePlaybackData();

    // Handle redirect if no simulation data is available
    useEffect(() => {
        if (!playbackData) {
            console.warn('No simulation data available. Redirecting to input page.');
            navigate('/input');
        }
    }, [playbackData, navigate]);

    // If no data is available, show loading or return null while redirect happens
    if (!playbackData) {
        return null;
    }

    const { graphs, replayController, times, activeIndex, setActiveIndex } = playbackData;

    return (
        <div className={styles.playback}>
            <div className={styles.buttonsContainer}>
            <Button
                text={'Home'}
                icon={Home}
                className={styles.navigateButton}
                onClick={() => {replayController.pause(); navigate('/')}}
            />
            <Button
                text={'Edit'}
                icon={Edit}
                className={styles.navigateButton}
                onClick={() => {replayController.pause(); navigate('/input')}}
            />
            </div>
            <div className={styles.displayGrid}>
                {graphs.map((graph, index) => (
                    <Graph2D
                        key={index}
                        {...graph}
                        activeIndex={activeIndex}
                        setActiveIndex={setActiveIndex}
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