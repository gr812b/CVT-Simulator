import styles from './ParameterInformation.module.scss';
import cx from 'classnames';

interface ParameterInformationProps {
    name: string
    description: string
    imgSrc: string
    className?: string
}

const ParameterInformation = ({ name, description, imgSrc, className }: ParameterInformationProps) => {
    return (
        <div className={cx(styles.parameterInformation, className)}>
            <div className={styles.textContainer}>
                <h2 className={styles.name}>{name}</h2>
                <p className={styles.description}>{description}</p>
            </div>
            <div className={styles.imageContainer}>
                <img className={styles.image} src={imgSrc} alt={`${name} illustration`} />
            </div>
        </div>
    );
}

export default ParameterInformation;