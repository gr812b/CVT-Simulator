import { MainButton } from '@components/mainButton/MainButton';
import styles from './Input.module.scss';
import ArrowLeft from '@assets/icons/arrow_left.svg?react';
import { useNavigate } from 'react-router-dom';

export const Input = () => {
    const navigate = useNavigate();
    
    return (
        <div className={styles.input}>
            <MainButton
            text={"Back"}
            icon={ArrowLeft}
            className={styles.backButton}
            onClick={() => navigate('/')}
            />
            <div className={styles.inputGrid}>
                <div className={styles.parameterInputContainer}></div>
                <div className={styles.parameterInformationContainer}></div>
                <div className={styles.inputButtonsContainer}></div>
                <div className={styles.nextButtonContainer}></div>
            </div>
        </div>
    )
}