import { useState } from 'react';
import styles from './ParameterAccordion.module.scss';
import cx from 'classnames';
import ChevronDown from '@assets/icons/chevron_down.svg?react';

interface ParameterAccordionProps {
    title: string
    className?: string
    children: React.ReactNode
}

export const ParameterAccordion = ({ title, className, children }: ParameterAccordionProps) => {
    // Controls if the section is expanded or collapsed
    const [isExpanded, setIsExpanded] = useState(false);

    const toggleExpanded = () => setIsExpanded(!isExpanded);

    return (
        <div
            className={cx(
                styles.accordion,
                { [styles.hideChildren]: !isExpanded },
                className
            )}
        >
            <div
                onClick={toggleExpanded}
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