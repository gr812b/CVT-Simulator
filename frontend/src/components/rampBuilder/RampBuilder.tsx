import { useState, useEffect, useCallback } from 'react';
import { Button } from '@components/button/Button';
import { InputField } from '@components/inputField/InputField';
import type { components } from '@types/api';
import styles from './RampBuilder.module.scss';
import Plus from '@assets/icons/plus.svg?react';
import Trash from '@assets/icons/trash_can.svg?react';

type RampSegment = components['schemas']['PiecewiseRampConfigModel']['segments'][number];
type LinearSegment = components['schemas']['LinearSegmentConfigModel'];
type CircularSegment = components['schemas']['CircularSegmentConfigModel'];
type CubicSpiralZeroK1Segment = components['schemas']['CubicSpiralZeroK1ConfigModel'];
type PiecewiseRampConfig = components['schemas']['PiecewiseRampConfigModel'];

type SegmentType = 'linear' | 'circular' | 'cubic_spiral_zero_k1' | 'cubic_spiral_zero_zero' | 'euler_spiral' | 'pro_defined';

interface RampBuilderProps {
    value: PiecewiseRampConfig | null;
    onChange: (config: PiecewiseRampConfig) => void;
    className?: string;
}

const SEGMENT_TYPE_LABELS: Record<SegmentType, string> = {
    linear: 'Linear',
    circular: 'Circular Arc',
    cubic_spiral_zero_k1: 'Cubic Spiral (Zero-K1)',
    cubic_spiral_zero_zero: 'Cubic Spiral (Zero-Zero)',
    euler_spiral: 'Euler Spiral',
    pro_defined: 'Pro Defined',
};

const createDefaultSegment = (type: SegmentType, xStart: number): RampSegment => {
    const xEnd = xStart + 0.01;
    
    switch (type) {
        case 'linear':
            return {
                type: 'linear',
                x_start: xStart,
                x_end: xEnd,
                slope: 0.5,
            } as LinearSegment;
        case 'circular':
            return {
                type: 'circular',
                x_start: xStart,
                x_end: xEnd,
                radius: 0.05,
                theta_start: 0,
                theta_end: 0.785, // π/4
            } as CircularSegment;
        case 'cubic_spiral_zero_k1':
            return {
                type: 'cubic_spiral_zero_k1',
                x_start: xStart,
                x_end: xEnd,
                slope_start: 0.3,
                slope_end: 0.4,
                target_curvature: 10.0,
            } as CubicSpiralZeroK1Segment;
        default:
            return {
                type: 'linear',
                x_start: xStart,
                x_end: xEnd,
                slope: 0.5,
            } as LinearSegment;
    }
};

export const RampBuilder = ({ value, onChange, className }: RampBuilderProps) => {
    const [segments, setSegments] = useState<RampSegment[]>(
        value?.segments || [createDefaultSegment('linear', 0)]
    );

    useEffect(() => {
        onChange({ segments });
    }, [segments, onChange]);

    const addSegment = useCallback(() => {
        const lastSegment = segments[segments.length - 1];
        const newXStart = lastSegment ? lastSegment.x_end : 0;
        const newSegment = createDefaultSegment('linear', newXStart);
        setSegments([...segments, newSegment]);
    }, [segments]);

    const removeSegment = useCallback((index: number) => {
        if (segments.length <= 1) return; // Keep at least one segment
        setSegments(segments.filter((_, i) => i !== index));
    }, [segments]);

    const updateSegment = useCallback((index: number, updates: Partial<RampSegment>) => {
        setSegments(segments.map((seg, i) => {
            if (i === index) {
                return { ...seg, ...updates };
            }
            return seg;
        }));
    }, [segments]);

    const changeSegmentType = useCallback((index: number, newType: SegmentType) => {
        const oldSegment = segments[index];
        const newSegment = createDefaultSegment(newType, oldSegment.x_start);
        newSegment.x_end = oldSegment.x_end;
        setSegments(segments.map((seg, i) => i === index ? newSegment : seg));
    }, [segments]);

    return (
        <div className={className}>
            <div className={styles.header}>
                <h3>Custom Ramp Configuration</h3>
                <Button onClick={addSegment} icon={Plus} text="Add Segment" />
            </div>

            <div className={styles.segmentList}>
                {segments.map((segment, index) => (
                    <div key={index} className={styles.segment}>
                        <div className={styles.segmentHeader}>
                            <span className={styles.segmentNumber}>Segment {index + 1}</span>
                            {segments.length > 1 && (
                                <Button
                                    type="button"
                                    onClick={() => removeSegment(index)}
                                    icon={Trash}
                                    className={styles.removeButton}
                                    title="Remove segment"
                                />
                            )}
                        </div>

                        <div className={styles.segmentContent}>
                            <div className={styles.field}>
                                <label>Type</label>
                                <select
                                    value={segment.type}
                                    onChange={(e) => changeSegmentType(index, e.target.value as SegmentType)}
                                    className={styles.select}
                                >
                                    {Object.entries(SEGMENT_TYPE_LABELS).map(([value, label]) => (
                                        <option key={value} value={value}>
                                            {label}
                                        </option>
                                    ))}
                                </select>
                            </div>

                            <div className={styles.row}>
                                <InputField
                                    label="X Start (m)"
                                    type="number"
                                    step="0.001"
                                    value={segment.x_start}
                                    onChange={(e) => updateSegment(index, { x_start: parseFloat(e.target.value) })}
                                />
                                <InputField
                                    label="X End (m)"
                                    type="number"
                                    step="0.001"
                                    value={segment.x_end}
                                    onChange={(e) => updateSegment(index, { x_end: parseFloat(e.target.value) })}
                                />
                            </div>

                            {segment.type === 'linear' && (
                                <InputField
                                    label="Slope"
                                    type="number"
                                    step="0.1"
                                    value={(segment as LinearSegment).slope}
                                    onChange={(e) => updateSegment(index, { slope: parseFloat(e.target.value) })}
                                />
                            )}

                            {segment.type === 'circular' && (
                                <>
                                    <InputField
                                        label="Radius (m)"
                                        type="number"
                                        step="0.001"
                                        value={(segment as CircularSegment).radius}
                                        onChange={(e) => updateSegment(index, { radius: parseFloat(e.target.value) })}
                                    />
                                    <div className={styles.row}>
                                        <InputField
                                            label="Theta Start (rad)"
                                            type="number"
                                            step="0.1"
                                            value={(segment as CircularSegment).theta_start}
                                            onChange={(e) => updateSegment(index, { theta_start: parseFloat(e.target.value) })}
                                        />
                                        <InputField
                                            label="Theta End (rad)"
                                            type="number"
                                            step="0.1"
                                            value={(segment as CircularSegment).theta_end}
                                            onChange={(e) => updateSegment(index, { theta_end: parseFloat(e.target.value) })}
                                        />
                                    </div>
                                </>
                            )}

                            {segment.type === 'cubic_spiral_zero_k1' && (
                                <>
                                    <div className={styles.row}>
                                        <InputField
                                            label="Slope Start (rad)"
                                            type="number"
                                            step="0.1"
                                            value={(segment as CubicSpiralZeroK1Segment).slope_start}
                                            onChange={(e) => updateSegment(index, { slope_start: parseFloat(e.target.value) })}
                                        />
                                        <InputField
                                            label="Slope End (rad)"
                                            type="number"
                                            step="0.1"
                                            value={(segment as CubicSpiralZeroK1Segment).slope_end}
                                            onChange={(e) => updateSegment(index, { slope_end: parseFloat(e.target.value) })}
                                        />
                                    </div>
                                    <InputField
                                        label="Target Curvature"
                                        type="number"
                                        step="0.1"
                                        value={(segment as CubicSpiralZeroK1Segment).target_curvature}
                                        onChange={(e) => updateSegment(index, { target_curvature: parseFloat(e.target.value) })}
                                    />
                                </>
                            )}
                        </div>
                    </div>
                ))}
            </div>

            <div className={styles.summary}>
                <div className={styles.summaryItem}>
                    <span>Total segments:</span>
                    <strong>{segments.length}</strong>
                </div>
                <div className={styles.summaryItem}>
                    <span>Range:</span>
                    <strong>
                        {segments[0]?.x_start.toFixed(3)} - {segments[segments.length - 1]?.x_end.toFixed(3)} m
                    </strong>
                </div>
            </div>
        </div>
    );
};
