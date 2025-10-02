import { runSimulation } from '@utils/api';
import { useNavigate } from 'react-router-dom';
import styles from './Playback.module.scss';
import { Button } from '@components/button/Button';
import { Graph2D } from '@components/graph2D/graph2D';
import Home from '@assets/icons/home.svg?react';
import Edit from '@assets/icons/edit.svg?react';
import { useEffect, useState } from 'react';
import type { Graph2DProps } from '@components/graph2D/types';
import { buildGraphs } from '@utils/graph';


export const Playback = () => {
    const navigate = useNavigate();

    const [graphs, setGraphs] = useState<Graph2DProps[]>([]);

    useEffect(() => {
        runSimulation().then((res) => {
        setGraphs(buildGraphs(res));
        });
    }, []);

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
    )
}