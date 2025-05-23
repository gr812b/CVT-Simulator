import styles from './Button.module.css';
import cx from 'classnames';

interface ButtonProps {
    onClick: () => void
    children?: React.ReactNode
    className?: string
}

export const Button = ({ onClick, children, className }: ButtonProps) => {
    return (
        <button
            className={cx(styles.button, className)}
            onClick={onClick}
        >
            {children}
        </button>
    );
};

