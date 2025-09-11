import styles from './ParameterAccordion.module.scss';
import cx from 'classnames';
import ChevronDown from '@assets/icons/chevron_down.svg?react';

interface ParameterAccordionProps {
    title: string
    className?: string
    children: React.ReactNode
    isExpanded: boolean
    onToggle: () => void
}

export const ParameterAccordion = ({ title, className, children, isExpanded, onToggle }: ParameterAccordionProps) => {

    return (
        <div
            className={cx(
                styles.accordion,
                { [styles.hideChildren]: !isExpanded },
                className
            )}
        >
            <div
                onClick={onToggle}
                className={cx(styles.header)}
            >
                <h2 className={styles.title}>{title}</h2>
                <button className={styles.iconWrapper}>
                    <ChevronDown className={cx(styles.icon, { [styles.rotateRight] : !isExpanded })} />
                </button>
            </div>
            <div className={cx(styles.children)}>{children}</div>
        </div>
    );
}