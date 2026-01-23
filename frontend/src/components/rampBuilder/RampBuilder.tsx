import { useState, useCallback } from 'react';
import { Button } from '@components/button/Button';
import { InputField } from '@components/inputField/InputField';
import type { components } from '@types';
import { SEGMENT_DEFAULTS } from '@types';
import styles from './RampBuilder.module.scss';
import Plus from '@assets/icons/plus.svg?react';
import Trash from '@assets/icons/trash_can.svg?react';

type RampSegment = components['schemas']['PiecewiseRampConfigModel']['segments'][number];
type PiecewiseRampConfig = components['schemas']['PiecewiseRampConfigModel'];
type SegmentType = RampSegment['type'];

interface RampBuilderProps {
    value: PiecewiseRampConfig | null;
    onChange: (config: PiecewiseRampConfig) => void;
    className?: string;
}

const createDefaultSegment = (type: SegmentType): RampSegment => {
    return SEGMENT_DEFAULTS[type] as RampSegment;
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

    const updateSegment = useCallback((index: number, key: string, value: number) => {
        const newSegments = segments.map((seg, i) => {
            if (i === index) {
                return { ...seg, [key]: value } as RampSegment;
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
                    const fields = Object.entries(segment).filter(([key]) => key !== 'type');
                    
                    return (
                        <div key={index} className={styles.segment}>
                            <div className={styles.segmentHeader}>
                                <span className={styles.segmentNumber}>Segment {index + 1}</span>
                                {segments.length > 1 && (
                                    <Button
                                        type="button"
                                        onClick={() => removeSegment(index)}
                                        icon={Trash}
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
                                        {Object.keys(SEGMENT_DEFAULTS).map((type) => (
                                            <option key={type} value={type}>
                                                {type.split('_').map(w => w.charAt(0).toUpperCase() + w.slice(1)).join(' ')}
                                            </option>
                                        ))}
                                    </select>
                                </div>
                                
                                <div className={styles.segmentFields}>
                                    {fields.map(([key, value]) => (
                                        <InputField
                                            key={key}
                                            label={key}
                                            type="number"
                                            value={typeof value === 'number' ? value : undefined}
                                            onChange={(e) => updateSegment(index, key, parseFloat(e.target.value))}
                                        />
                                    ))}
                                </div>
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