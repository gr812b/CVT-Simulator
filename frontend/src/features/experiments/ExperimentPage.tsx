import { EditorDisclosure } from '@components/form/EditorDisclosure';
import { FormError } from '@components/form/FormError';
import { libraryOptions } from '../physicalLibrary/libraryOptions';
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
import { QuantityInput } from '@components/quantityInput/QuantityInput';
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
  type PhysicalSelection,
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
import { getRunExperiment } from '../results/api';
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
  'Tune',
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
  const [setupDetail, setSetupDetail] = useState<PhysicalSelection | null>(null);
  const [surface, setSurface] = useState<TuneSurface | null>(null);
  const [tune, setTune] = useState<Tune | null>(null);
  const [tuneDetail, setTuneDetail] = useState<ExperimentDetail | null>(null);
  const [tunes, setTunes] = useState<ExperimentItem[]>([]);
  const [loadCases, setLoadCases] = useState<ExperimentItem[]>([]);
  const [loadCase, setLoadCase] = useState<ExperimentDetail | null>(null);
  const [scenario, setScenario] = useState<Scenario | null>(null);
  const [primary, setPrimary] = useState<PrimaryBoundary>(null);
  const [vehicleMassOverride, setVehicleMassOverride] = useState<number | null>(null);
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
  const [runName, setRunName] = useState('');
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
    setupDirty || tuneDirty || scenarioDirty || !!primary || vehicleMassOverride !== null || invalid.size > 0;
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
      params.get('source_run') ? getRunExperiment(params.get('source_run')!) : null,
    ])
      .then(async ([meta, physical, groups, roads, savedTunes, source]) => {
        if (disposed) return;
        const items = groups.flat();
        setMetadata(meta);
        setFields(physical.cvt_fields);
        setCatalog(items);
        setLoadCases(roads);
        setTunes(savedTunes);
        if (source) {
          if (source.setup.document.kind !== 'setups')
            throw new Error('This run has no vehicle setup for the builder.');
          setSetupDetail(source.setup);
          setSetup(source.setup.document);
          setCatalog([
            ...items.filter(item => item.id !== source.setup.item.id),
            source.setup.item,
          ]);
          setSurface(source.surface);
          setTuneDetail(source.tune);
          if (source.tune) {
            const selectedTune = source.tune;
            setTunes([
              ...savedTunes.filter(item => item.id !== selectedTune.item.id),
              selectedTune.item,
            ]);
          }
          const savedTune = source.tune?.document.kind === 'tunes'
            ? source.tune.document : source.surface.template;
          setTune({
            ...savedTune,
            values: source.selection.tune_values ?? savedTune.values,
          });
          setLoadCase(source.load_case);
          setScenario(source.selection.scenario ?? null);
          setPrimary(source.selection.primary_boundary ?? null);
          setVehicleMassOverride(source.selection.vehicle_mass_kg ?? null);
          if (source.load_case) {
            const selectedRoad = source.load_case;
            setLoadCases([
              ...roads.filter(item => item.id !== selectedRoad.item.id),
              selectedRoad.item,
            ]);
          }
          return;
        }
        setVehicleMassOverride(null);
        const selected =
          groups[0].find((item) => item.id === params.get('setup'));
        const road =
          roads.find((item) => item.id === params.get('scenario')) ??
          roads.find(
            (item) =>
              item.sample && item.name.toLowerCase().includes('flat road'),
          ) ??
          roads[0];
        const [current, selectedRoad] = await Promise.all([
          selected ? getPhysical('setups', selected.id) : null,
          road ? getExperiment(road.id) : null,
        ]);
        const nextSurface = current
          ? await getTuneSurface(current.item.revision_id)
          : null;
        if (disposed) return;
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
      const selected = catalog.find(item => item.kind === 'setups' && item.id === id);
      const next = await getPhysical('setups', id, selected?.revision_id);
      if (next.document.kind !== 'setups') return;
      const nextSurface = await getTuneSurface(next.item.revision_id);
      setSetupDetail(next);
      setSetup(next.document);
      setSurface(nextSurface);
      setTune(nextSurface.template);
      setTuneDetail(null);
      setPrimary(null);
      setVehicleMassOverride(null);
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
      setSetup({ ...template, name: '' });
      setSetupDetail(null);
      setSurface(null);
      setTune(null);
      setTuneDetail(null);
      setPrimary(null);
      setVehicleMassOverride(null);
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
      const previousSurface = nextSurface;
      nextSurface = await getTuneSurface(current.item.revision_id);
      if (previousSurface?.cvt_revision_id !== nextSurface.cvt_revision_id) {
        nextTune = nextSurface.template;
        setTuneDetail(null);
      }
      setSurface(nextSurface);
      setTune(nextTune);
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
        vehicle_mass_kg: vehicleMassOverride,
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
      if (next >= 2) {
        const prepared = await prepareSetup();
        if (next === 5) {
          if (!scenario || (!loadCase && !params.get('source_run')))
            throw new Error('Choose or create a saved load case.');
          const body: ExperimentSelection = {
            setup_revision_id: prepared.detail.item.revision_id,
            tune_revision_id:
              prepared.tune === tune
                ? (tuneDetail?.item.revision_id ?? null)
                : null,
            tune_values: prepared.tune.values,
            scenario_revision_id: loadCase?.item.revision_id ?? null,
            scenario,
            primary_boundary: primary ?? null,
            vehicle_mass_kg: vehicleMassOverride,
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
          <FormError title="Needs attention">
            {error}
            {!metadata && (
              <Button variant="subtle" onClick={() => setRetry((x) => x + 1)}>
                Try again
              </Button>
            )}
          </FormError>
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
                                data={libraryOptions(
                                  catalog.filter(
                                    (item) => item.kind === 'setups',
                                  ),
                                  (item) => item.id,
                                )}
                                onChange={(id) => id && chooseSetup(id)}
                              />
                              <Button variant="default" onClick={newSetup}>
                                New vehicle setup
                              </Button>
                            </Group>
                            {setup && (
                              <>
                                <EditorDisclosure key={setupDetail?.item.id ?? 'new'} title="Vehicle" initiallyOpen={!setupDetail}
                                  summary={`${setup.name || 'New vehicle'} · ${(vehicleMassOverride ?? setup.data.vehicle.mass_kg).toFixed(1)} kg`}>
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

                                </EditorDisclosure>
                                {vehicleMassOverride !== null && (
                                  <Paper withBorder p="md">
                                    <Stack gap="sm">
                                      <QuantityInput
                                        label="Run-only vehicle mass" unit="kg" scale={1} min={0.001}
                                        value={vehicleMassOverride} onChange={setVehicleMassOverride}
                                      />
                                      <Text size="sm" c="dimmed">
                                        This run used a mass override. The saved vehicle stays unchanged.
                                      </Text>
                                      <Button variant="subtle" onClick={() => setVehicleMassOverride(null)}>
                                        Use saved vehicle mass
                                      </Button>
                                    </Stack>
                                  </Paper>
                                )}
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
                            <EditorDisclosure key={setup.data.cvt.revision_id ?? 'new'} title="CVT" initiallyOpen={!setup.data.cvt.revision_id}
                              summary={`${setup.data.cvt.name} · ${setup.data.cvt.data.belt.name}`}>
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
                            </EditorDisclosure>
                          </>
                        )}
                        {setup && step === 2 && surface && tune && <Stack>
                          <Select label="CVT tune" searchable allowDeselect={false}
                            value={tuneDetail?.item.id ?? 'default'}
                            data={[{ group: 'Selected CVT', items: [{ value: 'default', label: 'Use CVT default settings' }] },
                            ...libraryOptions(tunes.filter(item => item.cvt_revision_id === surface.cvt_revision_id && (!item.archived || item.id === tuneDetail?.item.id)), item => item.id)]}
                            onChange={id => void task(async () => {
                              if (id === 'default') { setTune(surface.template); setTuneDetail(null); return; }
                              if (!id) return;
                              const next = await getExperiment(id, tunes.find(item => item.id === id)?.revision_id);
                              if (next.document.kind === 'tunes') { setTune(next.document); setTuneDetail(next); }
                            })} />
                          <Paper withBorder p="md"><Stack gap="xs">
                            <Text fw={600}>{tuneDetail?.item.name ?? 'CVT default settings'}</Text>
                            <Text size="sm" c="dimmed">{tuneDetail?.item.description || 'The saved CVT’s weights, springs and ramp settings.'}</Text>
                            <Button variant="light" onClick={() => { if (!tuneDetail) setTune({ ...tune, name: '' }); setTuneOpen(true); }}>Adjust tune</Button>
                          </Stack></Paper>
                        </Stack>}
                        {setup && step === 3 && (
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
                            <EditorDisclosure key={setup.data.engine.revision_id ?? 'new'} title="Engine" initiallyOpen={!setup.data.engine.revision_id}
                              summary={`${setup.data.engine.name} · full-open-throttle torque curve`}>
                              <EngineEditor
                                value={setup.data.engine.data}
                                onChange={(data) =>
                                  patchSetup({
                                    engine: { ...setup.data.engine, data },
                                  })
                                }
                              />
                            </EditorDisclosure>
                          </PrimaryBoundaryEditor>
                        )}
                        {step === 4 && (
                          <>
                            <Group align="end">
                              <Select
                                style={{ flex: '1 1 240px' }}
                                label="Saved load case"
                                searchable
                                allowDeselect={false}
                                value={loadCase?.item.id ?? null}
                                placeholder="Choose a road or load case"
                                data={libraryOptions(
                                  loadCases.filter((item) => !item.archived || item.id === loadCase?.item.id),
                                  (item) => item.id,
                                )}
                                onChange={(id) =>
                                  id &&
                                  void task(async () =>
                                    acceptLoadCase(await getExperiment(id, loadCases.find(item => item.id === id)?.revision_id)),
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
                            {!loadCase && scenario && params.get('source_run') && (
                              <Stack gap="sm">
                                <Text fw={600}>{scenario.name} · run-only load case</Text>
                                <Text size="sm" c="dimmed">
                                  These road settings will be reused for this run without creating a library item.
                                </Text>
                                <RoadPreview road={scenario.road} />
                              </Stack>
                            )}
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
                        {step === 5 && scenario && (
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
                              onRoadValidityChange={() => { }}
                            />
                            {scenarioDirty && (
                              <Text size="sm" c="dimmed">
                                These run settings override the selected load
                                case for this run. Its saved configuration
                                remains unchanged.
                              </Text>
                            )}
                            <Button variant="default" onClick={() => go(5)}>
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
                      {step < 5 && (
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
                          {step === 3 && setupDirty
                            ? 'Save setup & choose load case'
                            : step === 4
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
                          ? `${setup.name} · ${(vehicleMassOverride ?? setup.data.vehicle.mass_kg).toFixed(1)} kg`
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
                      { label: 'Tune', value: tuneDetail?.item.name ?? (tuneDirty ? 'Custom tune' : 'CVT default'), step: 2 },
                      { label: 'Primary', value: primaryLabel, step: 3 },
                      {
                        label: 'Load case',
                        value: loadCase?.item.name ?? scenario?.name ?? 'Choose a load case',
                        step: 4,
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
                            Change {item.label.toLowerCase()}
                          </Button>
                        </Group>
                        <Text size="sm" style={{ overflowWrap: 'anywhere' }}>
                          {item.value}
                        </Text>
                      </div>
                    ))}
                    <Divider />
                    <Text size="sm">
                      {scenario?.stops?.mode === 'timed' ? 'Timed run' : 'Run to course finish'} · up to {scenario?.duration_s ?? '—'} s ·{' '}
                      {tuneDetail?.item.name ??
                        (tuneDirty ? 'Custom tune values' : 'Setup tuning')}
                    </Text>
                    <Text size="xs" c="dimmed">
                      The secondary load is always the vehicle and selected
                      road. Saved configurations and run results are public.
                      Each run keeps a snapshot of its inputs.
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
                    items={tunes.filter(
                      (item) =>
                        item.cvt_revision_id === surface.cvt_revision_id,
                    )}
                    busy={busy}
                    invalid={Boolean(invalid.size)}
                    onChange={(next) => next.kind === 'tunes' && setTune(next)}
                    onNew={() => {
                      setTune({ ...surface.template, name: '' });
                      setTuneDetail(null);
                    }}
                    onLoad={(id) =>
                      void task(async () => {
                        const next = await getExperiment(id, tunes.find(item => item.id === id)?.revision_id);
                        if (
                          next.document.kind !== 'tunes' ||
                          !next.item.setup_object_id
                        )
                          return;
                        if (
                          next.item.cvt_revision_id !== surface.cvt_revision_id
                        )
                          throw new Error(
                            'Choose a tune for this CVT version.',
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
