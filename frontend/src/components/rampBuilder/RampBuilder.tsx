import { useState, useCallback } from 'react';
import { Button } from '@components/button/Button';
import { InputField } from '@components/inputField/InputField';
import type { components } from '@types';
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

const createDefaultSegment = (type: SegmentType): RampSegment => {
    const defaultLength = 0.1;
    
    switch (type) {
        case 'linear':
            return {
                type: 'linear',
                length: defaultLength,
                slope: 0.5,
            } as LinearSegment;
        case 'circular':
            return {
                type: 'circular',
                length: defaultLength,
                radius: 0.05,
                theta_start: 0,
                theta_end: 0.785, // π/4
            } as CircularSegment;
        case 'cubic_spiral_zero_k1':
            return {
                type: 'cubic_spiral_zero_k1',
                length: defaultLength,
                slope_start: 0.3,
                slope_end: 0.4,
                target_curvature: 10.0,
            } as CubicSpiralZeroK1Segment;
        default:
            return {
                type: 'linear',
                length: defaultLength,
                slope: 0.5,
            } as LinearSegment;
    }
};

export const RampBuilder = ({ value, onChange, className }: RampBuilderProps) => {
    const [segments, setSegments] = useState<RampSegment[]>(() => {
        const initialSegments = value?.segments || [createDefaultSegment('linear')];
        // If we had to create default segments, notify parent immediately
        if (!value?.segments || value.segments.length === 0) {
            // Use setTimeout to avoid updating parent during render
            setTimeout(() => onChange({ segments: initialSegments }), 0);
        }
        return initialSegments;
    });

    const addSegment = useCallback(() => {
        const newSegment = createDefaultSegment('linear');
        const newSegments = [...segments, newSegment];
        setSegments(newSegments);
        onChange({ segments: newSegments });
    }, [segments, onChange]);

    const removeSegment = useCallback((index: number) => {
        if (segments.length <= 1) return; // Keep at least one segment
        const newSegments = segments.filter((_, i) => i !== index);
        setSegments(newSegments);
        onChange({ segments: newSegments });
    }, [segments, onChange]);

    const updateSegment = useCallback((index: number, updates: Partial<RampSegment>) => {
        const newSegments = segments.map((seg, i) => {
            if (i === index) {
                return { ...seg, ...updates } as RampSegment;
            }
            return seg;
        });
        setSegments(newSegments);
        onChange({ segments: newSegments });
    }, [segments, onChange]);

    const changeSegmentType = useCallback((index: number, newType: SegmentType) => {
        const oldSegment = segments[index];
        const newSegment = createDefaultSegment(newType);
        newSegment.length = oldSegment.length;
        const newSegments = segments.map((seg, i) => i === index ? newSegment : seg);
        setSegments(newSegments);
        onChange({ segments: newSegments });
    }, [segments, onChange]);

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

                            <InputField
                                label="Length (m)"
                                type="number"
                                step="0.001"
                                value={segment.length}
                                onChange={(e) => updateSegment(index, { length: parseFloat(e.target.value) })}
                            />

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
                    <span>Total length:</span>
                    <strong>
                        {segments.reduce((sum, seg) => sum + (seg.length || 0), 0).toFixed(3)} m
                    </strong>
                </div>
            </div>
        </div>
    );
};
