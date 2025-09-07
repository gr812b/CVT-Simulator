import { useState } from 'react';
import styles from './ParameterAccordion.module.scss';
import cx from 'classnames';
import ChevronDown from '@assets/icons/chevron_down.svg?react';

interface ParameterAccordionProps {
    title: string
    className?: string
    children: React.ReactNode
}

const ParameterAccordion = ({ title, className, children }: ParameterAccordionProps) => {
    // Controls if the section is expanded or collapsed
    const [isOpen, setIsOpen] = useState(false);

    const toggleOpen = () => setIsOpen(!isOpen);

    return (
        <div
            className={cx(
                styles.section,
                { [styles.hideContent]: !isOpen },
                className
            )}
        >
            <div
                onClick={toggleOpen}
                className={cx(styles.header)}
            >
                <h2 className={styles.title}>{title}</h2>
                <button className={styles.iconWrapper}><ChevronDown className={cx(styles.icon, { [styles.rotateRight] : !isOpen })} /></button>
            </div>
            <div
                className={cx(
                    styles.children,
                    { [styles.hideChildren]: !isOpen }
                )}
            >
                {children}
            </div>
        </div>
    );
}

export default ParameterAccordion;