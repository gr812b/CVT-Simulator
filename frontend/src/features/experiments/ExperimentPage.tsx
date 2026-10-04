import { useEffect, useRef, useState } from 'react';
import {
  Alert,
  Badge,
  Container,
  Divider,
  Grid,
  Group,
  Loader,
  Modal,
  Paper,
  Select,
  Stack,
  Stepper,
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
import { ActionButton as Button } from '@components/button/ActionButton';
import { QuantityValidationContext } from '@components/quantityInput/validation';
import { ComponentPicker } from '../physicalLibrary/ComponentPicker';
import { CvtEditor } from '../physicalLibrary/CvtEditor';
import { EngineEditor } from '../physicalLibrary/EngineEditor';
import { VehicleEditor } from '../physicalLibrary/VehicleEditor';
import { PhysicalStatus } from '../physicalLibrary/PhysicalStatus';
import {
  getPhysical,
  listPhysical,
  physicalMetadata,
  physicalTemplate,
  savePhysical,
  validatePhysical,
  type PhysicalDetail,
  type PhysicalDocument,
  type PhysicalField,
  type PhysicalItem,
} from '../physicalLibrary/api';
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
import { getFrozenInput } from '../results/api';
import { LoadCaseEditor } from './LoadCaseEditor';
import {
  PrimaryBoundaryEditor,
  type PrimaryBoundary,
} from './PrimaryBoundaryEditor';
import { RevisionToolbar } from './RevisionToolbar';
import { RoadPreview } from './RoadPreview';
import { ScenarioEditor } from './ScenarioEditor';
import { TuneEditor } from './TuneEditor';
import { useRunActivity } from './RunActivity';
import styles from './RunBuilder.module.css';

type Setup = Extract<PhysicalDocument, { kind: 'setups' }>;
const steps = [
  'Vehicle',
  'CVT & belt',
  'Primary boundary',
  'Load case',
  'Review & run',
];

export function ExperimentPage() {
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const { activity, refresh: refreshActivity } = useRunActivity();
  const [step, setStep] = useState(0);
  const [metadata, setMetadata] = useState<ExperimentMetadata | null>(null);
  const [fields, setFields] = useState<PhysicalField[]>([]);
  const [catalog, setCatalog] = useState<PhysicalItem[]>([]);
  const [setup, setSetup] = useState<Setup | null>(null);
  const [setupDetail, setSetupDetail] = useState<PhysicalDetail | null>(null);
  const [surface, setSurface] = useState<TuneSurface | null>(null);
  const [tune, setTune] = useState<Tune | null>(null);
  const [tuneDetail, setTuneDetail] = useState<ExperimentDetail | null>(null);
  const [tunes, setTunes] = useState<ExperimentItem[]>([]);
  const [loadCases, setLoadCases] = useState<ExperimentItem[]>([]);
  const [loadCase, setLoadCase] = useState<ExperimentDetail | null>(null);
  const [scenario, setScenario] = useState<Scenario | null>(null);
  const [primary, setPrimary] = useState<PrimaryBoundary>(null);
  const [loadEditor, setLoadEditor] = useState<{ id: string | null } | null>(
    null,
  );
  const [tuneOpen, setTuneOpen] = useState(false);
  const [busy, setBusy] = useState(true);
  const [componentBusy, setComponentBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [preview, setPreview] = useState<ExperimentPreview | null>(null);
  const [previewKey, setPreviewKey] = useState('');
  const [invalid, setInvalid] = useState(new Set<string>());
  const [runName, setRunName] = useState('New simulation');
  const [retry, setRetry] = useState(0);
  const request = useRef({ fingerprint: '', key: crypto.randomUUID() });
  const leaving = useRef(false);
  const working = busy || componentBusy;
  const setupDirty =
    !!setup && JSON.stringify(setup) !== JSON.stringify(setupDetail?.document);
  const tuneDirty =
    !!tune &&
    JSON.stringify(tune) !==
      JSON.stringify(tuneDetail?.document ?? surface?.template);
  const scenarioDirty =
    !!scenario &&
    JSON.stringify(scenario) !== JSON.stringify(loadCase?.document);
  const dirty =
    setupDirty || tuneDirty || scenarioDirty || !!primary || invalid.size > 0;
  const blocker = useBlocker(
    ({ currentLocation, nextLocation }) =>
      !leaving.current &&
      dirty &&
      currentLocation.pathname !== nextLocation.pathname,
  );
  useEffect(() => {
    if (!dirty) return;
    const warn = (event: BeforeUnloadEvent) => {
      event.preventDefault();
      event.returnValue = '';
    };
    window.addEventListener('beforeunload', warn);
    return () => window.removeEventListener('beforeunload', warn);
  }, [dirty]);
  const task = async (action: () => Promise<void>) => {
    setBusy(true);
    setError(null);
    try {
      await action();
    } catch (cause) {
      setError(message(cause));
    } finally {
      setBusy(false);
    }
  };
  const acceptLoadCase = (next: ExperimentDetail) => {
    if (next.document.kind !== 'scenarios') return;
    setLoadCase(next);
    setScenario(next.document);
    setPreview(null);
  };
  useEffect(() => {
    let disposed = false;
    setBusy(true);
    setError(null);
    void Promise.all([
      getExperimentMetadata(),
      physicalMetadata(),
      Promise.all(
        (['setups', 'engines', 'cvts', 'belts'] as const).map((kind) =>
          listPhysical(kind, 'all'),
        ),
      ),
      listExperiments('scenarios'),
      listExperiments('tunes'),
    ])
      .then(async ([meta, physical, groups, roads, savedTunes]) => {
        const items = groups.flat();
        const selected =
          groups[0].find((item) => item.id === params.get('setup')) ??
          groups[0][0];
        const road =
          roads.find((item) => item.id === params.get('scenario')) ??
          roads.find((item) => item.name === 'Flat road') ??
          roads[0];
        const [current, selectedRoad] = await Promise.all([
          selected ? getPhysical('setups', selected.id) : null,
          road ? getExperiment(road.id) : null,
        ]);
        const nextSurface = current
          ? await getTuneSurface(current.item.revision_id)
          : null;
        if (disposed) return;
        setMetadata(meta);
        setFields(physical.cvt_fields);
        setCatalog(items);
        setLoadCases(roads);
        setTunes(savedTunes);
        if (current?.document.kind === 'setups') {
          setSetupDetail(current);
          setSetup(current.document);
        }
        if (nextSurface) {
          setSurface(nextSurface);
          setTune(nextSurface.template);
        }
        if (selectedRoad) acceptLoadCase(selectedRoad);
        if (params.get('tune')) {
          const selectedTune = await getExperiment(params.get('tune')!);
          if (disposed) return;
          if (
            selectedTune.document.kind === 'tunes' &&
            selectedTune.item.setup_object_id
          ) {
            const revision = selectedTune.document.setup_revision_id;
            const [pinnedSetup, pinnedSurface] = await Promise.all([
              getPhysical(
                'setups',
                selectedTune.item.setup_object_id,
                revision,
              ),
              getTuneSurface(revision),
            ]);
            if (disposed) return;
            if (pinnedSetup.document.kind !== 'setups') return;
            setSetupDetail({
              ...pinnedSetup,
              item: { ...pinnedSetup.item, revision_id: revision },
            });
            setSetup(pinnedSetup.document);
            setSurface(pinnedSurface);
            setTuneDetail(selectedTune);
            setTune(selectedTune.document);
          }
        }
        if (params.get('source_run')) {
          const source = await getFrozenInput(params.get('source_run')!);
          if (disposed) return;
          // The backend validates which run inputs are representable by this editor.
          const override = source.run.provenance?.primary_boundary;
          if (override) setPrimary(override as PrimaryBoundary);
        }
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
  }, [params, retry]);
  const chooseSetup = (id: string) =>
    void task(async () => {
      if (
        dirty &&
        !window.confirm(
          'Replace the current working setup and tune with this saved setup?',
        )
      )
        return;
      const next = await getPhysical('setups', id);
      if (next.document.kind !== 'setups') return;
      const nextSurface = await getTuneSurface(next.item.revision_id);
      setSetupDetail(next);
      setSetup(next.document);
      setSurface(nextSurface);
      setTune(nextSurface.template);
      setTuneDetail(null);
      setPrimary(null);
      setPreview(null);
    });
  const newSetup = () =>
    void task(async () => {
      if (
        dirty &&
        !window.confirm(
          'Start a new setup and discard current unsaved changes?',
        )
      )
        return;
      const template = await physicalTemplate('setups');
      if (template.kind !== 'setups') return;
      setSetup({ ...template, name: 'My vehicle setup' });
      setSetupDetail(null);
      setSurface(null);
      setTune(null);
      setTuneDetail(null);
      setPrimary(null);
      setPreview(null);
      setStep(0);
    });
  const prepareSetup = async () => {
    if (!setup) throw new Error('Choose or create a vehicle setup.');
    let current = setupDetail;
    if (setupDirty || !current) {
      const validation = await validatePhysical(setup);
      if (!validation.validation.is_valid)
        throw new Error(
          validation.validation.findings
            .map((item) => item.message)
            .join(' ') || 'Check the vehicle and CVT inputs.',
        );
      const own = current?.item.owned;
      const saved = await savePhysical(
        setup,
        own ? current!.item.revision_id : null,
        own ? current!.item.id : undefined,
        'Saved from the run builder.',
      );
      current = saved.detail;
      if (current.document.kind === 'setups') setSetup(current.document);
      setSetupDetail(current);
      setCatalog((old) => [
        ...old.filter((item) => item.id !== current!.item.id),
        current!.item,
      ]);
    }
    let nextSurface = surface;
    let nextTune = tune;
    if (
      !nextSurface ||
      nextSurface.template.setup_revision_id !== current.item.revision_id
    ) {
      nextSurface = await getTuneSurface(current.item.revision_id);
      nextTune = nextSurface.template;
      setSurface(nextSurface);
      setTune(nextTune);
      setTuneDetail(null);
    }
    if (!nextTune) throw new Error('The tuning surface is unavailable.');
    return { detail: current, tune: nextTune };
  };
  const selection: ExperimentSelection | null =
    setupDetail && tune && scenario
      ? {
          setup_revision_id: setupDetail.item.revision_id,
          tune_revision_id: tuneDetail?.item.revision_id ?? null,
          tune_values: tune.values,
          scenario_revision_id: loadCase?.item.revision_id ?? null,
          scenario,
          primary_boundary: primary ?? null,
        }
      : null;
  const selectionKey = JSON.stringify(selection);
  const go = (next: number) =>
    void task(async () => {
      if (invalid.size)
        throw new Error(
          'Correct the highlighted numeric inputs before changing steps.',
        );
      if (!setup?.name.trim())
        throw new Error('Give this vehicle setup a name.');
      if (next >= 3) {
        const prepared = await prepareSetup();
        if (next === 4) {
          if (!scenario || !loadCase)
            throw new Error('Choose or create a saved load case.');
          const body: ExperimentSelection = {
            setup_revision_id: prepared.detail.item.revision_id,
            tune_revision_id:
              prepared.tune === tune
                ? (tuneDetail?.item.revision_id ?? null)
                : null,
            tune_values: prepared.tune.values,
            scenario_revision_id: loadCase.item.revision_id,
            scenario,
            primary_boundary: primary ?? null,
          };
          setPreview(await previewExperiment(body));
          setPreviewKey(JSON.stringify(body));
        }
      }
      setStep(next);
    });
  const submit = () =>
    void task(async () => {
      if (!selection) return;
      const body = {
        ...selection,
        name: runName.trim(),
        parent_run_id: params.get('source_run'),
      };
      const fingerprint = JSON.stringify(body);
      if (request.current.fingerprint !== fingerprint)
        request.current = { fingerprint, key: crypto.randomUUID() };
      const run = await submitExperiment({
        ...body,
        request_key: request.current.key,
      });
      leaving.current = true;
      await refreshActivity();
      navigate(`/runs/${run.id}`);
    });
  const patchSetup = (data: Partial<Setup['data']>) => {
    if (setup) setSetup({ ...setup, data: { ...setup.data, ...data } });
  };
  const reason = working
    ? 'Please wait for the current action.'
    : invalid.size
      ? 'Correct the highlighted inputs.'
      : !runName.trim()
        ? 'Enter a run name.'
        : activity?.active
          ? 'You already have a queued or running simulation. Wait for it to finish or cancel it from Activity.'
          : setupDirty || !preview || previewKey !== selectionKey
            ? 'Review the current inputs before running.'
            : !preview.validation.is_valid
              ? 'Resolve the input errors before running.'
              : undefined;
  const primaryLabel = !primary
    ? (setup?.data.engine.name ?? 'Choose an engine')
    : primary.kind === 'fixed_shaft'
      ? `${primary.external_torque_Nm} N·m applied torque`
      : 'Speed-profile tracking';
  return (
    <Container size="xl" py="lg">
      <Stack gap="lg">
        <Group justify="space-between">
          <div>
            <Title order={1}>Build a run</Title>
            <Text c="dimmed">
              Choose reusable components and a load case, then review the
              complete simulation.
            </Text>
          </div>
          <Badge variant="light">Free · public saves and runs</Badge>
        </Group>
        {error && (
          <Alert color="red" title="Needs attention" role="alert">
            {error}
            {!metadata && (
              <Button variant="subtle" onClick={() => setRetry((x) => x + 1)}>
                Try again
              </Button>
            )}
          </Alert>
        )}
        {!metadata ? (
          busy && <Loader aria-label="Loading run builder" />
        ) : (
          <QuantityValidationContext.Provider value={setInvalid}>
            <Stepper
              active={step}
              onStepClick={(next) => {
                if (!working) go(next);
              }}
              size="sm"
              className={styles.steps}
            >
              {steps.map((label) => (
                <Stepper.Step key={label} label={label} />
              ))}
            </Stepper>
            <Grid gap="lg" align="start">
              <Grid.Col span={{ base: 12, md: 8 }}>
                <Paper withBorder p={{ base: 'md', sm: 'lg' }}>
                  <Stack gap="lg">
                    <Title order={2}>{steps[step]}</Title>
                    <fieldset
                      disabled={working}
                      style={{ border: 0, padding: 0, margin: 0, minWidth: 0 }}
                    >
                      <Stack gap="lg">
                        {step === 0 && (
                          <>
                            <Group align="end">
                              <Select
                                style={{ flex: '1 1 240px' }}
                                label="Saved vehicle setup"
                                searchable
                                allowDeselect={false}
                                value={setupDetail?.item.id ?? null}
                                placeholder="Choose a saved setup"
                                data={catalog
                                  .filter((item) => item.kind === 'setups')
                                  .map((item) => ({
                                    value: item.id,
                                    label: `${item.name} · r${item.revision_number}${item.owned ? ' · mine' : ''}`,
                                  }))}
                                onChange={(id) => id && chooseSetup(id)}
                              />
                              <Button variant="default" onClick={newSetup}>
                                New vehicle setup
                              </Button>
                            </Group>
                            {setup && (
                              <>
                                <TextInput
                                  label="Vehicle setup name"
                                  required
                                  maxLength={240}
                                  value={setup.name}
                                  onChange={(e) =>
                                    setSetup({
                                      ...setup,
                                      name: e.currentTarget.value,
                                    })
                                  }
                                />
                                <VehicleEditor
                                  value={setup.data.vehicle}
                                  onChange={(vehicle) =>
                                    patchSetup({ vehicle })
                                  }
                                />
                                <Text size="sm" c="dimmed">
                                  Changing another author's setup saves a copy
                                  in your library. Your own setups receive a new
                                  revision.
                                </Text>
                              </>
                            )}
                          </>
                        )}
                        {setup && step === 1 && (
                          <>
                            <ComponentPicker
                              kind="cvts"
                              value={setup.data.cvt}
                              items={catalog.filter(
                                (item) => item.kind === 'cvts',
                              )}
                              onChange={(cvt) => patchSetup({ cvt })}
                              onLoadingChange={setComponentBusy}
                            />
                            <CvtEditor
                              value={setup.data.cvt.data}
                              fields={fields}
                              belts={catalog.filter(
                                (item) => item.kind === 'belts',
                              )}
                              onChange={(data) =>
                                patchSetup({ cvt: { ...setup.data.cvt, data } })
                              }
                              onLoadingChange={setComponentBusy}
                            />
                            <Button
                              variant="light"
                              onClick={() =>
                                void task(async () => {
                                  await prepareSetup();
                                  setTuneOpen(true);
                                })
                              }
                            >
                              Adjust CVT tune
                            </Button>
                          </>
                        )}
                        {setup && step === 2 && (
                          <PrimaryBoundaryEditor
                            value={primary}
                            onChange={setPrimary}
                          >
                            <ComponentPicker
                              kind="engines"
                              value={setup.data.engine}
                              items={catalog.filter(
                                (item) => item.kind === 'engines',
                              )}
                              onChange={(engine) => patchSetup({ engine })}
                              onLoadingChange={setComponentBusy}
                            />
                            <EngineEditor
                              value={setup.data.engine.data}
                              onChange={(data) =>
                                patchSetup({
                                  engine: { ...setup.data.engine, data },
                                })
                              }
                            />
                          </PrimaryBoundaryEditor>
                        )}
                        {step === 3 && (
                          <>
                            <Group align="end">
                              <Select
                                style={{ flex: '1 1 240px' }}
                                label="Saved load case"
                                searchable
                                allowDeselect={false}
                                value={loadCase?.item.id ?? null}
                                placeholder="Choose a road or load case"
                                data={loadCases
                                  .filter((item) => !item.archived)
                                  .map((item) => ({
                                    value: item.id,
                                    label: `${item.name} · r${item.revision_number}${item.sample ? ' · default' : item.owned ? ' · mine' : ''}`,
                                  }))}
                                onChange={(id) =>
                                  id &&
                                  void task(async () =>
                                    acceptLoadCase(await getExperiment(id)),
                                  )
                                }
                              />
                              <Button
                                variant="default"
                                onClick={() => setLoadEditor({ id: null })}
                              >
                                New load case
                              </Button>
                            </Group>
                            {loadCase && scenario && (
                              <>
                                <Group justify="space-between">
                                  <Text fw={600}>{loadCase.item.name}</Text>
                                  <Button
                                    variant="light"
                                    onClick={() =>
                                      setLoadEditor({ id: loadCase.item.id })
                                    }
                                  >
                                    {loadCase.item.owned
                                      ? 'Edit load case'
                                      : 'Customize load case'}
                                  </Button>
                                </Group>
                                {loadCase.item.description && (
                                  <Text size="sm" c="dimmed">
                                    {loadCase.item.description}
                                  </Text>
                                )}
                                <RoadPreview road={scenario.road} />
                                <Button
                                  component={Link}
                                  to={`/catalog/load-cases/${loadCase.item.id}`}
                                  target="_blank"
                                  rel="noopener noreferrer"
                                  variant="subtle"
                                >
                                  Open full load-case details
                                </Button>
                              </>
                            )}
                          </>
                        )}
                        {step === 4 && scenario && (
                          <>
                            <TextInput
                              label="Run name"
                              required
                              maxLength={240}
                              value={runName}
                              onChange={(e) =>
                                setRunName(e.currentTarget.value)
                              }
                            />
                            <ScenarioEditor
                              showRoad={false}
                              value={scenario}
                              metadata={metadata}
                              onChange={setScenario}
                              onRoadValidityChange={() => {}}
                            />
                            {scenarioDirty && (
                              <Text size="sm" c="dimmed">
                                These run settings override the selected load
                                case for this run. Its saved revision remains
                                unchanged.
                              </Text>
                            )}
                            <Button variant="default" onClick={() => go(4)}>
                              Refresh input check
                            </Button>
                            <PhysicalStatus
                              validation={preview?.validation ?? null}
                              stale={previewKey !== selectionKey || setupDirty}
                            />
                            <Button
                              size="md"
                              disabledReason={reason}
                              onClick={submit}
                            >
                              Run simulation
                            </Button>
                            {activity?.active && (
                              <Alert title="One active simulation at a time">
                                <Text size="sm">
                                  {activity.active.name} is{' '}
                                  {activity.active.status}.
                                </Text>
                                <Button
                                  component={Link}
                                  to={`/runs/${activity.active.id}`}
                                  variant="subtle"
                                >
                                  View active run
                                </Button>
                              </Alert>
                            )}
                          </>
                        )}
                      </Stack>
                    </fieldset>
                    <Divider />
                    <Group justify="space-between">
                      <Button
                        variant="default"
                        disabledReason={
                          step === 0
                            ? 'This is the first step.'
                            : working
                              ? 'Please wait for the current action.'
                              : undefined
                        }
                        onClick={() => go(step - 1)}
                      >
                        Back
                      </Button>
                      {step < 4 && (
                        <Button
                          loading={busy}
                          disabledReason={
                            componentBusy
                              ? 'Wait for the selected component to load.'
                              : invalid.size
                                ? 'Correct the highlighted inputs before continuing.'
                                : !setup
                                  ? 'Choose or create a vehicle setup.'
                                  : undefined
                          }
                          onClick={() => go(step + 1)}
                        >
                          {step === 2 && setupDirty
                            ? 'Save setup & choose load case'
                            : step === 3
                              ? 'Review simulation'
                              : 'Next'}
                        </Button>
                      )}
                    </Group>
                  </Stack>
                </Paper>
              </Grid.Col>
              <Grid.Col
                span={{ base: 12, md: 4 }}
                className={styles.summaryColumn}
              >
                <Paper withBorder p="lg" className={styles.summary}>
                  <Stack gap="sm">
                    <Title order={2} size="h3">
                      Your simulation
                    </Title>
                    {[
                      {
                        label: 'Vehicle',
                        value: setup
                          ? `${setup.name} · ${setup.data.vehicle.mass_kg.toFixed(1)} kg`
                          : 'Choose a vehicle',
                        step: 0,
                      },
                      {
                        label: 'CVT & belt',
                        value: setup
                          ? `${setup.data.cvt.name} / ${setup.data.cvt.data.belt.name}`
                          : 'Choose a CVT',
                        step: 1,
                      },
                      { label: 'Primary', value: primaryLabel, step: 2 },
                      {
                        label: 'Load case',
                        value: loadCase?.item.name ?? 'Choose a load case',
                        step: 3,
                      },
                    ].map((item) => (
                      <div key={item.label}>
                        <Group justify="space-between">
                          <Text size="xs" c="dimmed" tt="uppercase">
                            {item.label}
                          </Text>
                          <Button
                            size="compact-xs"
                            variant="subtle"
                            disabled={working}
                            onClick={() => go(item.step)}
                          >
                            Edit {item.label.toLowerCase()}
                          </Button>
                        </Group>
                        <Text size="sm" style={{ overflowWrap: 'anywhere' }}>
                          {item.value}
                        </Text>
                      </div>
                    ))}
                    <Divider />
                    <Text size="sm">
                      {scenario?.duration_s ?? '—'} s simulation ·{' '}
                      {tuneDetail?.item.name ??
                        (tuneDirty ? 'Custom tune values' : 'Setup tuning')}
                    </Text>
                    <Text size="xs" c="dimmed">
                      The secondary load is always the vehicle and selected
                      road. Saved configurations and run results are public.
                      Each run keeps its exact input revisions.
                    </Text>
                  </Stack>
                </Paper>
              </Grid.Col>
            </Grid>
            {loadEditor && (
              <LoadCaseEditor
                key={loadEditor.id ?? 'new'}
                id={loadEditor.id}
                onClose={() => setLoadEditor(null)}
                onSaved={(next) => {
                  acceptLoadCase(next);
                  setLoadCases((old) => [
                    ...old.filter((item) => item.id !== next.item.id),
                    next.item,
                  ]);
                  setLoadEditor(null);
                }}
              />
            )}
            <Modal
              opened={tuneOpen}
              onClose={() => setTuneOpen(false)}
              title="CVT tune"
              size="xl"
            >
              {tune && surface && (
                <Stack>
                  <RevisionToolbar
                    label="Tune"
                    document={tune}
                    detail={tuneDetail}
                    items={tunes}
                    busy={busy}
                    invalid={Boolean(invalid.size)}
                    onChange={(next) => next.kind === 'tunes' && setTune(next)}
                    onNew={() => {
                      setTune(surface.template);
                      setTuneDetail(null);
                    }}
                    onLoad={(id) =>
                      void task(async () => {
                        const next = await getExperiment(id);
                        if (
                          next.document.kind !== 'tunes' ||
                          !next.item.setup_object_id
                        )
                          return;
                        if (
                          !window.confirm(
                            'Load this tune and its pinned vehicle setup?',
                          )
                        )
                          return;
                        const current = await getPhysical(
                          'setups',
                          next.item.setup_object_id,
                          next.document.setup_revision_id,
                        );
                        if (current.document.kind !== 'setups') return;
                        setSetupDetail({
                          ...current,
                          item: {
                            ...current.item,
                            revision_id: next.document.setup_revision_id,
                          },
                        });
                        setSetup(current.document);
                        setSurface(
                          await getTuneSurface(next.document.setup_revision_id),
                        );
                        setTune(next.document);
                        setTuneDetail(next);
                      })
                    }
                    onSave={(asNew) =>
                      void task(async () => {
                        const next = await saveExperiment(
                          tune,
                          tuneDetail,
                          asNew,
                        );
                        setTuneDetail(next);
                        if (next.document.kind === 'tunes')
                          setTune(next.document);
                        setTunes(await listExperiments('tunes'));
                      })
                    }
                    onRestored={(next) => {
                      setTuneDetail(next);
                      if (next.document.kind === 'tunes')
                        setTune(next.document);
                    }}
                    onRefresh={() =>
                      void task(async () =>
                        setTunes(await listExperiments('tunes')),
                      )
                    }
                  />
                  <TuneEditor
                    value={tune}
                    surface={surface}
                    onChange={setTune}
                  />
                  <Button
                    disabledReason={
                      invalid.size
                        ? 'Correct the highlighted tuning inputs.'
                        : undefined
                    }
                    onClick={() => setTuneOpen(false)}
                  >
                    Use these tune values
                  </Button>
                </Stack>
              )}
            </Modal>
          </QuantityValidationContext.Provider>
        )}
        <Modal
          opened={blocker.state === 'blocked'}
          onClose={() => blocker.state === 'blocked' && blocker.reset()}
          title="Leave unsaved run setup?"
        >
          <Stack>
            <Text>
              Unsaved working changes will be discarded. Saved configurations
              and submitted runs remain available.
            </Text>
            <Group>
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
