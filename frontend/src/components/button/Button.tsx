import styles from './Button.module.scss'
import cx from 'classnames';
import type { ButtonHTMLAttributes } from 'react';

export const Button = ({ className, ...props } : ButtonHTMLAttributes<HTMLButtonElement>) => {
    return (
        <button {...props} className={cx(className, styles.button)} />
    )
}