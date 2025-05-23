import styles from './IconButton.module.scss'
import cx from 'classnames';
import { Button } from "../button/Button";

interface IconButtonProps {
    onClick: () => void
    icon: string
    alt?: string
    text: string
    className?: string
}

export const IconButton = ({ onClick, icon, alt, text, className }: IconButtonProps) => {
    return (
        <Button onClick={onClick} className={cx(styles.iconButton, className)}>
            <img src={icon} alt={alt} className={styles.icon} />
            <span className={styles.text}>{text}</span>
        </Button>
    )
}