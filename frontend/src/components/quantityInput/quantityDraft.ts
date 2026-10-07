import { parseQuantityText, sameQuantity, type DisplayUnit, type QuantityDimension } from '../../utils/units';
import type { QuantityDraft } from '../editorHistory/draftHistory';

export interface QuantityLimits { min?: number; max?: number; integer?: boolean }
export function quantityError(value: number | null, limits: QuantityLimits): string | undefined {
  if (value === null || !Number.isFinite(value)) return 'Enter a finite value.';
  if (limits.min !== undefined && value < limits.min) return 'The value is below the allowed minimum.';
  if (limits.max !== undefined && value > limits.max) return 'The value is above the allowed maximum.';
  if (limits.integer && !Number.isInteger(value)) return 'Enter a whole number.';
  return undefined;
}
export function editQuantity(text: string, dimension: QuantityDimension, entryUnit: DisplayUnit,
  value: number | null, limits: QuantityLimits, documentPath?: string): QuantityDraft {
  const parsed = parseQuantityText(text, dimension, entryUnit);
  const error = parsed.error ?? quantityError(parsed.valueSi ?? null, limits);
  return { text, dimension, entryUnit, sourceValue: value,
    valueSi: error ? value : sameQuantity(value, parsed.valueSi!) ? value : parsed.valueSi!,
    ...(error ? { error } : {}), ...(documentPath ? { documentPath } : {}),
  };
}
