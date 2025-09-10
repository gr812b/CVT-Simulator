import styles from './MainButton.module.scss'
import cx from 'classnames';
import type {ComponentType, SVGAttributes} from 'react';

interface MainButtonProps {
    onClick: () => void
    text?: string
    icon: ComponentType<SVGAttributes<SVGSVGElement>>
    iconSide?: 'left' | 'right'
}

export const MainButton = ({ onClick, text, icon: Icon, iconSide = 'left'}: MainButtonProps) => {
    const renderIcon = () => <Icon className={styles.icon} />
    return (
        <button
            onClick={onClick}
            className={cx(styles.mainButton, { [styles.noText]: !text })}
        >
            {iconSide === 'left' && renderIcon()}
            {text && <span className={styles.text}>{text}</span>}
            {iconSide === 'right' && renderIcon()}
        </button>
    )
}