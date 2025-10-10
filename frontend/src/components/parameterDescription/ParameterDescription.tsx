import styles from './ParameterDescription.module.scss';
import cx from 'classnames';

interface ParameterDescriptionProps {
    name: string
    description?: string
    img?: string
    className?: string
}

export const ParameterDescription = ({ name, description, img, className }: ParameterDescriptionProps) => {
    return (
        <div className={cx(styles.parameterDescription, className)}>
            <div className={styles.textContainer}>
                <h2 className={styles.name}>{name}</h2>
                {description && <p className={styles.description}>{description}</p>}
            </div>
            <div className={styles.imageContainer}>
                {img && (<img className={styles.image} src={img} alt={`${name} illustration`} />)}
            </div>
        </div>
    );
}