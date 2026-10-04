import { useEffect, useRef, useState } from 'react';
import {
  Alert,
  Badge,
  Button,
  Checkbox,
  Container,
  Group,
  Loader,
  Modal,
  Paper,
  Select,
  Stack,
  Text,
  TextInput,
  Title,
} from '@mantine/core';
import {
  Link,
  useBlocker,
  useNavigate,
  useSearchParams,
} from 'react-router-dom';
import { QuantityInput } from '@components/quantityInput/QuantityInput';
import { QuantityValidationContext } from '@components/quantityInput/validation';
import { listPhysical, type PhysicalItem } from '../physicalLibrary/api';
import { PhysicalStatus } from '../physicalLibrary/PhysicalStatus';
import {
  getExperiment,
  getExperimentMetadata,
  getTuneSurface,
  listExperiments,
  message,
  previewExperiment,
  saveExperiment,
  submitExperiment,
  type ExperimentDetail,
  type ExperimentItem,
  type ExperimentMetadata,
  type ExperimentPreview,
  type ExperimentSelection,
  type Scenario,
  type Tune,
  type TuneSurface,
} from './api';
import { RevisionToolbar } from './RevisionToolbar';
import { ScenarioEditor } from './ScenarioEditor';
import { TuneEditor } from './TuneEditor';
import { useHistory } from './useHistory';
import { useRunActivity } from './RunActivity';

export function ExperimentPage() {
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const { activity, refresh: refreshActivity } = useRunActivity();
  const [metadata, setMetadata] = useState<ExperimentMetadata | null>(null);
  const [setups, setSetups] = useState<PhysicalItem[]>([]);
  const [setupId, setSetupId] = useState<string | null>(null);
  const [surface, setSurface] = useState<TuneSurface | null>(null);
  const [tune, setTune] = useState<Tune | null>(null);
  const [tuneDetail, setTuneDetail] = useState<ExperimentDetail | null>(null);
  const [scenarioDetail, setScenarioDetail] = useState<ExperimentDetail | null>(
    null,
  );
  const [tunes, setTunes] = useState<ExperimentItem[]>([]);
  const [scenarios, setScenarios] = useState<ExperimentItem[]>([]);
  const scenario = useHistory<Scenario | null>(null);
  const resetScenario = scenario.reset;
  const leavingForRun = useRef(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [preview, setPreview] = useState<ExperimentPreview | null>(null);
  const [previewKey, setPreviewKey] = useState('');
  const [invalid, setInvalid] = useState(new Set<string>());
  const [roadValid, setRoadValid] = useState(false);
  const [massOverride, setMassOverride] = useState(false);
  const [mass, setMass] = useState(300);
  const [runName, setRunName] = useState('New experiment');
  const request = useRef({ fingerprint: '', key: crypto.randomUUID() });
  const generation = useRef(0);
  const tuneDirty = Boolean(
    tune &&
    JSON.stringify(tune) !==
      JSON.stringify(tuneDetail?.document ?? surface?.template),
  );
  const scenarioDirty = Boolean(
    scenario.value &&
    JSON.stringify(scenario.value) !==
      JSON.stringify(scenarioDetail?.document ?? metadata?.scenario_template),
  );
  const blocker = useBlocker(
    ({ currentLocation, nextLocation }) =>
      !leavingForRun.current &&
      (tuneDirty || scenarioDirty || massOverride) &&
      currentLocation.pathname !== nextLocation.pathname,
  );
  const selection: ExperimentSelection | null =
    tune && scenario.value
      ? {
          setup_revision_id: tune.setup_revision_id,
          tune_revision_id: tuneDetail?.item.revision_id,
          scenario_revision_id: scenarioDetail?.item.revision_id,
          tune_values: tune.values,
          scenario: scenario.value,
          vehicle_mass_kg: massOverride ? mass : null,
        }
      : null;
  const selectionKey = JSON.stringify(selection);
  const ready = Boolean(
    selection &&
    !busy &&
    !invalid.size &&
    roadValid &&
    tune?.name.trim() &&
    scenario.value?.name.trim(),
  );
  const refreshItems = async () => {
    const [nextTunes, nextScenarios] = await Promise.all([
      listExperiments('tunes'),
      listExperiments('scenarios'),
    ]);
    setTunes(nextTunes);
    setScenarios(nextScenarios);
  };
  const task = async (action: () => Promise<void>) => {
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      await action();
    } catch (cause) {
      setError(message(cause));
    } finally {
      setBusy(false);
    }
  };
  useEffect(() => {
    let disposed = false;
    setBusy(true);
    void Promise.all([
      getExperimentMetadata(),
      listPhysical('setups', 'all'),
      listExperiments('tunes'),
      listExperiments('scenarios'),
    ])
      .then(async ([meta, available, savedTunes, savedScenarios]) => {
        if (disposed) return;
        setMetadata(meta);
        resetScenario(meta.scenario_template);
        setSetups(available);
        setTunes(savedTunes);
        setScenarios(savedScenarios);
        if (params.get('scenario')) {
          const saved = await getExperiment(params.get('scenario')!);
          if (disposed) return;
          if (saved.document.kind === 'scenarios') {
            resetScenario(saved.document);
            setScenarioDetail(saved);
          }
        }
        if (params.get('source_run')) {
          setRunName('New experiment from saved run');
          setNotice(
            'This private setup contains the original run’s frozen hardware, tuning and mass. Its copied scenario is selected. Changes here do not alter the original run.',
          );
        }
        const selected =
          available.find((item) => item.id === params.get('setup')) ??
          available[0];
        if (!selected) return;
        const next = await getTuneSurface(selected.revision_id);
        if (disposed) return;
        setSetupId(selected.id);
        setSurface(next);
        setTune(next.template);
      })
      .catch((cause) => {
        if (!disposed) setError(message(cause));
      })
      .finally(() => {
        if (!disposed) setBusy(false);
      });
    return () => {
      disposed = true;
    };
  }, [params, resetScenario]);
  useEffect(() => {
    if (!tuneDirty && !scenarioDirty && !massOverride) return;
    const warn = (event: BeforeUnloadEvent) => {
      event.preventDefault();
      event.returnValue = '';
    };
    window.addEventListener('beforeunload', warn);
    return () => window.removeEventListener('beforeunload', warn);
  }, [tuneDirty, scenarioDirty, massOverride]);
  const chooseSetup = async (id: string) => {
    if (
      tuneDirty &&
      !window.confirm('Change setup and discard the unsaved tune values?')
    )
      return;
    const selected = setups.find((item) => item.id === id);
    if (!selected) return;
    await task(async () => {
      const next = await getTuneSurface(selected.revision_id);
      setSetupId(id);
      setSurface(next);
      setTune(next.template);
      setTuneDetail(null);
    });
  };
  const acceptTune = async (detail: ExperimentDetail) => {
    if (detail.document.kind !== 'tunes') return;
    const next = await getTuneSurface(detail.document.setup_revision_id);
    setSurface(next);
    setTune(detail.document);
    setTuneDetail(detail);
    setSetupId(detail.item.setup_object_id ?? null);
  };
  const loadTune = (id: string) => {
    if (
      tuneDirty &&
      !window.confirm('Discard unsaved tune values and open this tune?')
    )
      return;
    void task(async () => acceptTune(await getExperiment(id)));
  };
  const loadScenario = (id: string) => {
    if (
      scenarioDirty &&
      !window.confirm('Discard unsaved scenario values and open this scenario?')
    )
      return;
    void task(async () => {
      const detail = await getExperiment(id);
      if (detail.document.kind === 'scenarios') {
        setScenarioDetail(detail);
        scenario.reset(detail.document);
      }
    });
  };
  const saveTune = async (asNew: boolean) => {
    if (!tune) return null;
    const detail = await saveExperiment(tune, tuneDetail, asNew);
    setTuneDetail(detail);
    if (detail.document.kind === 'tunes') setTune(detail.document);
    await refreshItems();
    return detail;
  };
  const saveScenario = async (asNew: boolean) => {
    if (!scenario.value) return;
    const detail = await saveExperiment(scenario.value, scenarioDetail, asNew);
    setScenarioDetail(detail);
    if (detail.document.kind === 'scenarios') scenario.reset(detail.document);
    await refreshItems();
  };
  const submit = async (mode: 'unsaved' | 'save' | 'new') => {
    if (!selection) return;
    await task(async () => {
      const saved =
        mode !== 'unsaved' ? await saveTune(mode === 'new') : tuneDetail;
      const body = {
        ...selection,
        tune_revision_id: saved?.item.revision_id,
        name: runName.trim() || 'Experiment',
        parent_run_id: params.get('source_run'),
      };
      const fingerprint = JSON.stringify(body);
      if (request.current.fingerprint !== fingerprint)
        request.current = { fingerprint, key: crypto.randomUUID() };
      const run = await submitExperiment({
        ...body,
        request_key: request.current.key,
      });
      await refreshActivity();
      leavingForRun.current = true;
      navigate(`/runs/${run.id}`);
    });
  };
  const check = () =>
    void task(async () => {
      if (!selection) return;
      const token = ++generation.current;
      const result = await previewExperiment(selection);
      if (token === generation.current) {
        setPreview(result);
        setPreviewKey(selectionKey);
      }
    });
  return (
    <Container size="lg">
      <Stack gap="lg">
        <Group justify="space-between">
          <div>
            <Title order={1}>Tune & run</Title>
            <Text c="dimmed">
              Build an experiment. Keep the setup, tune and road separate.
            </Text>
          </div>
          <Button component={Link} to="/library" variant="default">
            Physical library
          </Button>
        </Group>
        {error && (
          <Alert color="red" role="alert" title="Needs attention">
            {error}
          </Alert>
        )}
        {notice && (
          <Alert color="teal" role="status">
            {notice}
          </Alert>
        )}
        {busy && !metadata && <Loader aria-label="Loading experiments" />}
        {metadata && !setups.length && (
          <Alert title="Choose a vehicle setup first">
            Save a setup in the physical library, or ask an administrator to add
            the default sample catalog.
          </Alert>
        )}
        {metadata && (
          <QuantityValidationContext.Provider value={setInvalid}>
            <fieldset
              disabled={busy}
              inert={busy || undefined}
              style={{ border: 0, padding: 0, margin: 0, minWidth: 0 }}
            >
              <Stack gap="lg">
                <Paper withBorder p="lg">
                  <Stack>
                    <Select
                      label="Vehicle setup"
                      searchable
                      value={setupId}
                      disabled={busy}
                      data={setups.map((item) => ({
                        value: item.id,
                        label: `${item.name} · latest r${item.revision_number}${item.owned ? '' : ' · sample'}`,
                      }))}
                      onChange={(id) => id && void chooseSetup(id)}
                    />
                    {surface && (
                      <Group justify="space-between">
                        <Text size="sm">
                          Using {surface.setup_name}, revision{' '}
                          {surface.setup_revision_number}.
                        </Text>
                        {setupId &&
                          setups.find((item) => item.id === setupId)
                            ?.revision_id !== tune?.setup_revision_id && (
                            <Button
                              size="xs"
                              variant="light"
                              onClick={() => void chooseSetup(setupId)}
                            >
                              Start a tune on latest setup revision
                            </Button>
                          )}
                      </Group>
                    )}
                    <Checkbox
                      label="Override vehicle mass for this run only"
                      checked={massOverride}
                      disabled={busy}
                      onChange={(event) => {
                        const enabled = event.currentTarget.checked;
                        setMassOverride(enabled);
                        if (enabled && surface)
                          setMass(surface.default_vehicle_mass_kg);
                      }}
                    />
                    {massOverride && (
                      <QuantityInput
                        label="Run-only vehicle mass"
                        unit="kg"
                        scale={1}
                        min={0.001}
                        value={mass}
                        onChange={setMass}
                      />
                    )}
                  </Stack>
                </Paper>
                {tune && surface && (
                  <Paper withBorder p="lg">
                    <Stack gap="lg">
                      <RevisionToolbar
                        label="Tune"
                        document={tune}
                        detail={tuneDetail}
                        items={tunes}
                        busy={busy}
                        invalid={Boolean(invalid.size)}
                        onChange={(next) =>
                          next.kind === 'tunes' && setTune(next)
                        }
                        onLoad={loadTune}
                        onNew={() => {
                          if (
                            !tuneDirty ||
                            window.confirm('Discard unsaved tune values?')
                          ) {
                            setTuneDetail(null);
                            setTune(surface.template);
                          }
                        }}
                        onSave={(asNew) =>
                          void task(async () => {
                            await saveTune(asNew);
                            setNotice('Tune saved as an immutable revision.');
                          })
                        }
                        onRestored={(detail) =>
                          void task(async () => acceptTune(detail))
                        }
                        onRefresh={() =>
                          void refreshItems().catch((cause) =>
                            setError(message(cause)),
                          )
                        }
                      />
                      <TuneEditor
                        value={tune}
                        surface={surface}
                        onChange={setTune}
                      />
                      <Button
                        size="xs"
                        variant="subtle"
                        onClick={() => {
                          if (
                            window.confirm(
                              'Reset all tuning values to this pinned setup revision’s defaults?',
                            )
                          )
                            setTune({
                              ...tune,
                              values: surface.template.values,
                            });
                        }}
                      >
                        Reset values to setup defaults
                      </Button>
                    </Stack>
                  </Paper>
                )}
                {scenario.value && (
                  <Paper withBorder p="lg">
                    <Stack gap="lg">
                      <RevisionToolbar
                        label="Scenario"
                        document={scenario.value}
                        detail={scenarioDetail}
                        items={scenarios}
                        busy={busy}
                        invalid={Boolean(invalid.size) || !roadValid}
                        onChange={(next) =>
                          next.kind === 'scenarios' && scenario.change(next)
                        }
                        onLoad={loadScenario}
                        onNew={() => {
                          if (
                            !scenarioDirty ||
                            window.confirm('Discard unsaved scenario values?')
                          ) {
                            setScenarioDetail(null);
                            scenario.reset(metadata.scenario_template);
                          }
                        }}
                        onSave={(asNew) =>
                          void task(async () => {
                            await saveScenario(asNew);
                            setNotice(
                              'Scenario saved as an immutable revision.',
                            );
                          })
                        }
                        onRestored={(detail) => {
                          setScenarioDetail(detail);
                          if (detail.document.kind === 'scenarios')
                            scenario.reset(detail.document);
                        }}
                        onRefresh={() =>
                          void refreshItems().catch((cause) =>
                            setError(message(cause)),
                          )
                        }
                      />
                      <Group>
                        <Button
                          variant="default"
                          size="xs"
                          disabled={!scenario.canUndo || busy}
                          onClick={scenario.undo}
                        >
                          Undo scenario edit
                        </Button>
                        <Button
                          variant="default"
                          size="xs"
                          disabled={!scenario.canRedo || busy}
                          onClick={scenario.redo}
                        >
                          Redo scenario edit
                        </Button>
                      </Group>
                      <ScenarioEditor
                        value={scenario.value}
                        metadata={metadata}
                        onChange={scenario.change}
                        onRoadValidityChange={setRoadValid}
                      />
                    </Stack>
                  </Paper>
                )}
                <Paper withBorder p="lg">
                  <Stack>
                    <Group justify="space-between">
                      <Title order={2}>Run this experiment</Title>
                      <Badge variant="light">
                        One active run per workspace
                      </Badge>
                    </Group>
                    <TextInput
                      label="Run name"
                      value={runName}
                      maxLength={240}
                      onChange={(event) =>
                        setRunName(event.currentTarget.value)
                      }
                    />
                    <Text size="sm" c="dimmed">
                      Every option freezes the current scenario and run-only
                      overrides. Saving a tune does not save the scenario; use
                      its own Save button above. Runs continue even when this
                      page closes.
                    </Text>
                    {activity?.active && (
                      <Alert title="A simulation is already active">
                        <Text size="sm">
                          {activity.active.name} · {activity.active.status}
                        </Text>
                        <Button
                          component={Link}
                          to={`/runs/${activity.active.id}`}
                          variant="light"
                          size="xs"
                          mt="sm"
                        >
                          View or cancel active run
                        </Button>
                      </Alert>
                    )}
                    <Group>
                      <Button
                        variant="default"
                        disabled={!ready}
                        loading={busy}
                        onClick={check}
                      >
                        Check experiment
                      </Button>
                      <Button
                        disabled={!ready || Boolean(activity?.active)}
                        loading={busy}
                        onClick={() => void submit('unsaved')}
                      >
                        Run unsaved values
                      </Button>
                      <Button
                        variant="light"
                        disabled={
                          !ready ||
                          Boolean(activity?.active) ||
                          !tuneDetail?.item.owned ||
                          tuneDetail.item.archived
                        }
                        onClick={() => void submit('save')}
                      >
                        Save and Run
                      </Button>
                      <Button
                        variant="light"
                        disabled={!ready || Boolean(activity?.active)}
                        onClick={() => void submit('new')}
                      >
                        Save as New Tune and Run
                      </Button>
                    </Group>
                    {Boolean(invalid.size) && (
                      <Text c="red" size="sm">
                        Correct the highlighted numeric inputs before saving or
                        running.
                      </Text>
                    )}
                    <PhysicalStatus
                      validation={preview?.validation ?? null}
                      stale={previewKey !== selectionKey}
                    />
                  </Stack>
                </Paper>
              </Stack>
            </fieldset>
          </QuantityValidationContext.Provider>
        )}
        <Modal
          opened={blocker.state === 'blocked'}
          onClose={() => blocker.state === 'blocked' && blocker.reset()}
          title="Leave unsaved experiment?"
        >
          <Stack>
            <Text>
              Unsaved tune and scenario edits will be discarded. Already
              submitted runs keep their frozen inputs.
            </Text>
            <Group justify="flex-end">
              <Button
                variant="default"
                onClick={() => blocker.state === 'blocked' && blocker.reset()}
              >
                Keep editing
              </Button>
              <Button
                color="red"
                onClick={() => blocker.state === 'blocked' && blocker.proceed()}
              >
                Discard & leave
              </Button>
            </Group>
          </Stack>
        </Modal>
      </Stack>
    </Container>
  );
}
