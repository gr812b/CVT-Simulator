import { useEffect, useState } from 'react';
import { Group, Stack, TextInput, Textarea, Text } from '@mantine/core';
import { Modal } from '@components/modal/Modal';
import { ActionButton as Button } from '@components/button/ActionButton';
import { FormError } from '@components/form/FormError';
import { QuantityValidationContext } from '@components/quantityInput/validation';
import { overlayLayers } from '../../styles/theme';
import { TuneEditor } from './TuneEditor';
import { tuneGeometryBlocker, type TuneCheck } from './tunePreviewState';
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
  const [baseline] = useState(() => JSON.stringify(value));
  const [confirmDiscard, setConfirmDiscard] = useState(false);
  const [textEdited, setTextEdited] = useState(false);
  const [invalid, setInvalid] = useState(new Set<string>());
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [geometryCheck, setGeometryCheck] = useState<TuneCheck | null>(null);
  // Compare the current draft key synchronously during render. Do not wait for
  // the child's debounced request/effect to invalidate a previous approval.
  const useBlocker = invalid.size ? 'Correct the highlighted inputs.' : tuneGeometryBlocker(value, geometryCheck);
  const saveBlocker = !value.name.trim() ? 'Give this tune a name.' : useBlocker;
  const dirty = JSON.stringify(value) !== baseline || (textEdited && invalid.size > 0);
  const requestClose = () => {
    if (busy) return;
    if (dirty) setConfirmDiscard(true);
    else onClose();
  };
  useEffect(() => {
    if (!dirty) return;
    const beforeUnload = (event: BeforeUnloadEvent) => {
      event.preventDefault();
      event.returnValue = '';
    };
    window.addEventListener('beforeunload', beforeUnload);
    return () => window.removeEventListener('beforeunload', beforeUnload);
  }, [dirty]);
  const save = async () => {
    if (busy) return;
    setError(null);
    if (saveBlocker) {
      setError(saveBlocker);
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
    <>
    <Modal
      opened
      onClose={requestClose}
      closeOnEscape={!confirmDiscard && !busy}
      title={mode === 'edit' ? 'Edit tune' : 'Add tune'}
      size="min(1100px, 96vw)"
      closeOnClickOutside={false}
    >
      <QuantityValidationContext.Provider value={setInvalid}>
        <Stack onInputCapture={(event) => {
          if (event.target instanceof HTMLInputElement || event.target instanceof HTMLTextAreaElement) setTextEdited(true);
        }}>
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
            <TuneEditor value={value} surface={surface} onChange={setValue} onValidationChange={setGeometryCheck} />
          </fieldset>
          {error && <FormError key={error}>{error}</FormError>}
          {useBlocker && <Text size="sm" c="dimmed" role="status">{useBlocker}</Text>}
          <Group justify="flex-end">
            <Button variant="default" disabled={busy} onClick={requestClose}>
              Cancel
            </Button>
            {onUse && (
              <Button
                variant="light"
                disabledReason={useBlocker}
                disabled={busy}
                onClick={() => { if (!busy && !useBlocker) onUse(value); }}
              >
                Use for this run only
              </Button>
            )}
            <Button loading={busy} disabledReason={saveBlocker} onClick={() => void save()}>
              Save tune
            </Button>
          </Group>
        </Stack>
      </QuantityValidationContext.Provider>
    </Modal>
    <Modal
      opened={confirmDiscard}
      onClose={() => setConfirmDiscard(false)}
      title="Discard unsaved tune changes?"
      closeOnClickOutside={false}
      zIndex={overlayLayers.modalDropdown + 10}
    >
      <Stack>
        <Text>Your changes have not been saved. Discarding them will leave the saved tune unchanged.</Text>
        <Group justify="flex-end">
          <Button data-autofocus variant="default" onClick={() => setConfirmDiscard(false)}>
            Keep editing
          </Button>
          <Button color="red" onClick={onClose}>Discard changes</Button>
        </Group>
      </Stack>
    </Modal>
    </>
  );
}
