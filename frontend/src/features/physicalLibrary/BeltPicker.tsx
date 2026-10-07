import { FormError } from '@components/form/FormError';
import { useState } from 'react';
import { Modal } from '@components/modal/Modal';
import { Group, Select, Stack, Text, TextInput } from '@mantine/core';
import { ActionButton as Button } from '@components/button/ActionButton';
import { QuantityValidationContext } from '@components/quantityInput/validation';
import { useAuth } from '@contexts/AuthContext';
import {
  formatPreferredQuantity,
  normalizeUnitPreferences,
} from '@utils/units';
import { BeltEditor } from './BeltEditor';
import { libraryOptions } from './libraryOptions';
import {
  getPhysical,
  physicalTemplate,
  savePhysical,
  type BeltChoice,
  type PhysicalDocument,
  type PhysicalItem,
} from './api';

export function BeltPicker({
  value,
  onChange,
  items,
  disabled = false,
  onLoadingChange,
}: {
  value: BeltChoice;
  onChange: (value: BeltChoice) => void;
  items: PhysicalItem[];
  disabled?: boolean;
  onLoadingChange?: (busy: boolean) => void;
}) {
  const { unitPreferences } = useAuth();
  const preferences = normalizeUnitPreferences(unitPreferences);
  const [added, setAdded] = useState<PhysicalItem[]>([]);
  const [draft, setDraft] = useState<Extract<
    PhysicalDocument,
    { kind: 'belts' }
  > | null>(null);
  const [invalid, setInvalid] = useState(new Set<string>());
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const catalog = [
    ...items,
    ...added.filter((item) => !items.some((other) => other.id === item.id)),
  ];
  const options = libraryOptions(catalog, (item) => item.revision_id);
  if (!catalog.some((item) => item.revision_id === value.revision_id)) {
    options.unshift({
      group: 'Current selection',
      items: [{ value: value.revision_id ?? 'working', label: value.name }],
    });
  }
  const task = async (action: () => Promise<void>) => {
    setBusy(true);
    onLoadingChange?.(true);
    setError(null);
    try {
      await action();
    } catch (cause) {
      setError(
        cause instanceof Error ? cause.message : 'Unable to load this belt.',
      );
    } finally {
      setBusy(false);
      onLoadingChange?.(false);
    }
  };
  return (
    <Stack gap="sm">
      <Group align="end">
        <Select
          style={{ flex: '1 1 240px' }}
          label="Belt"
          searchable
          allowDeselect={false}
          value={value.revision_id ?? 'working'}
          data={options}
          disabled={disabled || busy}
          onChange={(revision) => {
            const item = catalog.find(
              (entry) => entry.revision_id === revision,
            );
            if (item)
              void task(async () => {
                const detail = await getPhysical(
                  'belts',
                  item.id,
                  item.revision_id,
                );
                if (detail.document.kind === 'belts') {
                  const { kind: _, ...belt } = detail.document;
                  void _;
                  onChange({ ...belt, revision_id: item.revision_id });
                }
              });
          }}
        />
        {!disabled && (
          <Button
            variant="default"
            loading={busy}
            onClick={() =>
              void task(async () => {
                const template = await physicalTemplate('belts');
                if (template.kind === 'belts') {
                  setInvalid(new Set());
                  setDraft({ ...template, name: '' });
                }
              })
            }
          >
            New belt
          </Button>
        )}
      </Group>
      <Text size="sm" c="dimmed">
        {formatPreferredQuantity(value.data.outer_length_m, 'length', 'hardware', preferences, 'mm', 1)} outer length ·{' '}
        {formatPreferredQuantity(value.data.outer_width_m, 'length', 'hardware', preferences, 'mm', 2)} /{' '}
        {formatPreferredQuantity(value.data.inner_width_m, 'length', 'hardware', preferences, 'mm', 2)} top / bottom ·{' '}
        {formatPreferredQuantity(value.data.height_m, 'length', 'hardware', preferences, 'mm', 2)} height ·{' '}
        {((value.data.half_angle_rad * 180) / Math.PI).toFixed(2)}° half-angle
      </Text>
      {error && !draft && (
        <FormError color="red" role="alert">
          {error}
        </FormError>
      )}
      <Modal
        opened={Boolean(draft)}
        onClose={() => {
          if (!busy) {
            setDraft(null);
            setError(null);
          }
        }}
        title="Create a reusable belt"
        size="lg"
        closeOnClickOutside={!busy}
      >
        {draft && (
          <QuantityValidationContext.Provider value={setInvalid}>
            <Stack>
              <TextInput
                label="Belt name"
                required
                value={draft.name}
                maxLength={240}
                onChange={(event) =>
                  setDraft({ ...draft, name: event.currentTarget.value })
                }
              />
              <BeltEditor
                value={draft.data}
                onChange={(data) =>
                  setDraft((current) => current && { ...current, data })
                }
              />
              {error && (
                <FormError color="red" role="alert">
                  {error}
                </FormError>
              )}
              <Button
                loading={busy}
                disabledReason={
                  invalid.size
                    ? 'Complete the belt measurements and wait for calculation.'
                    : !draft.name.trim()
                      ? 'Enter a belt name.'
                      : undefined
                }
                onClick={() =>
                  void task(async () => {
                    const { detail } = await savePhysical(draft, null);
                    if (detail.document.kind !== 'belts') return;
                    const { kind: _, ...belt } = detail.document;
                    void _;
                    setAdded((previous) => [...previous, detail.item]);
                    onChange({ ...belt, revision_id: detail.item.revision_id });
                    setDraft(null);
                  })
                }
              >
                Save belt and select
              </Button>
            </Stack>
          </QuantityValidationContext.Provider>
        )}
      </Modal>
    </Stack>
  );
}
