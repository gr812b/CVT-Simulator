import styles from './ParameterAccordion.module.scss';
import cx from 'classnames';
import { ActionIcon } from '@mantine/core';
import ChevronDown from '@assets/icons/chevron_down.svg?react';

interface ParameterAccordionProps {
  title: string;
  className?: string;
  children: React.ReactNode;
  isExpanded: boolean;
  onToggle: () => void;
}

export const ParameterAccordion = ({
  title,
  className,
  children,
  isExpanded,
  onToggle,
}: ParameterAccordionProps) => {
  return (
    <div className={cx(styles.accordion, { [styles.hideChildren]: !isExpanded }, className)}>
      <div onClick={onToggle} className={cx(styles.header)}>
        <h2 className={styles.title}>{title}</h2>
        <ActionIcon
          className={styles.iconWrapper}
          variant="subtle"
          aria-label={`${isExpanded ? 'Collapse' : 'Expand'} ${title}`}
          aria-expanded={isExpanded}
        >
          <ChevronDown className={cx(styles.icon, { [styles.rotateRight]: !isExpanded })} />
        </ActionIcon>
      </div>
      <div className={cx(styles.children)}>
        <div className={styles.childrenContent}>{children}</div>
      </div>
    </div>
  );
};
