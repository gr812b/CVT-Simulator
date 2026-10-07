import { useCallback, useContext, useEffect, useId, useState, useSyncExternalStore } from 'react';
import { TextInput } from '@mantine/core';
import { useAuth } from '@contexts/AuthContext';
import { QuantityValidationContext } from './validation';
import { EditorHistoryContext } from '../editorHistory/context';
import type { QuantityDraft } from '../editorHistory/draftHistory';
import { editQuantity, quantityError } from './quantityDraft';
import {
  dimensionForUnit, displayUnitForCanonical, formatEditableQuantity, normalizeUnitPreferences,
  preferredDisplayUnit, sameQuantity, type QuantityDimension, type UnitScope,
} from '@utils/units';

const EMPTY = { quantities: {} as Readonly<Record<string, QuantityDraft>>, epoch: 0, canUndo: false, canRedo: false };
const noSubscription = () => () => undefined;
const emptySnapshot = () => EMPTY;

export function QuantityInput({
  label, value, onChange, unit = '', dimension: requestedDimension, scope = 'default', description,
  min, max, integer = false, disabled = false, onFocusChange, draftKey, documentPath,
}: {
  label: string;
  value: number | null;
  onChange: (value: number) => void;
  unit?: string;
  /** Retained for source compatibility; recognized units own their conversion factor. */
  scale?: number;
  dimension?: QuantityDimension;
  scope?: UnitScope;
  description?: string;
  min?: number;
  max?: number;
  integer?: boolean;
  disabled?: boolean;
  onFocusChange?: (focused: boolean) => void;
  draftKey?: string;
  documentPath?: string;
}) {
  const id = useId();
  const history = useContext(EditorHistoryContext);
  const snapshot = useSyncExternalStore(history?.subscribe ?? noSubscription,
    history?.getSnapshot ?? emptySnapshot, history?.getSnapshot ?? emptySnapshot);
  const key = draftKey ?? `${scope}:${label}`;
  const { session } = useAuth();
  const preferences = normalizeUnitPreferences(session?.user.unit_preferences);
  const knownDimension = requestedDimension ?? dimensionForUnit(unit);
  const dimension = knownDimension ?? 'dimensionless';
  const configurationError = !knownDimension && unit !== '' ? `Unsupported field unit: ${unit}` : undefined;
  const fallbackUnit = displayUnitForCanonical(unit, dimension);
  const displayUnit = preferredDisplayUnit(dimension, scope, preferences, fallbackUnit);
  const setInvalid = useContext(QuantityValidationContext);
  const [localDraft, setLocalDraft] = useState<QuantityDraft | undefined>(undefined);
  const [entryUnit, setEntryUnit] = useState(displayUnit);
  const [focused, setFocused] = useState(false);
  const draft = history ? snapshot.quantities[key] : localDraft;
  const limits = { min, max, integer };
  const error = configurationError ?? draft?.error ?? quantityError(draft ? draft.valueSi : value, limits);
  const invalid = error !== undefined && (!disabled || draft !== undefined);
  const writeDraft = useCallback((next: QuantityDraft | undefined) => {
    if (history) history.setQuantity(key, next);
    else setLocalDraft(next);
  }, [history, key]);
  const setValidity = useCallback((bad: boolean) => {
    setInvalid?.(previous => {
      if (previous.has(id) === bad) return previous;
      const next = new Set(previous);
      if (bad) next.add(id); else next.delete(id);
      return next;
    });
  }, [id, setInvalid]);
  useEffect(() => { setValidity(invalid); }, [invalid, setValidity]);
  useEffect(() => () => { setValidity(false); }, [setValidity]);
  useEffect(() => {
    // A genuine external replacement (not our own accepted edit) invalidates stale text.
    // Undo/redo restore a matching value+text frame together. Unit changes never enter here.
    if (draft && !sameQuantity(value, draft.sourceValue) && !sameQuantity(value, draft.valueSi))
      writeDraft(undefined);
  }, [value, draft, writeDraft]);

  const normalize = () => {
    if (!draft || disabled) return; // Focus/blur must not round-trip an untouched value.
    const checked = editQuantity(draft.text, dimension, draft.entryUnit, value, limits, documentPath);
    if (checked.error) { writeDraft(checked); setValidity(true); return; }
    // Valid text is sent synchronously on input. Do not silently discard a value
    // rejected by a higher-level control (e.g. a profile-stage constraint).
    if (!sameQuantity(value, checked.valueSi)) {
      writeDraft({ ...checked, error: 'This value could not be applied. Check the neighbouring settings.' });
      setValidity(true);
      return;
    }
    writeDraft(undefined);
    setValidity(false);
  };
  return <TextInput
    key={snapshot.epoch}
    id={id}
    label={label}
    description={description}
    value={draft?.text ?? (value === null ? '' : formatEditableQuantity(value, focused ? entryUnit : displayUnit))}
    disabled={disabled}
    data-quantity-input
    onFocus={() => { setFocused(true); setEntryUnit(draft?.entryUnit ?? displayUnit); onFocusChange?.(true); }}
    onBlur={() => { normalize(); setFocused(false); history?.endGroup(); onFocusChange?.(false); }}
    onKeyDown={event => {
      if (event.key === 'Enter' && !event.nativeEvent.isComposing) {
        event.preventDefault();
        event.currentTarget.blur(); // One normalization, not Enter plus blur twice.
      }
    }}
    onChange={event => {
      const next = editQuantity(event.currentTarget.value, dimension, draft?.entryUnit ?? entryUnit,
        value, limits, documentPath);
      const apply = () => {
        writeDraft(next);
        setValidity(next.error !== undefined || configurationError !== undefined);
        if (!configurationError && !next.error && next.valueSi !== null && !sameQuantity(value, next.valueSi))
          onChange(next.valueSi);
      };
      if (history) { history.beginGroup(`quantity:${key}`); history.transaction(apply); }
      else apply();
    }}
    required
    error={invalid ? error : undefined}
  />;
}
