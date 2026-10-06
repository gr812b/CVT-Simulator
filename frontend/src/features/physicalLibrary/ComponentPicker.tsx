import { FormError } from '@components/form/FormError';
import { libraryOptions } from './libraryOptions';
import { useState } from 'react';
import { Group, Select, Stack, Text, TextInput } from '@mantine/core';
import { ActionButton as Button } from '@components/button/ActionButton';
import {
  getPhysical,
  physicalTemplate,
  singularLabels,
  type BeltChoice,
  type CvtChoice,
  type EngineChoice,
  type PhysicalItem,
} from './api';

type Choices = { engines: EngineChoice; belts: BeltChoice; cvts: CvtChoice };

export function ComponentPicker<K extends keyof Choices>({
  kind,
  value,
  onChange,
  items,
  disabled = false,
  onLoadingChange,
}: {
  kind: K;
  value: Choices[K];
  onChange: (value: Choices[K]) => void;
  items: PhysicalItem[];
  disabled?: boolean;
  onLoadingChange?: (loading: boolean) => void;
}) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const options = libraryOptions(items, (item) => item.revision_id);
  if (
    value.revision_id &&
    !items.some((item) => item.revision_id === value.revision_id)
  ) {
    options.unshift({
      group: 'Current selection',
      items: [{ value: value.revision_id, label: value.name }],
    });
  }
  const select = async (revision: string | null) => {
    if (!revision || revision === value.revision_id) return;
    const item = items.find((entry) => entry.revision_id === revision);
    if (!item) return;
    setBusy(true);
    onLoadingChange?.(true);
    setError(null);
    try {
      const detail = await getPhysical(kind, item.id, revision);
      if (detail.document.kind !== kind)
        throw new Error('This component does not match the selected library.');
      const { kind: documentKind, ...document } = detail.document;
      void documentKind;
      onChange({ ...document, revision_id: revision } as Choices[K]);
    } catch (reason) {
      setError(
        reason instanceof Error
          ? reason.message
          : 'Unable to load this component.',
      );
    } finally {
      setBusy(false);
      onLoadingChange?.(false);
    }
  };
  const create = async () => {
    setBusy(true);
    onLoadingChange?.(true);
    setError(null);
    try {
      const template = await physicalTemplate(kind);
      const { kind: documentKind, ...document } = template;
      void documentKind;
      onChange({
        ...document,
        name: '',
        revision_id: null,
      } as Choices[K]);
    } catch (reason) {
      setError(
        reason instanceof Error
          ? reason.message
          : 'Unable to start a new component.',
      );
    } finally {
      setBusy(false);
      onLoadingChange?.(false);
    }
  };
  return (
    <Stack gap="sm">
      <Group align="end" wrap="wrap">
        <Select
          style={{ flex: '1 1 250px' }}
          label={`Saved ${singularLabels[kind]}`}
          placeholder="New component — saved with this setup"
          searchable
          data={options}
          value={value.revision_id ?? null}
          disabled={disabled || busy}
          onChange={(next) => void select(next)}
          allowDeselect={false}
          nothingFoundMessage="No saved components"
        />
        {!disabled && (
          <Button
            variant="default"
            loading={busy}
            onClick={() => void create()}
          >
            New {singularLabels[kind]}
          </Button>
        )}
      </Group>
      {!value.revision_id && <TextInput
        label={`${kind === 'cvts' ? 'CVT' : singularLabels[kind][0].toUpperCase() + singularLabels[kind].slice(1)} name`}
        value={value.name}
        disabled={disabled || busy}
        required
        maxLength={240}
        onChange={(event) =>
          onChange({ ...value, name: event.currentTarget.value })
        }
      />}
      {!disabled && !value.revision_id && (
        <Text size="xs" c="dimmed">
          Changes are saved with this setup. Customizing a default creates your
          own copy.
        </Text>
      )}
      {error && (
        <FormError color="red" role="alert">
          {error}
        </FormError>
      )}
    </Stack>
  );
}
