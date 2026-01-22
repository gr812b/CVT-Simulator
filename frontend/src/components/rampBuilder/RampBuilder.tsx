import { useState, useCallback } from 'react';
import { Button } from '@components/button/Button';
import { InputField } from '@components/inputField/InputField';
import type { components, SegmentType } from '@types';
import styles from './RampBuilder.module.scss';
import Plus from '@assets/icons/plus.svg?react';
import Trash from '@assets/icons/trash_can.svg?react';
import { SEGMENT_LABELS, SEGMENT_FIELD_CONFIGS, FIELD_KEY_MAP } from '@types';

type RampSegment = components['schemas']['PiecewiseRampConfigModel']['segments'][number];
type PiecewiseRampConfig = components['schemas']['PiecewiseRampConfigModel'];

interface RampBuilderProps {
    value: PiecewiseRampConfig | null;
    onChange: (config: PiecewiseRampConfig) => void;
    className?: string;
}

const createDefaultSegment = (type: SegmentType): RampSegment => {
    const fields = SEGMENT_FIELD_CONFIGS[type];
    const segment: Record<string, string | number> = { type };
    
    fields.forEach(field => {
        const key = FIELD_KEY_MAP[field.label];
        if (key) {
            segment[key] = field.defaultValue;
        }
    });
    
    return segment as RampSegment;
};

const getSegmentFieldValue = (segment: RampSegment, label: string): number | undefined => {
    const key = FIELD_KEY_MAP[label];
    if (!key) return undefined;
    
    const segmentRecord = segment as Record<string, number | string>;
    const value = segmentRecord[key];
    return typeof value === 'number' ? value : undefined;
};

const updateSegmentField = (segment: RampSegment, label: string, value: number): RampSegment => {
    const key = FIELD_KEY_MAP[label];
    if (!key) return segment;
    
    return { ...segment, [key]: value } as RampSegment;
};

const preserveCommonFields = (oldSegment: RampSegment, newSegment: RampSegment): RampSegment => {
    const oldRecord = oldSegment as Record<string, number | string>;
    const newRecord = newSegment as Record<string, number | string>;
    const result = { ...newSegment };
    
    // Preserve 'length' if it exists in both
    if ('length' in oldRecord && 'length' in newRecord && typeof oldRecord.length === 'number') {
        (result as Record<string, number | string>).length = oldRecord.length;
    }
    
    return result as RampSegment;
};

export const RampBuilder = ({ value, onChange, className }: RampBuilderProps) => {
    const [segments, setSegments] = useState<RampSegment[]>(() => {
        const initialSegments = value?.segments || [createDefaultSegment('linear')];
        if (!value?.segments || value.segments.length === 0) {
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
        if (segments.length <= 1) return;
        const newSegments = segments.filter((_, i) => i !== index);
        setSegments(newSegments);
        onChange({ segments: newSegments });
    }, [segments, onChange]);

    const updateSegment = useCallback((index: number, label: string, value: number) => {
        const newSegments = segments.map((seg, i) => {
            if (i === index) {
                return updateSegmentField(seg, label, value);
            }
            return seg;
        });
        setSegments(newSegments);
        onChange({ segments: newSegments });
    }, [segments, onChange]);

    const changeSegmentType = useCallback((index: number, newType: SegmentType) => {
        const oldSegment = segments[index];
        const newSegment = createDefaultSegment(newType);
        const preservedSegment = preserveCommonFields(oldSegment, newSegment);
        const newSegments = segments.map((seg, i) => i === index ? preservedSegment : seg);
        setSegments(newSegments);
        onChange({ segments: newSegments });
    }, [segments, onChange]);

    return (
        <div className={className}>
            <div className={styles.segmentList}>
                {segments.map((segment, index) => {
                    const fields = SEGMENT_FIELD_CONFIGS[segment.type];
                    
                    return (
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
                                        {Object.entries(SEGMENT_LABELS).map(([value, label]) => (
                                            <option key={value} value={value}>
                                                {label}
                                            </option>
                                        ))}
                                    </select>
                                </div>

                                {fields.map((field) => (
                                    <InputField
                                        key={field.label}
                                        label={`${field.label} (${field.units})`}
                                        type="number"
                                        value={getSegmentFieldValue(segment, field.label)}
                                        onChange={(e) => updateSegment(index, field.label, parseFloat(e.target.value))}
                                    />
                                ))}
                            </div>
                        </div>
                    );
                })}
            </div>

            <div className={styles.addSegmentButton}>
                <Button onClick={addSegment} icon={Plus} text={'Add Segment'}/>
            </div>
        </div>
    );
};