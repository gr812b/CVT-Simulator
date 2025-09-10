import styles from './Input.module.scss';

export const Input = () => {
    return (
        <div className={styles.input}>
            <span className={styles.backButton}>Back</span>
            <div className={styles.inputGrid}>
                <div className={styles.parameterInputContainer}></div>
                <div className={styles.parameterInformationContainer}></div>
                <div className={styles.inputButtonsContainer}></div>
                <div className={styles.nextButtonContainer}></div>
            </div>
        </div>
    )
}