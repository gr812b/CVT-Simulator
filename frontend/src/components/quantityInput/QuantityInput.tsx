import { useEffect, useState } from 'react';
import {
  defaultDisplayUnit,
  displayToSi,
  siToDisplay,
  type DisplayUnit,
  type QuantityDimension,
} from '@utils/units';
import styles from './QuantityInput.module.scss';

export interface QuantityInputProps {
  label: string;
  valueSi: number;
  dimension: QuantityDimension;
  canonicalUnit: string;
  displayUnit?: DisplayUnit;
  description?: string;
  disabled?: boolean;
  minSi?: number;
  step?: number | 'any';
  onChangeSi: (valueSi: number) => void;
}

/** A display-unit input that always persists canonical SI through its callback. */
export const QuantityInput = ({
  label,
  valueSi,
  dimension,
  canonicalUnit,
  displayUnit = defaultDisplayUnit(dimension),
  description,
  disabled = false,
  minSi,
  step = 'any',
  onChangeSi,
}: QuantityInputProps) => {
  const [text, setText] = useState(() => String(siToDisplay(valueSi, displayUnit)));
  const [editing, setEditing] = useState(false);

  useEffect(() => {
    if (!editing) setText(String(siToDisplay(valueSi, displayUnit)));
  }, [displayUnit, editing, valueSi]);

  const commit = () => {
    const shownValue = Number(text);
    if (!Number.isFinite(shownValue)) {
      setText(String(siToDisplay(valueSi, displayUnit)));
      return;
    }
    const nextSi = displayToSi(shownValue, displayUnit);
    if (minSi !== undefined && nextSi < minSi) {
      setText(String(siToDisplay(valueSi, displayUnit)));
      return;
    }
    onChangeSi(nextSi);
    setText(String(siToDisplay(nextSi, displayUnit)));
  };

  return (
    <label className={styles.field} title={description}>
      <span className={styles.label}>{label}</span>
      {description && <span className={styles.description}>{description}</span>}
      <span className={styles.control}>
        <input
          className={styles.input}
          type="number"
          value={text}
          step={step}
          disabled={disabled}
          onFocus={() => setEditing(true)}
          onChange={(event) => setText(event.target.value)}
          onBlur={() => {
            setEditing(false);
            commit();
          }}
          onKeyDown={(event) => {
            if (event.key === 'Enter' || event.key === 'Escape') {
              if (event.key === 'Escape') setText(String(siToDisplay(valueSi, displayUnit)));
              event.currentTarget.blur();
            }
          }}
        />
        <span className={styles.unit}>{displayUnit || canonicalUnit}</span>
      </span>
      <span className={styles.canonical}>Stored as SI: {canonicalUnit}</span>
    </label>
  );
};
