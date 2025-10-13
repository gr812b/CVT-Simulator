import { useEffect, useState, useRef } from 'react';
import styles from './SpeedSelector.module.scss';

interface SpeedSelectorProps {
    speed: number;
    onSpeedChange: (speed: number) => void;
    speedOptions?: number[];
}

export const SpeedSelector = ({ 
    speed, 
    onSpeedChange, 
    speedOptions = [0.25, 0.5, 0.75, 1, 1.25, 1.5, 2, 2.5, 3, 4] 
}: SpeedSelectorProps) => {
    const [isDropdownOpen, setIsDropdownOpen] = useState(false);
    const dropdownRef = useRef<HTMLDivElement>(null);

    // Close dropdown when clicking outside
    useEffect(() => {
        const handleClickOutside = (event: MouseEvent) => {
            if (dropdownRef.current && !dropdownRef.current.contains(event.target as Node)) {
                setIsDropdownOpen(false);
            }
        };

        if (isDropdownOpen) {
            document.addEventListener('mousedown', handleClickOutside);
        }

        return () => {
            document.removeEventListener('mousedown', handleClickOutside);
        };
    }, [isDropdownOpen]);

    const handleSpeedSelect = (newSpeed: number) => {
        onSpeedChange(newSpeed);
        setIsDropdownOpen(false);
    };

    const toggleDropdown = () => {
        setIsDropdownOpen(!isDropdownOpen);
    };

    return (
        <div className={styles.speedContainer}>

            <div className={styles.customDropdown} ref={dropdownRef}>
                <button
                    className={styles.speedButton}
                    onClick={toggleDropdown}
                    aria-label="Change playback speed"
                    aria-expanded={isDropdownOpen}
                >
                    {speed}x
                </button>
                {isDropdownOpen && (
                    <div className={styles.dropdownMenu}>
                        {speedOptions.map(option => (
                            <button
                                key={option}
                                className={`${styles.dropdownOption} ${speed === option ? styles.selected : ''}`}
                                onClick={() => handleSpeedSelect(option)}
                            >
                                {option}x
                            </button>
                        ))}
                    </div>
                )}
            </div>
        </div>
    );
};