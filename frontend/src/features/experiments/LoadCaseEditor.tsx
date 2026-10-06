import { FormError } from '@components/form/FormError';
import { useEffect, useState } from 'react';
import { Modal } from '@components/modal/Modal';
import { Group, Loader, Stack, Text, TextInput } from '@mantine/core';
import { ActionButton as Button } from '@components/button/ActionButton';
import { QuantityValidationContext } from '@components/quantityInput/validation';
import {
  getExperiment,
  getExperimentMetadata,
  message,
  saveExperiment,
  type ExperimentDetail,
  type ExperimentMetadata,
  type Scenario,
} from './api';
import { RevisionToolbar } from './RevisionToolbar';
import { ScenarioEditor } from './ScenarioEditor';
import { useHistory } from './useHistory';

/** One editor for library items and run-builder creation, with revision-safe saves. */
export function LoadCaseEditor({
  id,
  onSaved,
  onClose,
}: {
  id: string | null;
  onSaved: (detail: ExperimentDetail) => void;
  onClose: () => void;
}) {
  const [metadata, setMetadata] = useState<ExperimentMetadata | null>(null);
  const [detail, setDetail] = useState<ExperimentDetail | null>(null);
  const history = useHistory<Scenario | null>(null);
  const reset = history.reset;
  const [busy, setBusy] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [invalid, setInvalid] = useState(new Set<string>());
  const [roadValid, setRoadValid] = useState(false);
  const [retry, setRetry] = useState(0);
  const [saved, setSaved] = useState('');
  const dirty = history.value && JSON.stringify(history.value) !== saved;
  useEffect(() => {
    let cancelled = false;
    setBusy(true);
    setError(null);
    void Promise.all([
      getExperimentMetadata(),
      id ? getExperiment(id) : Promise.resolve(null),
    ])
      .then(([meta, current]) => {
        if (cancelled) return;
        const document = current?.document ?? {
          ...meta.scenario_template,
          name: '',
        };
        if (document.kind !== 'scenarios')
          throw new Error('This item is not a load case.');
        setMetadata(meta);
        setDetail(current);
        reset(document);
        setSaved(JSON.stringify(document));
      })
      .catch((cause) => {
        if (!cancelled) setError(message(cause));
      })
      .finally(() => {
        if (!cancelled) setBusy(false);
      });
    return () => {
      cancelled = true;
    };
  }, [id, reset, retry]);
  useEffect(() => {
    if (!dirty) return;
    const warn = (event: BeforeUnloadEvent) => {
      event.preventDefault();
      event.returnValue = '';
    };
    window.addEventListener('beforeunload', warn);
    return () => window.removeEventListener('beforeunload', warn);
  }, [dirty]);
  const close = () => {
    if (
      !busy &&
      (!dirty || window.confirm('Discard unsaved load-case changes?'))
    )
      onClose();
  };
  const save = async (asNew: boolean) => {
    if (!history.value) return;
    setBusy(true);
    setError(null);
    try {
      const result = await saveExperiment(history.value, detail, asNew);
      setSaved(JSON.stringify(result.document));
      onSaved(result);
    } catch (cause) {
      setError(message(cause));
    } finally {
      setBusy(false);
    }
  };
  return (
    <Modal
      opened
      onClose={close}
      title={id ? 'Load case' : 'Create load case'}
      size="min(1200px, 96vw)"
      styles={{
        header: { position: 'sticky', top: 0, zIndex: 3 },
        body: { paddingBottom: 'var(--mantine-spacing-xl)' },
      }}
      closeOnEscape={!busy}
      closeOnClickOutside={false}
    >
      <Stack>
        {error && (
          <FormError color="red" role="alert">
            {error}
            {!metadata && (
              <Button variant="subtle" onClick={() => setRetry((x) => x + 1)}>
                Try again
              </Button>
            )}
          </FormError>
        )}
        {!metadata || !history.value ? (
          busy && <Loader aria-label="Loading load case" />
        ) : (
          <QuantityValidationContext.Provider value={setInvalid}>
            <Text size="sm" c="dimmed">
              Save this road once and select it for any vehicle. Saved load
              cases are public; editing another author's case creates your own
              copy.
            </Text>
            <fieldset
              disabled={busy}
              style={{ border: 0, padding: 0, margin: 0, minWidth: 0 }}
            >
              <Stack>
                <TextInput
                  label="Load case name"
                  required
                  placeholder="Give this course a name"
                  value={history.value.name}
                  onChange={(e) =>
                    history.change({
                      ...history.value!,
                      name: e.currentTarget.value,
                    })
                  }
                />
                <Group>
                  <Button
                    size="xs"
                    variant="default"
                    disabledReason={
                      !history.canUndo
                        ? 'There are no edits to undo.'
                        : undefined
                    }
                    onClick={history.undo}
                  >
                    Undo
                  </Button>
                  <Button
                    size="xs"
                    variant="default"
                    disabledReason={
                      !history.canRedo
                        ? 'There are no edits to redo.'
                        : undefined
                    }
                    onClick={history.redo}
                  >
                    Redo
                  </Button>
                </Group>
                <ScenarioEditor
                  value={history.value}
                  metadata={metadata}
                  onChange={history.change}
                  onRoadValidityChange={setRoadValid}
                />
                <div
                  style={{
                    position: 'sticky',
                    bottom: 0,
                    padding: '12px 0',
                    background: 'var(--mantine-color-body)',
                    zIndex: 2,
                    borderTop: '1px solid var(--mantine-color-default-border)',
                  }}
                >
                  <RevisionToolbar
                    label="Load case"
                    showPicker={false}
                    showFields={false}
                    document={history.value}
                    detail={detail}
                    items={[]}
                    busy={busy}
                    invalid={Boolean(invalid.size) || !roadValid}
                    onChange={(next) =>
                      next.kind === 'scenarios' && history.change(next)
                    }
                    onLoad={() => {}}
                    onNew={() => {}}
                    onSave={(asNew) => void save(asNew)}
                    onRefresh={() => setRetry((x) => x + 1)}
                    onRestored={(next) => {
                      setDetail(next);
                      if (next.document.kind === 'scenarios') {
                        reset(next.document);
                        setSaved(JSON.stringify(next.document));
                      }
                    }}
                  />
                </div>
              </Stack>
            </fieldset>
          </QuantityValidationContext.Provider>
        )}
      </Stack>
    </Modal>
  );
}
