import { runSimulation } from '@utils/api';
import { useNavigate } from 'react-router-dom';
import styles from './Playback.module.scss';
import { Button } from '@components/button/Button';
import { Graph2D } from '@components/graph2D/graph2D';
import Home from '@assets/icons/home.svg?react';
import Edit from '@assets/icons/edit.svg?react';
import type { AxisConfig } from '@components/graph2D/types';

const graphConfigs = [
    {
        title: "Velocity vs Time",
        xAxis: { name: "Time", type: "value", unit: "s" },
        yAxis: { name: "Velocity", type: "value", unit: "m/s" },
        height: 400,
        data: [],
    },
    {
        title: "Acceleration vs Time",
        xAxis: { name: "Time", type: "value", unit: "s" },
        yAxis: { name: "Acceleration", type: "value", unit: "m/s²" },
        height: 400,
        data: [],
    },
    {
        title: "Force vs Time",
        xAxis: { name: "Time", type: "value", unit: "s" },
        yAxis: { name: "Force", type: "value", unit: "N" },
        height: 400,
        data: [],
    },
    {
        title: "Power vs Time",
        xAxis: { name: "Time", type: "value", unit: "s" },
        yAxis: { name: "Power", type: "value", unit: "W" },
        height: 400,
        data: [],
    },
    {
        title: "Torque vs Time",
        xAxis: { name: "Time", type: "value", unit: "s" },
        yAxis: { name: "Torque", type: "value", unit: "N·m" },
        height: 400,
        data: [],
    },
    {
        title: "Displacement vs Time",
        xAxis: { name: "Time", type: "value", unit: "s" },
        yAxis: { name: "Displacement", type: "value", unit: "m" },
        height: 400,
        data: [],
    },
];

export const Playback = () => {
    const navigate = useNavigate();

    runSimulation().then((data) => {
        console.log(data);
    });

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
                {graphConfigs.map((config, index) => (
                    <Graph2D
                        key={index}
                        data={config.data}
                        config={{
                            title: config.title,
                            xAxis: config.xAxis as AxisConfig,
                            yAxis: config.yAxis as AxisConfig,
                            height: config.height,
                        }}
                    />
                ))}
            </div>
            <div className={styles.playbarContainer}></div>
        </div>
    )
}