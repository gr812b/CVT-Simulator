import { useContext, useEffect, useId, useState } from 'react';
import { NumberInput } from '@mantine/core';
import { QuantityValidationContext } from './validation';
import { displayScale } from '@utils/units';

export function QuantityInput({
  label,
  value,
  onChange,
  unit = '',
  scale: requestedScale,
  description,
  min,
  max,
  integer = false,
  disabled = false,
}: {
  label: string;
  value: number | null;
  onChange: (value: number) => void;
  unit?: string;
  scale?: number;
  description?: string;
  min?: number;
  max?: number;
  integer?: boolean;
  disabled?: boolean;
}) {
  const id = useId();
  const scale = requestedScale ?? displayScale(unit);
  const setInvalid = useContext(QuantityValidationContext);
  const display = value === null ? '' : Number((value * scale).toPrecision(12));
  const [working, setWorking] = useState<string | number>(display);
  useEffect(() => {
    setWorking(display);
  }, [display]);
  const valid =
    typeof working === 'number' &&
    Number.isFinite(working) &&
    (min === undefined || working / scale >= min) &&
    (max === undefined || working / scale <= max) &&
    (!integer || Number.isInteger(working));
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
  return (
    <NumberInput
      id={id}
      label={label}
      description={description}
      value={working}
      disabled={disabled}
      onChange={(next) => {
        setWorking(next);
        if (typeof next === 'number' && Number.isFinite(next))
          onChange(next / scale);
      }}
      required
      suffix={unit ? ` ${unit}` : undefined}
      allowDecimal={!integer}
      min={min === undefined ? undefined : min * scale}
      max={max === undefined ? undefined : max * scale}
      clampBehavior="none"
      hideControls={!integer}
      error={
        !valid && !disabled
          ? working === ''
            ? 'Enter a value.'
            : 'Check the allowed range.'
          : undefined
      }
    />
  );
}
