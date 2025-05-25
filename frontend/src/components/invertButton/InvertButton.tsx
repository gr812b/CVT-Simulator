import styles from './InvertButton.module.scss'
import cx from 'classnames'

interface InvertButtonProps {
    onClick: () => void
    className?: string
    children?: React.ReactNode
}

export const InvertButton = ({ onClick, className, children }: InvertButtonProps) => {

    return (
        <button onClick={onClick} className={cx(styles.invertButton, className)} >
            {children}
        </button>
    )
}