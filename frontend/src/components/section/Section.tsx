import { useState } from 'react';
import styles from './Section.module.scss';
import cx from 'classnames';
import ChevronDown from '@assets/icons/chevron_down.svg?react';

interface SectionProps {
    title: string
    collapsible?: boolean
    className?: string
    children: React.ReactNode
}

const Section = ({ title, className, collapsible = true, children }: SectionProps) => {
    // Controls if the section is expanded or collapsed
    const [isOpen, setIsOpen] = useState(false);

    // Only change the state if the section is collapsible
    const toggleOpen = () => {
        if (collapsible) {
            setIsOpen(!isOpen);
        }
    }

    return (
        <div className={cx(styles.section, className)}>
            <button
                onClick={toggleOpen}
                className={cx(
                    styles.header,
                    { [styles.noDropdown]: !collapsible }
                )}
            >
                <h2 className={styles.title}>{title}</h2>
                {collapsible && <ChevronDown className={cx(styles.icon, { [styles.rotateRight] : !isOpen })} />}
            </button>
            <div
                className={cx(
                    styles.content,
                    { [styles.hideContent]: !isOpen }
                )}
            >
                {children}
            </div>
        </div>
    );
}

export default Section;