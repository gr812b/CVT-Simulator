import { useEffect, useState } from 'react';
import { InputField } from '@components/inputField/InputField';
import { defaultDisplayUnit, displayToSi, displayUnitForCanonical, isQuantityDimension, siToDisplay } from '@utils/units';

interface Props {
  label: string;
  valueSi: number;
  dimension?: string;
  canonicalUnit: string;
  minimum?: number;
  error?: string | null;
  hasChanged?: boolean;
  onFocus?: () => void;
  onChangeSi: (next: number) => void;
}

/** Existing input styling, with display-only SI conversion at the edge. */
export const DocumentQuantityInput = ({
  label,
  valueSi,
  dimension,
  canonicalUnit,
  minimum,
  error,
  hasChanged,
  onFocus,
  onChangeSi,
}: Props) => {
  const resolvedDimension = isQuantityDimension(dimension) ? dimension : undefined;
  const unit = resolvedDimension
    ? defaultDisplayUnit(resolvedDimension)
    : displayUnitForCanonical(canonicalUnit);
  const labelUnit = unit || canonicalUnit;
  const displayedValue = siToDisplay(valueSi, unit);
  const [text, setText] = useState(String(displayedValue));
  const [editing, setEditing] = useState(false);

  useEffect(() => {
    if (!editing) setText(String(displayedValue));
  }, [displayedValue, editing]);

  const restore = () => setText(String(displayedValue));
  const commit = () => {
    const shown = Number(text);
    if (!Number.isFinite(shown)) {
      restore();
      return;
    }
    const next = displayToSi(shown, unit);
    if (minimum !== undefined && next < minimum) return;
    onChangeSi(next);
  };

  return (
    <InputField
      className="baseInputField"
      label={`${label} (${labelUnit})`}
      type="number"
      value={text}
      error={error}
      hasChanged={hasChanged}
      onFocus={() => {
        setEditing(true);
        onFocus?.();
      }}
      onChange={(event) => setText(event.target.value)}
      onBlur={() => {
        setEditing(false);
        commit();
      }}
      onKeyDown={(event) => {
        if (event.key === 'Enter') event.currentTarget.blur();
        if (event.key === 'Escape') {
          restore();
          event.currentTarget.blur();
        }
      }}
    />
  );
};
