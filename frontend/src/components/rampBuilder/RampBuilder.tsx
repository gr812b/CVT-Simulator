import { useEffect, useState } from 'react';
import { Button } from '@components/button/Button';
import { InputField } from '@components/inputField/InputField';
import { Dropdown } from '@components/dropdown/Dropdown';
import type { RampEditorSegment, RampEditorValue } from '@utils/rampEditor';
import styles from './RampBuilder.module.scss';
import Plus from '@assets/icons/plus.svg?react';
import Trash from '@assets/icons/trash_can.svg?react';

interface RampBuilderProps {
  value: RampEditorValue;
  onChange: (config: RampEditorValue) => void;
  className?: string;
  hasChanged?: boolean;
}

const defaultSegment = (type: RampEditorSegment['type']): RampEditorSegment => type === 'linear'
  ? { type: 'linear', length: 0.05, angle: 15 }
  : { type: 'circular', length: 0.05, angle_start: 45, angle_end: 15, quadrant: 2 };

export const RampBuilder = ({ value, onChange, className, hasChanged = false }: RampBuilderProps) => {
  const [segments, setSegments] = useState<RampEditorSegment[]>(value.segments.length ? value.segments : [defaultSegment('linear')]);
  useEffect(() => setSegments(value.segments.length ? value.segments : [defaultSegment('linear')]), [value]);
  const commit = (next: RampEditorSegment[]) => { setSegments(next); onChange({ segments: next }); };
  const update = (index: number, field: string, nextValue: number) => commit(segments.map((segment, segmentIndex) => segmentIndex === index ? { ...segment, [field]: nextValue } as RampEditorSegment : segment));
  const changeType = (index: number, type: RampEditorSegment['type']) => commit(segments.map((segment, segmentIndex) => segmentIndex === index ? { ...defaultSegment(type), length: segment.length } : segment));
  const fields = (segment: RampEditorSegment): Array<[string, number, string]> => segment.type === 'linear'
    ? [['length', segment.length, 'Length (m)'], ['angle', segment.angle, 'Angle (°)']]
    : [['length', segment.length, 'Length (m)'], ['angle_start', segment.angle_start, 'Start Angle (°)'], ['angle_end', segment.angle_end, 'End Angle (°)'], ['quadrant', segment.quadrant, 'Quadrant']];
  return <div className={[styles.rampBuilder, className].filter(Boolean).join(' ')}>
    <div className={styles.rampStatus}><span className={styles.rampLabel}>Ramp Profile</span>{hasChanged && <span className={styles.changedBadge}><span className={styles.changeIndicator} /><span>Changed</span></span>}</div>
    <div className={styles.segmentList}>{segments.map((segment, index) => <div key={index} className={styles.segment}>
      <div className={styles.segmentHeader}><span className={styles.segmentNumber}>Segment {index + 1}</span>{segments.length > 1 && <Button type="button" onClick={() => commit(segments.filter((_, candidate) => candidate !== index))} icon={Trash} title="Remove segment" />}</div>
      <div className={styles.segmentContent}><Dropdown label="Type" value={segment.type} onChange={(next) => changeType(index, next as RampEditorSegment['type'])} options={[{ value: 'linear', label: 'Linear' }, { value: 'circular', label: 'Circular' }]} />
        <div className={styles.segmentFields}>{fields(segment).map(([key, fieldValue, label]) => <InputField key={key} label={label} type="number" value={fieldValue} onChange={(event) => update(index, key, Number(event.target.value))} />)}</div>
      </div>
    </div>)}</div>
    <div className={styles.addSegmentButton}><Button onClick={() => commit([...segments, defaultSegment('linear')])} icon={Plus} text="Add Segment" /></div>
  </div>;
};
