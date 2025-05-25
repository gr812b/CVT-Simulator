import type {FC, SVGProps} from 'react';
import styles from './IconButton.module.scss'
import cx from 'classnames';

interface IconButtonProps {
    onClick: () => void
    icon: FC<SVGProps<SVGSVGElement>>
    iconSide?: 'left' | 'right'
    text: string
}

export const IconButton = ({ onClick, icon: Icon, iconSide = 'left', text }: IconButtonProps) => {

    const renderIcon = () => <Icon className={styles.icon} />

    return (
        <button onClick={onClick} className={cx(styles.iconButton)} >
            {iconSide === 'left' && renderIcon()}
            <span className={styles.text}>{text}</span>
            {iconSide === 'right' && renderIcon()}
        </button>
    )
}