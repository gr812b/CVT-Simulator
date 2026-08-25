import { useEffect, useState } from 'react';
import { Button } from '@components/button/Button';
import { InputField } from '@components/inputField/InputField';
import { Dropdown } from '@components/dropdown/Dropdown';
import type {
  RampEditorSegment,
  RampEditorValue,
  RampQuadrant,
} from '@utils/rampEditor';
import styles from './RampBuilder.module.scss';
import Plus from '@assets/icons/plus.svg?react';
import Trash from '@assets/icons/trash_can.svg?react';

interface RampBuilderProps {
  value: RampEditorValue;
  onChange: (config: RampEditorValue) => void;
  className?: string;
  hasChanged?: boolean;
}

type CircularRampEditorSegment = Extract<RampEditorSegment, { type: 'circular' }>;
type QuadrantOption = '1' | '2' | '3' | '4';

const ALL_QUADRANT_OPTIONS: Array<{ value: QuadrantOption; label: string }> = [
  { value: '1', label: '1' },
  { value: '2', label: '2' },
  { value: '3', label: '3' },
  { value: '4', label: '4' },
];

const defaultSegment = (type: RampEditorSegment['type']): RampEditorSegment => type === 'linear'
  ? { type: 'linear', length: 0.05, angle: 15 }
  : { type: 'circular', length: 0.05, angle_start: 45, angle_end: 15, quadrant: 2 };

/**
 * CINDER requires:
 *   Q1/Q4: angle_start <= angle_end
 *   Q2/Q3: angle_start >= angle_end
 */
const allowedQuadrants = (
  angleStart: number,
  angleEnd: number,
): RampQuadrant[] => {
  if (angleStart < angleEnd) return [1, 4];
  if (angleStart > angleEnd) return [2, 3];
  return [1, 2, 3, 4];
};

/**
 * Keep the ramp valid while an angle edit crosses the ordering boundary.
 * Preserve slope sign instead of swapping the user's entered angles:
 *   positive: Q2 <-> Q4
 *   negative: Q3 <-> Q1
 */
const validQuadrantForAngles = (
  quadrant: RampQuadrant,
  angleStart: number,
  angleEnd: number,
): RampQuadrant => {
  const allowed = allowedQuadrants(angleStart, angleEnd);
  if (allowed.includes(quadrant)) return quadrant;

  if (quadrant === 2) return 4;
  if (quadrant === 4) return 2;
  if (quadrant === 3) return 1;
  return 3;
};

const quadrantOptionsFor = (
  segment: CircularRampEditorSegment,
): Array<{ value: QuadrantOption; label: string }> => {
  const allowed = new Set(allowedQuadrants(segment.angle_start, segment.angle_end));
  return ALL_QUADRANT_OPTIONS.filter((option) =>
    allowed.has(Number(option.value) as RampQuadrant));
};

export const RampBuilder = ({
  value,
  onChange,
  className,
  hasChanged = false,
}: RampBuilderProps) => {
  const [segments, setSegments] = useState<RampEditorSegment[]>(
    value.segments.length ? value.segments : [defaultSegment('linear')],
  );

  useEffect(
    () => setSegments(value.segments.length ? value.segments : [defaultSegment('linear')]),
    [value],
  );

  const commit = (next: RampEditorSegment[]) => {
    setSegments(next);
    onChange({ segments: next });
  };

  const update = (index: number, field: string, nextValue: number) => {
    commit(segments.map((segment, segmentIndex) => {
      if (segmentIndex !== index) return segment;

      if (segment.type !== 'circular') {
        return { ...segment, [field]: nextValue } as RampEditorSegment;
      }

      let nextSegment = {
        ...segment,
        [field]: nextValue,
      } as CircularRampEditorSegment;

      if (field === 'angle_start' || field === 'angle_end') {
        nextSegment = {
          ...nextSegment,
          quadrant: validQuadrantForAngles(
            nextSegment.quadrant,
            nextSegment.angle_start,
            nextSegment.angle_end,
          ),
        };
      }

      return nextSegment;
    }));
  };

  const changeType = (index: number, type: RampEditorSegment['type']) => {
    commit(segments.map((segment, segmentIndex) =>
      segmentIndex === index
        ? { ...defaultSegment(type), length: segment.length }
        : segment));
  };

  const fields = (segment: RampEditorSegment): Array<[string, number, string]> =>
    segment.type === 'linear'
      ? [
          ['length', segment.length, 'Length (m)'],
          ['angle', segment.angle, 'Angle (°)'],
        ]
      : [
          ['length', segment.length, 'Length (m)'],
          ['angle_start', segment.angle_start, 'Start Angle (°)'],
          ['angle_end', segment.angle_end, 'End Angle (°)'],
        ];

  return (
    <div className={[styles.rampBuilder, className].filter(Boolean).join(' ')}>
      <div className={styles.rampStatus}>
        <span className={styles.rampLabel}>Ramp Profile</span>
        {hasChanged && (
          <span className={styles.changedBadge}>
            <span className={styles.changeIndicator} />
            <span>Changed</span>
          </span>
        )}
      </div>

      <div className={styles.segmentList}>
        {segments.map((segment, index) => (
          <div key={index} className={styles.segment}>
            <div className={styles.segmentHeader}>
              <span className={styles.segmentNumber}>Segment {index + 1}</span>
              {segments.length > 1 && (
                <Button
                  type="button"
                  onClick={() => commit(
                    segments.filter((_, candidate) => candidate !== index),
                  )}
                  icon={Trash}
                  title="Remove segment"
                />
              )}
            </div>

            <div className={styles.segmentContent}>
              <Dropdown
                label="Type"
                value={segment.type}
                onChange={(next) =>
                  changeType(index, next as RampEditorSegment['type'])}
                options={[
                  { value: 'linear', label: 'Linear' },
                  { value: 'circular', label: 'Circular' },
                ]}
              />

              <div className={styles.segmentFields}>
                {fields(segment).map(([key, fieldValue, label]) => (
                  <InputField
                    key={key}
                    label={label}
                    type="number"
                    value={fieldValue}
                    onChange={(event) =>
                      update(index, key, Number(event.target.value))}
                  />
                ))}

                {segment.type === 'circular' && (
                  <Dropdown
                    label="Quadrant"
                    value={String(segment.quadrant) as QuadrantOption}
                    onChange={(next) =>
                      update(index, 'quadrant', Number(next))}
                    options={quadrantOptionsFor(segment)}
                  />
                )}
              </div>
            </div>
          </div>
        ))}
      </div>

      <div className={styles.addSegmentButton}>
        <Button
          onClick={() => commit([...segments, defaultSegment('linear')])}
          icon={Plus}
          text="Add Segment"
        />
      </div>
    </div>
  );
};
