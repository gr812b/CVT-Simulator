import { useState } from 'react';
import { Group, Stack, TextInput, Textarea, Text } from '@mantine/core';
import { Modal } from '@components/modal/Modal';
import { ActionButton as Button } from '@components/button/ActionButton';
import { FormError } from '@components/form/FormError';
import { QuantityValidationContext } from '@components/quantityInput/validation';
import { TuneEditor } from './TuneEditor';
import {
  saveExperiment,
  message,
  type Tune,
  type TuneSurface,
  type ExperimentDetail,
} from './api';

export function TuneDialog({
  surface,
  initial,
  detail = null,
  mode,
  onClose,
  onSaved,
  onUse,
}: {
  surface: TuneSurface;
  initial?: Tune;
  detail?: ExperimentDetail | null;
  mode: 'new' | 'edit' | 'copy';
  onClose: () => void;
  onSaved: (detail: ExperimentDetail) => void;
  onUse?: (value: Tune) => void;
}) {
  const [value, setValue] = useState<Tune>(() => ({
    ...(initial ?? surface.template),
    name: mode === 'edit' ? (initial?.name ?? '') : '',
  }));
  const [invalid, setInvalid] = useState(new Set<string>());
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const save = async () => {
    setError(null);
    if (!value.name.trim() || invalid.size) {
      setError('Give this tune a name and correct the highlighted inputs.');
      return;
    }
    setBusy(true);
    try {
      onSaved(await saveExperiment(value, detail, mode !== 'edit'));
    } catch (cause) {
      setError(message(cause));
    } finally {
      setBusy(false);
    }
  };
  return (
    <Modal
      opened
      onClose={() => {
        if (!busy) onClose();
      }}
      title={mode === 'edit' ? 'Edit tune' : 'Add tune'}
      size="min(1100px, 96vw)"
      closeOnClickOutside={false}
    >
      <QuantityValidationContext.Provider value={setInvalid}>
        <Stack>
          <Text size="sm" c="dimmed">
            For {surface.cvt_name}
          </Text>
          <TextInput
            label="Tune name"
            required
            value={value.name}
            maxLength={240}
            disabled={busy}
            placeholder="Name your tune"
            onChange={(event) =>
              setValue({ ...value, name: event.currentTarget.value })
            }
          />
          <Textarea
            label="Description"
            autosize
            minRows={2}
            maxLength={4000}
            value={value.notes ?? ''}
            disabled={busy}
            onChange={(event) =>
              setValue({ ...value, notes: event.currentTarget.value })
            }
          />
          <fieldset
            disabled={busy}
            style={{ border: 0, padding: 0, margin: 0 }}
          >
            <TuneEditor value={value} surface={surface} onChange={setValue} />
          </fieldset>
          {error && <FormError key={error}>{error}</FormError>}
          <Group justify="flex-end">
            <Button variant="default" disabled={busy} onClick={onClose}>
              Cancel
            </Button>
            {onUse && (
              <Button
                variant="light"
                disabledReason={
                  invalid.size ? 'Correct the highlighted inputs.' : undefined
                }
                disabled={busy}
                onClick={() => onUse(value)}
              >
                Use for this run only
              </Button>
            )}
            <Button loading={busy} onClick={() => void save()}>
              Save tune
            </Button>
          </Group>
        </Stack>
      </QuantityValidationContext.Provider>
    </Modal>
  );
}
