import { useCallback, useEffect, useState } from 'react';
import { Alert, Group, Loader, Stack, Text } from '@mantine/core';
import { ActionButton as Button } from '@components/button/ActionButton';
import { Modal } from '@components/modal/Modal';
import {
  EditorHistoryBoundary,
  UndoRedoControls,
} from '@components/editorHistory/EditorHistory';
import { useEditorHistory } from '@components/editorHistory/useEditorHistory';
import { QuantityValidationContext } from '@components/quantityInput/validation';
import { TuneEditor } from '../experiments/TuneEditor';
import {
  tuneGeometryBlocker,
  type TuneCheck,
} from '../experiments/tunePreviewState';
import type { Tune } from '../experiments/api';
import {
  applyInitialTune,
  initialTuneSurface,
  previewInitialTune,
  type CvtData,
  type InitialTuneSurface,
} from './api';

function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : 'Unable to update the initial tune.';
}

export function InitialTunePanel({
  value,
  onChange,
  disabled = false,
  onSaveBlockChange,
}: {
  value: CvtData;
  onChange: (value: CvtData) => void;
  disabled?: boolean;
  onSaveBlockChange?: (message: string | null) => void;
}) {
  const [opened, setOpened] = useState(false);
  const [surface, setSurface] = useState<InitialTuneSurface | null>(null);
  const [base, setBase] = useState<CvtData | null>(null);
  const [check, setCheck] = useState<TuneCheck | null>(null);
  const [invalid, setInvalid] = useState(new Set<string>());
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [confirmDiscard, setConfirmDiscard] = useState(false);
  const draft = useEditorHistory<Tune | null>(null);
  const { history, value: tune, setValue: setTune } = draft;

  useEffect(() => {
    onSaveBlockChange?.(
      opened ? 'Finish or close Initial tune before saving the CVT.' : null,
    );
    return () => onSaveBlockChange?.(null);
  }, [opened, onSaveBlockChange]);

  const close = useCallback(() => {
    setOpened(false);
    setConfirmDiscard(false);
    setSurface(null);
    setBase(null);
    setCheck(null);
    setInvalid(new Set());
    setError(null);
    history.reset(null);
  }, [history]);

  const requestClose = () => {
    if (busy) return;
    if (draft.dirty || invalid.size > 0) setConfirmDiscard(true);
    else close();
  };

  const open = async () => {
    if (disabled || busy) return;
    setOpened(true);
    setBusy(true);
    setError(null);
    setCheck(null);
    setInvalid(new Set());
    const snapshot = structuredClone(value);
    setBase(snapshot);
    try {
      const next = await initialTuneSurface(snapshot);
      setSurface(next);
      history.reset({
        kind: 'tunes',
        name: 'Initial tune',
        notes: '',
        cvt_revision_id: 'working-copy',
        values: structuredClone(next.values),
      });
    } catch (reason) {
      setError(errorMessage(reason));
    } finally {
      setBusy(false);
    }
  };

  const previewRequest = useCallback(
    async (candidate: Tune, signal?: AbortSignal) => {
      if (!base) throw new Error('The CVT working copy is not ready.');
      return previewInitialTune(base, candidate.values ?? {}, signal);
    },
    [base],
  );

  const blocker =
    tune && surface
      ? invalid.size > 0 || draft.invalidCount > 0
        ? 'Correct the highlighted inputs.'
        : tuneGeometryBlocker(tune, check)
      : 'Loading initial tune…';

  const apply = async () => {
    if (!base || !tune || blocker || busy) return;
    setBusy(true);
    setError(null);
    try {
      const next = await applyInitialTune(base, tune.values ?? {});
      onChange(next);
      close();
    } catch (reason) {
      setError(errorMessage(reason));
    } finally {
      setBusy(false);
    }
  };

  return (
    <>
      <Stack gap="sm">
        <Text size="sm">
          Set the starting flyweight, spring, ramp and helix values for this
          new CVT using the same controls as Tunes. The first CVT save creates
          its Default tune from the applied values.
        </Text>
        <Text size="xs" c="dimmed">
          Ramp placement remains relative to the fixed pivot. Nothing here is
          persisted until the CVT itself is saved.
        </Text>
        <Group>
          <Button
            variant="light"
            disabled={disabled}
            onClick={() => void open()}
          >
            Adjust initial tune
          </Button>
        </Group>
      </Stack>

      <Modal
        opened={opened}
        onClose={requestClose}
        title="Initial tune"
        size="min(1180px, 96vw)"
        closeOnClickOutside={false}
      >
        <EditorHistoryBoundary history={history} disabled={busy}>
          <QuantityValidationContext.Provider value={setInvalid}>
            <Stack gap="md">
              <Text size="sm" c="dimmed">
                These are Tune controls for the unsaved CVT, not additional
                hardware-placement inputs. Apply once when you are happy with
                them; the whole change is one CVT undo step.
              </Text>
              <UndoRedoControls history={history} disabled={busy} />
              {busy && !surface && (
                <Group>
                  <Loader size="sm" />
                  <Text size="sm">Loading Tune controls…</Text>
                </Group>
              )}
              {error && <Alert color="red">{error}</Alert>}
              {surface && tune && (
                <TuneEditor
                  value={tune}
                  surface={{ fields: surface.fields }}
                  onChange={setTune}
                  onValidationChange={setCheck}
                  previewRequest={previewRequest}
                />
              )}
              {surface && (
                <Group justify="flex-end">
                  <Button
                    variant="default"
                    disabled={busy}
                    onClick={requestClose}
                  >
                    Cancel
                  </Button>
                  <Button
                    loading={busy}
                    disabledReason={blocker}
                    onClick={() => void apply()}
                  >
                    Apply to CVT
                  </Button>
                </Group>
              )}
              {surface && blocker && (
                <Text size="xs" c="dimmed" role="status">
                  {blocker}
                </Text>
              )}
            </Stack>
          </QuantityValidationContext.Provider>
        </EditorHistoryBoundary>
      </Modal>

      <Modal
        opened={confirmDiscard}
        onClose={() => setConfirmDiscard(false)}
        title="Discard initial tune changes?"
        closeOnClickOutside={false}
      >
        <Stack>
          <Text>
            These Tune edits have not been applied to the CVT. Closing now
            discards only this Initial tune draft.
          </Text>
          <Group justify="flex-end">
            <Button
              variant="default"
              onClick={() => setConfirmDiscard(false)}
            >
              Keep editing
            </Button>
            <Button color="red" onClick={close}>
              Discard tune edits
            </Button>
          </Group>
        </Stack>
      </Modal>
    </>
  );
}
