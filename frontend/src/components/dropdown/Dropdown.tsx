import { useState, useRef, useEffect } from 'react';
import styles from './Dropdown.module.scss';
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

    return (
        <div ref={ref} className={`${styles.dropdown} ${className ?? ''}`}>
            {label && <label className={styles.label}>{label}</label>}

            <button
                type="button"
                className={styles.trigger}
                onClick={() => setOpen(o => !o)}
            >
                <span>{selected?.label}</span>
                <ChevronDown className={styles.icon} />
            </button>

            {open && (
                <ul className={styles.menu}>
                    {options.map(option => (
                        <li
                            key={option.value}
                            className={styles.option}
                            onClick={() => {
                                onChange(option.value);
                                setOpen(false);
                            }}
                        >
                            {option.label}
                        </li>
                    ))}
                </ul>
            )}
        </div>
    );
};
