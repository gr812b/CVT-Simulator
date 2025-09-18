import styles from './Button.module.scss'
import cx from 'classnames';
import type {ButtonHTMLAttributes, ComponentType, SVGAttributes} from 'react';

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
    text?: string
    icon: ComponentType<SVGAttributes<SVGSVGElement>>
    iconSide?: 'left' | 'right'
    className?: string
}

export const Button = ({ text, icon: Icon, iconSide = 'left', className, ...props }: ButtonProps) => {
    const renderIcon = () => <Icon className={styles.icon} />
    return (
        <button
            className={cx(styles.button, { [styles.noText]: !text }, className)}
            {...props}
        >
            {iconSide === 'left' && renderIcon()}
            {text && <span className={styles.text}>{text}</span>}
            {iconSide === 'right' && renderIcon()}
        </button>
    )
}