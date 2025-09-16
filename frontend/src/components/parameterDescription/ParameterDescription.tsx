import styles from './ParameterDescription.module.scss';
import cx from 'classnames';

interface ParameterDescriptionProps {
    name: string
    description?: string
    imgSrc?: string
    className?: string
}

export const ParameterDescription = ({ name, description, imgSrc, className }: ParameterDescriptionProps) => {
    return (
        <div className={cx(styles.parameterDescription, className)}>
            <div className={styles.textContainer}>
                <h2 className={styles.name}>{name}</h2>
                {description && <p className={styles.description}>{description}</p>}
            </div>
            <div className={styles.imageContainer}>
                {imgSrc && (<img className={styles.image} src={imgSrc} alt={`${name} illustration`} />)}
            </div>
        </div>
    );
}