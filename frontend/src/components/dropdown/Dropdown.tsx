import React, { useState, useRef, useEffect } from 'react';
import styles from './Dropdown.module.scss';
import cx from 'classnames';
import ChevronDown from '@assets/icons/chevron_down.svg?react';

interface Option<T extends string> {
    value: T;
    label: string;
}

interface DropdownProps<T extends string> {
    value: T;
    options: Option<T>[];
    onChange: (value: T) => void;
    label?: string;
    className?: string;
}

export const Dropdown = <T extends string>({
    value,
    options,
    onChange,
    label,
    className,
}: DropdownProps<T>) => {
    const [open, setOpen] = useState(false);
    const ref = useRef<HTMLDivElement>(null);

    useEffect(() => {
        const onClickOutside = (e: MouseEvent) => {
            if (ref.current && !ref.current.contains(e.target as Node)) {
                setOpen(false);
            }
        };

        const onKeyDown = (e: KeyboardEvent) => {
            if (e.key === 'Escape' || e.key === 'Esc') {
                setOpen(false);
            }
        };

        document.addEventListener('keydown', onKeyDown);
        document.addEventListener('mousedown', onClickOutside);

        return () => {
            document.removeEventListener('keydown', onKeyDown);
            document.removeEventListener('mousedown', onClickOutside);
        }
    }, []);

    const selected = options.find(o => o.value === value);
    const triggerId = `dropdown-trigger-${value}`;

    return (
        <div ref={ref} className={cx(styles.dropdown, className)}>
            {label && <label htmlFor={triggerId} className={styles.label}>{label}</label>}

            <button
                id={triggerId}
                type="button"
                className={styles.trigger}
                onClick={() => setOpen(o => !o)}
                aria-label={label || 'Dropdown menu'}
                aria-expanded={open}
            >
                <span>{selected?.label}</span>
                <ChevronDown className={styles.icon} />
            </button>

            {open && (
                <ul className={styles.menu} role="listbox">
                    {options.map(option => (
                        <li key={option.value} className={styles.listItem} role="option">
                            <button
                                className={styles.option}
                                type="button"
                                onClick={() => {
                                    onChange(option.value);
                                    setOpen(false);
                                }}
                                aria-selected={option.value === value}
                            >
                                {option.label}
                            </button>
                        </li>
                    ))}
                </ul>
            )}
        </div>
    );
};
