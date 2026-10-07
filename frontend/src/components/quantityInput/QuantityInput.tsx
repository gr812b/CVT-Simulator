import { useContext, useEffect, useId, useMemo, useState } from 'react';
import { TextInput } from '@mantine/core';
import { useAuth } from '@contexts/AuthContext';
import { QuantityValidationContext } from './validation';
import {
  dimensionForUnit,
  displayUnitForCanonical,
  formatEditableQuantity,
  normalizeUnitPreferences,
  parseQuantityText,
  preferredDisplayUnit,
  type DisplayUnit,
  type QuantityDimension,
  type UnitScope,
} from '@utils/units';

export function QuantityInput({
  label,
  value,
  onChange,
  unit = '',
  dimension: requestedDimension,
  scope = 'default',
  description,
  min,
  max,
  integer = false,
  disabled = false,
  onFocusChange,
}: {
  label: string;
  value: number | null;
  onChange: (value: number) => void;
  unit?: string;
  scale?: number;
  dimension?: QuantityDimension;
  scope?: UnitScope;
  description?: string;
  min?: number;
  max?: number;
  integer?: boolean;
  disabled?: boolean;
  onFocusChange?: (focused: boolean) => void;
}) {
  const id = useId();
  const { session } = useAuth();
  const preferences = normalizeUnitPreferences(session?.user.unit_preferences);
  const dimension = requestedDimension ?? dimensionForUnit(unit) ?? 'dimensionless';
  const fallbackUnit = displayUnitForCanonical(unit, dimension) as DisplayUnit;
  const displayUnit = preferredDisplayUnit(dimension, scope, preferences, fallbackUnit);
  const setInvalid = useContext(QuantityValidationContext);
  const display = useMemo(
    () => value === null ? '' : formatEditableQuantity(value, displayUnit),
    [value, displayUnit],
  );
  const [working, setWorking] = useState(display);
  const [focused, setFocused] = useState(false);
  const [entryUnit, setEntryUnit] = useState(displayUnit);
  useEffect(() => {
    if (!focused) {
      setWorking(display);
      setEntryUnit(displayUnit);
    }
  }, [display, displayUnit, focused]);
  const parseUnit = focused ? entryUnit : displayUnit;
  const parsed = parseQuantityText(working, dimension, parseUnit);
  const valid = parsed.error === undefined &&
    Number.isFinite(parsed.valueSi) &&
    (min === undefined || parsed.valueSi >= min) &&
    (max === undefined || parsed.valueSi <= max) &&
    (!integer || Number.isInteger(parsed.valueSi));
  useEffect(() => {
    setInvalid?.((previous) => {
      const next = new Set(previous);
      if (valid || disabled) next.delete(id);
      else next.add(id);
      return next;
    });
    return () =>
      setInvalid?.((previous) => {
        const next = new Set(previous);
        next.delete(id);
        return next;
      });
  }, [id, setInvalid, valid, disabled]);
  const normalize = () => {
    if (valid && parsed.error === undefined) {
      onChange(parsed.valueSi);
      setWorking(formatEditableQuantity(parsed.valueSi, displayUnit));
    }
  };
  return (
    <TextInput
      id={id}
      label={label}
      description={description}
      value={working}
      disabled={disabled}
      onFocus={() => {
        setEntryUnit(displayUnit);
        setFocused(true);
        onFocusChange?.(true);
      }}
      onBlur={() => {
        setFocused(false);
        normalize();
        onFocusChange?.(false);
      }}
      onKeyDown={(event) => {
        if (event.key === 'Enter') {
          event.preventDefault();
          normalize();
          event.currentTarget.blur();
        }
      }}
      onChange={(event) => {
        const next = event.currentTarget.value;
        setWorking(next);
        const candidate = parseQuantityText(next, dimension, parseUnit);
        if (
          candidate.error === undefined &&
          Number.isFinite(candidate.valueSi) &&
          (min === undefined || candidate.valueSi >= min) &&
          (max === undefined || candidate.valueSi <= max) &&
          (!integer || Number.isInteger(candidate.valueSi))
        ) onChange(candidate.valueSi);
      }}
      required
      error={
        !valid && !disabled
          ? parsed.error ?? (integer ? 'Enter a whole number in the allowed range.' : 'Check the allowed range.')
          : undefined
      }
    />
  );
}
