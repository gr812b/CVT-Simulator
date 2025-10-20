import React, { useCallback } from 'react';
import * as Slider from '@radix-ui/react-slider';
import styles from './Slider.module.scss';
import cx from 'classnames';

interface SliderProps {
    values: (string | number)[];
    selectedIndex: number;
    onIndexChange: (index: number, value: string | number) => void;
    className?: string;
    disabled?: boolean;
    showLabels?: boolean;
    showTicks?: boolean;
}

export const DiscreteSlider = ({
    values,
    selectedIndex,
    onIndexChange,
    className,
    disabled = false,
    showLabels = false,
    showTicks = false,
}: SliderProps) => {
    // Clamp selectedIndex to valid range
    const currentIndex = Math.max(0, Math.min(selectedIndex, values.length - 1));

    const handleValueChange = useCallback((newValues: number[]) => {
        const newIndex = newValues[0];
        
        if (values[newIndex] !== undefined) {
            onIndexChange(newIndex, values[newIndex]);
        }
    }, [values, onIndexChange]);

    const handleTrackClick = useCallback((event: React.MouseEvent<HTMLDivElement>) => {
        if (disabled) return;
        
        const rect = event.currentTarget.getBoundingClientRect();
        const clickX = event.clientX - rect.left;
        const trackWidth = rect.width;
        const percentage = clickX / trackWidth;
        
        // Calculate which discrete value is closest
        const targetIndex = Math.round(percentage * (values.length - 1));
        const clampedIndex = Math.max(0, Math.min(values.length - 1, targetIndex));
        
        if (values[clampedIndex] !== undefined) {
            onIndexChange(clampedIndex, values[clampedIndex]);
        }
    }, [disabled, values, onIndexChange]);

    if (!values || values.length === 0) {
        return null;
    }

    return (
        <div className={cx(styles.sliderContainer, className)}>
            <div className={styles.sliderWrapper}>
                <Slider.Root
                    className={styles.sliderRoot}
                    value={[currentIndex]}
                    onValueChange={handleValueChange}
                    max={values.length - 1}
                    min={0}
                    step={1}
                    disabled={disabled}
                >
                    <Slider.Track 
                        className={styles.sliderTrack}
                        onClick={handleTrackClick}
                    >
                        <Slider.Range className={styles.sliderRange} />
                        
                        {/* Render tick marks */}
                        {showTicks && values.map((_, index) => (
                            <div
                                key={index}
                                className={cx(styles.tick, {
                                    [styles.activeTick]: index <= currentIndex
                                })}
                                style={{
                                    left: `${(index / (values.length - 1)) * 100}%`
                                }}
                            />
                        ))}
                    </Slider.Track>
                    
                    <Slider.Thumb className={styles.sliderThumb} />
                </Slider.Root>
                
                {/* Value labels */}
                {showLabels && (
                    <div className={styles.labels}>
                        {values.map((value, index) => (
                            <div
                                key={index}
                                className={cx(styles.labelItem, {
                                    [styles.activeLabel]: index === currentIndex
                                })}
                                style={{
                                    left: `${(index / (values.length - 1)) * 100}%`
                                }}
                                onClick={() => {
                                    if (!disabled) {
                                        onIndexChange(index, value);
                                    }
                                }}
                            >
                                {value}
                            </div>
                        ))}
                    </div>
                )}
            </div>
            

        </div>
    );
};

export default DiscreteSlider;
