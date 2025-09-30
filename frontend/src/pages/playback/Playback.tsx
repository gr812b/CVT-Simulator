import { runSimulation } from '@utils/api';
import { useNavigate } from 'react-router-dom';
import styles from './Playback.module.scss';
import { Button } from '@components/button/Button';
import Home from '@assets/icons/home.svg?react';
import Edit from '@assets/icons/edit.svg?react';

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
            <div className={styles.displayGrid}></div>
            <div className={styles.playbarContainer}></div>
        </div>
    )
}