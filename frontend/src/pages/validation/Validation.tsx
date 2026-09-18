import { useEffect, useMemo, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { LoadingOverlay } from '@components/loadingOverlay/LoadingOverlay';
import { MeasurementUncertaintyModal } from '@components/validation/MeasurementUncertaintyModal';
import { SetupEditorModal } from '@components/validation/SetupEditorModal';
import { ValidationTraceChart } from '@components/validation/ValidationTraceChart';
import { useLoading } from '@contexts/LoadingContext';
import {
  DEMO_ACCOUNT_ID,
  getSimulationResult,
  getValidationWorkspace,
  listValidationRuns,
  saveValidationRun,
  saveValidationWorkspace,
  submitValidationSimulationRun,
  waitForSimulationRun,
  type CompletedSimulationRun,
  type SimulationCaseDocument,
  type ValidationRunSummary,
  type ValidationWorkspace,
} from '@api/client';
import { reportAxisTimes, reportColumn } from '@utils/reportTable';
import {
  croppedIndices,
  errorMetrics,
  interpolate,
  measurementUncertaintySeries,
  nearestIndex,
  parseDynoCsv,
  RAD_PER_S_TO_RPM,
  resampleLinear,
  rpmToRadPerS,
  summarizeUncertainty,
} from './data';
import type {
  ChannelConfig,
  CropWindow,
  MeasurementMetadata,
  ParsedDynoData,
  ShaftValidationMode,
  SignalMetric,
  ValidationWorkflowDefaults,
} from './types';
import styles from './Validation.module.scss';

type SetupSection = 'primary' | 'cvt' | 'secondary';
type Shaft = 'primary' | 'secondary';
type JsonObject = Record<string, unknown>;

const DEFAULT_MANUAL_STATE = {
  primaryAngularSpeedRadPerS: 0,
  secondaryAngularSpeedRadPerS: 0,
  beltSpeedMPerS: 0,
  shiftPositionM: 0,
  shiftSpeedMPerS: 0,
};

const DEFAULT_REPLAY_GAIN_NM_S_PER_RAD = 400;
const DEFAULT_VALIDATION_INTEGRATOR = {
  relativeTolerance: 1e-4,
  absoluteTolerance: 1e-7,
  maxStepS: 0.05,
};

const VALIDATION_MINIMUM_TRANSITIONS = 60;
const VALIDATION_TRANSITIONS_PER_SECOND = 25;

function validationTransitionBudget(durationS: number): number {
  if (!(durationS > 0) || !Number.isFinite(durationS)) {
    return VALIDATION_MINIMUM_TRANSITIONS;
  }
  return Math.max(
    VALIDATION_MINIMUM_TRANSITIONS,
    Math.ceil(VALIDATION_TRANSITIONS_PER_SECOND * durationS),
  );
}

function deepClone<T>(value: T): T {
  return JSON.parse(JSON.stringify(value)) as T;
}

function normalizeMode(mode: ValidationWorkflowDefaults['primaryMode']): ShaftValidationMode {
  return mode === 'replay_measured_speed' || mode === 'track_measured_speed'
    ? 'replay_measured_speed'
    : 'physical';
}

function defaultRpmUncertainty(
  saved: ChannelConfig['uncertainty'] | undefined,
): ChannelConfig['uncertainty'] {
  return {
    status: 'pending',
    model: 'rpm_tooth_timing',
    unit: 'rpm',
    replaySampleIntervalS: 0.01,
    ...saved,
  };
}

function defaultChannels(data: ParsedDynoData, workflow: ValidationWorkflowDefaults): ChannelConfig[] {
  return Object.keys(data.columns)
    .filter((key) => key !== 'timestamp_ms' && !/^time(_s)?$/i.test(key))
    .map((key) => {
      if (key === 'primary_rpm') return {
        key,
        label: 'Primary RPM',
        unit: 'rpm',
        enabled: true,
        role: 'comparison' as const,
        mapping: 'primary_speed' as const,
        initializeState: true,
        uncertainty: defaultRpmUncertainty(workflow.rpmMeasurementDefaults?.primary),
      };
      if (key === 'secondary_rpm') return {
        key,
        label: 'Secondary RPM',
        unit: 'rpm',
        enabled: true,
        role: 'comparison' as const,
        mapping: 'secondary_speed' as const,
        initializeState: true,
        uncertainty: defaultRpmUncertainty(workflow.rpmMeasurementDefaults?.secondary),
      };
      if (key === 'shift_position') return {
        key,
        label: 'Shift position',
        unit: 'raw',
        enabled: false,
        role: 'unused' as const,
        mapping: 'shift_position' as const,
        initializeState: false,
        uncertainty: { status: 'pending' as const, model: 'absolute' as const, unit: 'raw' },
      };
      if (key === 'primary_power_kw') return {
        key,
        label: 'Primary power',
        unit: 'kW',
        enabled: false,
        role: 'unused' as const,
        mapping: 'none' as const,
        initializeState: false,
        uncertainty: { status: 'pending' as const, model: 'absolute' as const, unit: 'kW' },
      };
      if (key === 'secondary_power_kw') return {
        key,
        label: 'Secondary power',
        unit: 'kW',
        enabled: false,
        role: 'unused' as const,
        mapping: 'none' as const,
        initializeState: false,
        uncertainty: { status: 'pending' as const, model: 'absolute' as const, unit: 'kW' },
      };
      if (key === 'efficiency_percent') return {
        key,
        label: 'Efficiency',
        unit: '%',
        enabled: false,
        role: 'unused' as const,
        mapping: 'none' as const,
        initializeState: false,
        uncertainty: { status: 'pending' as const, model: 'absolute' as const, unit: '%' },
      };
      if (key === 'primary_torque' || key === 'secondary_torque') return {
        key,
        label: key === 'primary_torque' ? 'Primary torque' : 'Secondary torque',
        unit: 'N·m',
        enabled: false,
        role: 'unused' as const,
        mapping: 'none' as const,
        initializeState: false,
        uncertainty: { status: 'pending' as const, model: 'absolute' as const, unit: 'N·m' },
      };
      return {
        key,
        label: key.replace(/_/g, ' '),
        unit: '',
        enabled: false,
        role: 'unused' as const,
        mapping: 'none' as const,
        initializeState: false,
        uncertainty: { status: 'pending' as const, model: 'absolute' as const },
      };
    });
}

function measurementValueAtStart(data: ParsedDynoData, crop: CropWindow, channel: ChannelConfig): number | null {
  const values = data.columns[channel.key];
  if (values === undefined) return null;
  return values[nearestIndex(data.timeS, crop.startS)] ?? null;
}

function referencePoints(
  data: ParsedDynoData,
  crop: CropWindow,
  channel: ChannelConfig,
  convert: (value: number) => number,
): Array<{ time_s: number; value: number }> {
  const values = data.columns[channel.key];
  if (values === undefined) throw new Error(`Missing channel '${channel.key}'.`);

  const interval = channel.uncertainty.replaySampleIntervalS;
  if (
    (channel.mapping === 'primary_speed' || channel.mapping === 'secondary_speed')
    && interval !== undefined
    && Number.isFinite(interval)
    && interval > 0
  ) {
    const resampled = resampleLinear(data.timeS, values, crop.startS, crop.endS, interval);
    if (resampled.length >= 2) {
      return resampled.map(([time, value]) => ({
        time_s: time - crop.startS,
        value: convert(value),
      }));
    }
  }

  return croppedIndices(data.timeS, crop.startS, crop.endS).map((index) => ({
    time_s: data.timeS[index] - crop.startS,
    value: convert(values[index]),
  }));
}

function findMapped(channels: ChannelConfig[], mapping: ChannelConfig['mapping']): ChannelConfig | undefined {
  return channels.find((channel) => channel.enabled && channel.mapping === mapping);
}

function findMappingCandidate(channels: ChannelConfig[], mapping: ChannelConfig['mapping']): ChannelConfig | undefined {
  return channels.find((channel) => channel.mapping === mapping);
}

interface ResolvedInitialState {
  primaryAngularSpeedRadPerS: number;
  secondaryAngularSpeedRadPerS: number;
  beltSpeedMPerS: number;
  shiftPositionM: number;
  shiftSpeedMPerS: number;
  beltSpeedSource: 'manual' | 'deadzone_secondary_lock';
  beltSecondaryLockRadiusM?: number;
}

function objectValue(value: unknown, name: string): JsonObject {
  if (typeof value !== 'object' || value === null || Array.isArray(value)) {
    throw new Error(`${name} is missing from the validation setup.`);
  }
  return value as JsonObject;
}

function finiteNumber(value: unknown, name: string): number {
  if (typeof value !== 'number' || !Number.isFinite(value)) {
    throw new Error(`${name} must be a finite number in the validation setup.`);
  }
  return value;
}

function resolveInitialState(
  workspace: ValidationWorkspace,
  data: ParsedDynoData,
  crop: CropWindow,
  channels: ChannelConfig[],
): ResolvedInitialState {
  const workflow = (workspace.workflowDefaults ?? {}) as ValidationWorkflowDefaults;
  const manual = { ...DEFAULT_MANUAL_STATE, ...(workflow.manualInitialState ?? {}) };
  const primary = findMapped(channels, 'primary_speed');
  const secondary = findMapped(channels, 'secondary_speed');
  const shift = findMapped(channels, 'shift_position');

  const primaryInitial = primary?.initializeState
    ? rpmToRadPerS(measurementValueAtStart(data, crop, primary) ?? 0)
    : manual.primaryAngularSpeedRadPerS;
  const secondaryInitial = secondary?.initializeState
    ? rpmToRadPerS(measurementValueAtStart(data, crop, secondary) ?? 0)
    : manual.secondaryAngularSpeedRadPerS;
  const shiftInitial = shift?.initializeState && shift.unit === 'm'
    ? measurementValueAtStart(data, crop, shift) ?? manual.shiftPositionM
    : manual.shiftPositionM;
  const shiftSpeedInitial = manual.shiftSpeedMPerS;

  const setup = workspace.setupDocument as unknown as JsonObject;
  const assembly = objectValue(setup.assembly, 'assembly');
  const geometry = objectValue(assembly.geometry, 'assembly.geometry');
  const deadzoneShift = finiteNumber(geometry.deadzone_shift_m, 'assembly.geometry.deadzone_shift_m');
  const inDeadzone = deadzoneShift > 0 && (
    shiftInitial < deadzoneShift
    || (shiftInitial === deadzoneShift && shiftSpeedInitial < 0)
  );

  if (inDeadzone) {
    const belt = objectValue(geometry.belt, 'assembly.geometry.belt');
    const secondaryOuterRadius = finiteNumber(
      geometry.secondary_outer_radius_at_zero_shift_m,
      'assembly.geometry.secondary_outer_radius_at_zero_shift_m',
    );
    const cordDepth = finiteNumber(
      belt.cord_depth_from_outer_m,
      'assembly.geometry.belt.cord_depth_from_outer_m',
    );
    const lockRadius = secondaryOuterRadius - cordDepth;
    if (!(lockRadius > 0)) throw new Error('Resolved deadzone belt-secondary lock radius must be positive.');
    return {
      primaryAngularSpeedRadPerS: primaryInitial,
      secondaryAngularSpeedRadPerS: secondaryInitial,
      beltSpeedMPerS: lockRadius * secondaryInitial,
      shiftPositionM: shiftInitial,
      shiftSpeedMPerS: shiftSpeedInitial,
      beltSpeedSource: 'deadzone_secondary_lock',
      beltSecondaryLockRadiusM: lockRadius,
    };
  }

  return {
    primaryAngularSpeedRadPerS: primaryInitial,
    secondaryAngularSpeedRadPerS: secondaryInitial,
    beltSpeedMPerS: manual.beltSpeedMPerS,
    shiftPositionM: shiftInitial,
    shiftSpeedMPerS: shiftSpeedInitial,
    beltSpeedSource: 'manual',
  };
}

function replayBoundary(
  points: Array<{ time_s: number; value: number }>,
  workflow: ValidationWorkflowDefaults,
): JsonObject {
  const gain = workflow.speedReplay?.trackingGainNmSPerRad ?? DEFAULT_REPLAY_GAIN_NM_S_PER_RAD;
  if (!(gain > 0) || !Number.isFinite(gain)) throw new Error('RPM replay gain must be positive and finite.');
  return {
    kind: 'speed_replay_shaft',
    speed_reference: { points },
    tracking_gain_Nm_s_per_rad: gain,
  };
}

function resolveDocument(
  workspace: ValidationWorkspace,
  data: ParsedDynoData,
  crop: CropWindow,
  channels: ChannelConfig[],
): SimulationCaseDocument {
  const document = deepClone(workspace.setupDocument) as unknown as JsonObject;
  const workflow = (workspace.workflowDefaults ?? {}) as ValidationWorkflowDefaults;
  const primary = findMapped(channels, 'primary_speed');
  const secondary = findMapped(channels, 'secondary_speed');
  const initial = resolveInitialState(workspace, data, crop, channels);

  const scenario = document.scenario as JsonObject;
  const validationDurationS = crop.endS - crop.startS;
  scenario.time_span_s = [0, validationDurationS];
  scenario.initial_cvt_state = {
    primary_angular_speed_rad_per_s: initial.primaryAngularSpeedRadPerS,
    secondary_angular_speed_rad_per_s: initial.secondaryAngularSpeedRadPerS,
    belt_speed_m_per_s: initial.beltSpeedMPerS,
    shift_position_m: initial.shiftPositionM,
    shift_speed_m_per_s: initial.shiftSpeedMPerS,
  };

  // Validation deliberately uses replay-safe tolerances for every run. These
  // are validation-page execution defaults, not global CINDER defaults.
  const validationIntegrator = DEFAULT_VALIDATION_INTEGRATOR;
  const execution = objectValue(document.execution, 'execution');
  const integrator = objectValue(execution.integrator, 'execution.integrator');
  integrator.relative_tolerance = validationIntegrator.relativeTolerance;
  integrator.absolute_tolerance = validationIntegrator.absoluteTolerance;
  integrator.max_step = validationIntegrator.maxStepS;
  integrator.maximum_transitions = validationTransitionBudget(validationDurationS);

  const boundaries = document.shaft_boundaries as JsonObject;
  if (normalizeMode(workflow.primaryMode) === 'replay_measured_speed') {
    if (primary === undefined) throw new Error('Primary RPM replay requires a mapped primary-speed measurement.');
    boundaries.primary = replayBoundary(referencePoints(data, crop, primary, rpmToRadPerS), workflow);
  }
  if (normalizeMode(workflow.secondaryMode) === 'replay_measured_speed') {
    if (secondary === undefined) throw new Error('Secondary RPM replay requires a mapped secondary-speed measurement.');
    boundaries.secondary = replayBoundary(referencePoints(data, crop, secondary, rpmToRadPerS), workflow);
  }

  return document as unknown as SimulationCaseDocument;
}

function simSeries(run: CompletedSimulationRun, key: string, scale = 1): Array<[number, number]> {
  const table = run.result.report_table;
  const time = reportAxisTimes(table);
  const column = reportColumn(table, key);
  if (column === undefined) return [];
  const result: Array<[number, number]> = [];
  column.values.forEach((value, index) => {
    if (typeof value === 'number' && Number.isFinite(value)) result.push([time[index], value * scale]);
  });
  return result;
}

function comparisonMetric(
  data: ParsedDynoData,
  crop: CropWindow,
  channel: ChannelConfig,
  simulation: Array<[number, number]>,
): SignalMetric {
  const indices = croppedIndices(data.timeS, crop.startS, crop.endS);
  const measured = indices.map((index) => data.columns[channel.key][index]);
  const simTime = simulation.map(([time]) => time);
  const simValue = simulation.map(([, value]) => value);
  const predicted = indices.map((index) => interpolate(simTime, simValue, data.timeS[index] - crop.startS));
  return errorMetrics(measured, predicted);
}

function formatMetric(value: number): string {
  return Number.isFinite(value) ? value.toFixed(2) : '—';
}

function boundaryKind(document: SimulationCaseDocument, shaft: Shaft): string {
  const root = document as unknown as JsonObject;
  const boundaries = root.shaft_boundaries as JsonObject | undefined;
  const boundary = boundaries?.[shaft] as JsonObject | undefined;
  return typeof boundary?.kind === 'string' ? boundary.kind : 'unknown';
}

function boundaryKindLabel(kind: string): string {
  if (kind === 'full_throttle_engine') return 'Full-throttle engine';
  if (kind === 'fixed_shaft') return 'Fixed torque / inertia';
  if (kind === 'locked_final_drive') return 'Locked final-drive vehicle';
  if (kind === 'speed_replay_shaft') return 'Measured RPM replay';
  return kind.replace(/_/g, ' ');
}

export const Validation = () => {
  const navigate = useNavigate();
  const { isLoading, loadingMessage, setLoading } = useLoading();
  const [workspace, setWorkspace] = useState<ValidationWorkspace | null>(null);
  const [workspaceStatus, setWorkspaceStatus] = useState('Loading setup…');
  const [workspaceError, setWorkspaceError] = useState<string | null>(null);
  const [data, setData] = useState<ParsedDynoData | null>(null);
  const [channels, setChannels] = useState<ChannelConfig[]>([]);
  const [crop, setCrop] = useState<CropWindow>({ startS: 0, endS: 1 });
  const [editor, setEditor] = useState<SetupSection | null>(null);
  const [uncertaintyEditor, setUncertaintyEditor] = useState<string | null>(null);
  const [completed, setCompleted] = useState<CompletedSimulationRun | null>(null);
  const [metrics, setMetrics] = useState<Record<string, SignalMetric>>({});
  const [recentRuns, setRecentRuns] = useState<ValidationRunSummary[]>([]);
  const [recentRunsError, setRecentRunsError] = useState<string | null>(null);
  const initialWorkspaceRef = useRef(true);

  useEffect(() => {
    setLoading(true, 'Loading validation setup…');
    void getValidationWorkspace(DEMO_ACCOUNT_ID)
      .then((loaded) => {
        setWorkspace(loaded);
        setWorkspaceError(null);
        setWorkspaceStatus('Saved');

        const saved = (loaded.workflowDefaults as ValidationWorkflowDefaults).activeDataset;
        if (
          saved !== undefined
          && typeof saved.filename === 'string'
          && typeof saved.rawCsv === 'string'
          && saved.rawCsv.length > 0
        ) {
          try {
            const restored = parseDynoCsv(saved.filename, saved.rawCsv);
            const first = restored.timeS[0];
            const last = restored.timeS[restored.timeS.length - 1];
            const startS = Math.max(first, Math.min(saved.cropStartS, last));
            const endS = Math.max(startS, Math.min(saved.cropEndS, last));
            const restoredCrop = endS > startS
              ? { startS, endS }
              : { startS: first, endS: last };
            const restoredChannels = Array.isArray(saved.channels) && saved.channels.length > 0
              ? saved.channels
              : defaultChannels(restored, loaded.workflowDefaults as ValidationWorkflowDefaults);

            setData(restored);
            setCrop(restoredCrop);
            setChannels(restoredChannels);
          } catch (cause) {
            console.warn('Could not restore the saved validation dataset.', cause);
          }
        }
      })
      .catch((error) => {
        const message = error instanceof Error ? error.message : String(error);
        setWorkspaceError(message);
        setWorkspaceStatus(`Setup unavailable: ${message}`);
      })
      .finally(() => setLoading(false));
  }, [setLoading]);

  useEffect(() => {
    void listValidationRuns(20)
      .then((runs) => {
        setRecentRuns(runs);
        setRecentRunsError(null);
      })
      .catch((cause) => {
        setRecentRuns([]);
        setRecentRunsError(cause instanceof Error ? cause.message : String(cause));
      });
  }, []);

  useEffect(() => {
    if (workspace === null) return;
    if (initialWorkspaceRef.current) {
      initialWorkspaceRef.current = false;
      return;
    }
    setWorkspaceStatus('Saving…');
    const handle = window.setTimeout(() => {
      void saveValidationWorkspace(workspace)
        .then((saved) => {
          setWorkspace((current) => current === null ? current : {
            ...current,
            id: saved.id,
            updatedAt: saved.updatedAt,
          });
          setWorkspaceStatus(`Saved ${new Date(saved.updatedAt).toLocaleTimeString()}`);
        })
        .catch((error) => setWorkspaceStatus(`Save failed: ${error instanceof Error ? error.message : String(error)}`));
    }, 550);
    return () => window.clearTimeout(handle);
  }, [workspace?.setupDocument, workspace?.metrology, workspace?.workflowDefaults, workspace?.controllerTemplates]);

  useEffect(() => {
    if (data === null) return;
    setWorkspace((current) => current === null ? current : {
      ...current,
      workflowDefaults: {
        ...current.workflowDefaults,
        activeDataset: {
          filename: data.filename,
          rawCsv: data.rawCsv,
          cropStartS: crop.startS,
          cropEndS: crop.endS,
          channels,
        },
      },
    });
  }, [data, crop.startS, crop.endS, channels]);

  const workflow = (workspace?.workflowDefaults ?? {}) as ValidationWorkflowDefaults;
  const manual = { ...DEFAULT_MANUAL_STATE, ...(workflow.manualInitialState ?? {}) };
  const primaryMode = normalizeMode(workflow.primaryMode);
  const secondaryMode = normalizeMode(workflow.secondaryMode);

  const updateWorkflow = (patch: Partial<ValidationWorkflowDefaults>) => {
    setWorkspace((current) => current === null ? current : {
      ...current,
      workflowDefaults: { ...current.workflowDefaults, ...patch },
    });
  };

  const handleFile = async (file: File) => {
    const raw = await file.text();
    const parsed = parseDynoCsv(file.name, raw);
    const loadedChannels = defaultChannels(parsed, workflow).map((channel) => {
      if (channel.mapping === 'primary_speed' && primaryMode === 'replay_measured_speed') {
        return { ...channel, enabled: true, role: 'boundary_input' as const };
      }
      if (channel.mapping === 'secondary_speed' && secondaryMode === 'replay_measured_speed') {
        return { ...channel, enabled: true, role: 'boundary_input' as const };
      }
      return channel;
    });
    setData(parsed);
    setChannels(loadedChannels);
    setCrop({ startS: parsed.timeS[0], endS: parsed.timeS[parsed.timeS.length - 1] });
    setCompleted(null);
    setMetrics({});
  };

  const updateChannel = (key: string, patch: Partial<ChannelConfig>) => {
    setChannels((current) => current.map((channel) => channel.key === key ? { ...channel, ...patch } : channel));
  };

  const setShaftMode = (shaft: Shaft, mode: ShaftValidationMode) => {
    const mapping = shaft === 'primary' ? 'primary_speed' : 'secondary_speed';
    if (mode === 'replay_measured_speed') {
      const candidate = findMappingCandidate(channels, mapping);
      if (candidate === undefined) return;
      setChannels((current) => current.map((channel) => {
        if (channel.key === candidate.key) return { ...channel, enabled: true, role: 'boundary_input' };
        if (channel.mapping === mapping && channel.role === 'boundary_input') return { ...channel, role: 'comparison' };
        return channel;
      }));
    } else {
      setChannels((current) => current.map((channel) => (
        channel.mapping === mapping && channel.role === 'boundary_input'
          ? { ...channel, role: 'comparison' }
          : channel
      )));
    }
    updateWorkflow(shaft === 'primary' ? { primaryMode: mode } : { secondaryMode: mode });
  };

  const setChannelRole = (channel: ChannelConfig, role: ChannelConfig['role']) => {
    const replayable = channel.mapping === 'primary_speed' || channel.mapping === 'secondary_speed';
    if (role === 'boundary_input' && !replayable) return;

    setChannels((current) => current.map((entry) => {
      if (entry.key === channel.key) return { ...entry, enabled: role !== 'unused', role };
      if (role === 'boundary_input' && entry.mapping === channel.mapping && entry.role === 'boundary_input') {
        return { ...entry, role: 'comparison' };
      }
      return entry;
    }));

    if (channel.mapping === 'primary_speed' && (role === 'boundary_input' || channel.role === 'boundary_input')) {
      updateWorkflow({ primaryMode: role === 'boundary_input' ? 'replay_measured_speed' : 'physical' });
    }
    if (channel.mapping === 'secondary_speed' && (role === 'boundary_input' || channel.role === 'boundary_input')) {
      updateWorkflow({ secondaryMode: role === 'boundary_input' ? 'replay_measured_speed' : 'physical' });
    }
  };

  const runValidation = async () => {
    if (workspace === null || data === null) return;
    try {
      const document = resolveDocument(workspace, data, crop, channels);
      setLoading(true, 'Running CINDER validation case…');
      const submitted = await submitValidationSimulationRun(document);
      const status = await waitForSimulationRun(submitted.id);
      if (status.status !== 'completed') throw new Error(status.error?.message ?? `Simulation ${status.status}.`);
      const result = await getSimulationResult(submitted.id);
      setCompleted(result);
      if (!result.result.metrics.completed) {
        const keepPartial = window.confirm(
          `CINDER terminated early after ${result.result.metrics.duration_s.toFixed(3)} s:

`
          + `${result.result.metrics.termination_reason}

`
          + 'Continue anyway and save/open the partial result for debugging?',
        );
        if (!keepPartial) return;
      }

      const nextMetrics: Record<string, SignalMetric> = {};
      const primary = findMapped(channels, 'primary_speed');
      const secondary = findMapped(channels, 'secondary_speed');
      if (primary?.role === 'comparison' && primaryMode !== 'replay_measured_speed') {
        nextMetrics[primary.key] = comparisonMetric(data, crop, primary, simSeries(result, 'state.primary_angular_speed', RAD_PER_S_TO_RPM));
      }
      if (secondary?.role === 'comparison' && secondaryMode !== 'replay_measured_speed') {
        nextMetrics[secondary.key] = comparisonMetric(data, crop, secondary, simSeries(result, 'state.secondary_angular_speed', RAD_PER_S_TO_RPM));
      }
      setMetrics(nextMetrics);

      const resolvedInitialState = resolveInitialState(workspace, data, crop, channels);
      setLoading(true, 'Saving validation result…');
      const savedValidationRun = await saveValidationRun({
        accountId: DEMO_ACCOUNT_ID,
        sourceFilename: data.filename,
        rawCsv: data.rawCsv,
        cropStartS: crop.startS,
        cropEndS: crop.endS,
        channelConfig: Object.fromEntries(channels.map((channel) => [channel.key, channel])),
        initialStateConfig: {
          manual,
          resolved_start_s: crop.startS,
          resolved: resolvedInitialState,
          execution_policy: {
            secondary_helix_topology: 'slotted_bilateral_zero_clearance',
          },
        },
        workspaceSnapshot: workspace,
        resolvedDocument: document,
        simulationRunId: result.run.id,
        resultSnapshot: result.result as unknown as Record<string, unknown>,
        metrics: nextMetrics,
      });
      const validationRunId = savedValidationRun.id;
      if (typeof validationRunId !== 'string' || validationRunId.length === 0) {
        throw new Error('Validation result was saved without a run id.');
      }
      navigate(`/validation/runs/${validationRunId}`);
    } catch (error) {
      alert(`Validation run failed: ${error instanceof Error ? error.message : String(error)}`);
    } finally {
      setLoading(false);
    }
  };

  const mappedPrimary = findMapped(channels, 'primary_speed');
  const mappedSecondary = findMapped(channels, 'secondary_speed');
  const mappedShift = findMapped(channels, 'shift_position');
  const primaryCandidate = findMappingCandidate(channels, 'primary_speed');
  const secondaryCandidate = findMappingCandidate(channels, 'secondary_speed');
  const primaryInitial = data !== null && mappedPrimary?.initializeState
    ? measurementValueAtStart(data, crop, mappedPrimary)
    : null;
  const secondaryInitial = data !== null && mappedSecondary?.initializeState
    ? measurementValueAtStart(data, crop, mappedSecondary)
    : null;
  const resolvedInitial = workspace !== null && data !== null
    ? resolveInitialState(workspace, data, crop, channels)
    : null;

  const resultSeries = useMemo(() => {
    if (completed === null) return { primary_speed: [], secondary_speed: [], shift_position: [] };
    const offset = (series: Array<[number, number]>) =>
      series.map(([time, value]) => [time + crop.startS, value] as [number, number]);
    return {
      primary_speed: offset(simSeries(completed, 'state.primary_angular_speed', RAD_PER_S_TO_RPM)),
      secondary_speed: offset(simSeries(completed, 'state.secondary_angular_speed', RAD_PER_S_TO_RPM)),
      shift_position: offset(simSeries(completed, 'state.shift_position', 1)),
    };
  }, [completed, crop.startS]);

  const renderChannelCard = (channel: ChannelConfig) => {
    if (data === null) return null;
    const sim = channel.mapping === 'primary_speed' ? resultSeries.primary_speed
      : channel.mapping === 'secondary_speed' ? resultSeries.secondary_speed
      : channel.mapping === 'shift_position' ? resultSeries.shift_position
      : undefined;
    const uncertainty = measurementUncertaintySeries(data.columns[channel.key], channel.uncertainty);
    const uncertaintySummary = summarizeUncertainty(uncertainty);
    const replayLocked = channel.role === 'boundary_input';
    const replayable = channel.mapping === 'primary_speed' || channel.mapping === 'secondary_speed';

    return (
      <article key={channel.key} className={`${styles.channelCard} ${replayLocked ? styles.channelCardReplay : ''}`}>
        <ValidationTraceChart
          title={channel.label}
          unit={channel.unit}
          timeS={data.timeS}
          measured={data.columns[channel.key]}
          cropStartS={crop.startS}
          cropEndS={crop.endS}
          onCropChange={(startS, endS) => setCrop({ startS, endS })}
          simulated={completed === null || !channel.enabled ? undefined : sim}
          uncertaintyBySample={uncertainty}
        />
        <div className={styles.channelToolbar}>
          <div className={styles.channelControlGroup}>
            <label className={styles.checkControl}>
              <input
                type="checkbox"
                checked={channel.enabled}
                disabled={replayLocked}
                onChange={(event) => updateChannel(channel.key, {
                  enabled: event.target.checked,
                  role: event.target.checked ? 'comparison' : 'unused',
                })}
              />
              Include
            </label>
            <label>
              <span>Use as</span>
              <select value={channel.role} onChange={(event) => setChannelRole(channel, event.target.value as ChannelConfig['role'])}>
                <option value="comparison">Compare to model</option>
                <option value="boundary_input" disabled={!replayable}>Replay as shaft boundary</option>
                <option value="diagnostic">Diagnostic only</option>
                <option value="unused">Ignore</option>
              </select>
            </label>
            <label>
              <span>Mapping</span>
              <select
                value={channel.mapping}
                disabled={replayLocked}
                onChange={(event) => updateChannel(channel.key, { mapping: event.target.value as ChannelConfig['mapping'] })}
              >
                <option value="none">None</option>
                <option value="primary_speed">Primary speed</option>
                <option value="secondary_speed">Secondary speed</option>
                <option value="shift_position">Shift position</option>
              </select>
            </label>
            <label>
              <span>Unit</span>
              <input value={channel.unit} onChange={(event) => updateChannel(channel.key, { unit: event.target.value })} />
            </label>
          </div>
          <div className={styles.channelMetaRow}>
            <label className={styles.checkControl}>
              <input
                type="checkbox"
                checked={channel.initializeState}
                disabled={!channel.enabled}
                onChange={(event) => updateChannel(channel.key, { initializeState: event.target.checked })}
              />
              Initialize state at crop start
            </label>
            <button type="button" className={styles.metaButton} onClick={() => setUncertaintyEditor(channel.key)}>
              Uncertainty · {uncertaintySummary === null
                ? (channel.uncertainty.status === 'not_applicable' ? 'N/A' : 'Set up')
                : `±${uncertaintySummary.median.toFixed(2)} ${channel.unit} median`}
            </button>
            {replayLocked && <span className={styles.lockBadge}>Locked to RPM replay</span>}
          </div>
        </div>
        {metrics[channel.key] !== undefined && (
          <dl className={styles.metrics}>
            <div><dt>RMSE</dt><dd>{formatMetric(metrics[channel.key].rmse)} {channel.unit}</dd></div>
            <div><dt>MAE</dt><dd>{formatMetric(metrics[channel.key].mae)} {channel.unit}</dd></div>
            <div><dt>Bias</dt><dd>{formatMetric(metrics[channel.key].bias)} {channel.unit}</dd></div>
            <div><dt>Max |error|</dt><dd>{formatMetric(metrics[channel.key].maxAbs)} {channel.unit}</dd></div>
          </dl>
        )}
      </article>
    );
  };

  const primaryRpmChannel = channels.find((channel) => channel.key === 'primary_rpm');
  const secondaryRpmChannel = channels.find((channel) => channel.key === 'secondary_rpm');
  const otherChannels = channels.filter((channel) => channel.key !== 'primary_rpm' && channel.key !== 'secondary_rpm');
  const uncertaintyChannel = uncertaintyEditor === null ? undefined : channels.find((channel) => channel.key === uncertaintyEditor);

  const primaryPhysicalKind = workspace === null ? 'unknown' : boundaryKind(workspace.setupDocument, 'primary');
  const secondaryPhysicalKind = workspace === null ? 'unknown' : boundaryKind(workspace.setupDocument, 'secondary');
  const replayGain = workflow.speedReplay?.trackingGainNmSPerRad ?? DEFAULT_REPLAY_GAIN_NM_S_PER_RAD;
  const validationIntegrator = DEFAULT_VALIDATION_INTEGRATOR;

  return (
    <main className={styles.page}>
      <LoadingOverlay isVisible={isLoading} message={loadingMessage} />
      <header className={styles.header}>
        <div>
          <button type="button" className={styles.backButton} onClick={() => navigate('/')}>← Home</button>
          <span className={styles.eyebrow}>Experimental validation</span>
          <h1>Dyno validation</h1>
          <p>Replay measured shaft speed when it is a boundary input; compare the remaining measured signals against unchanged CINDER mechanics.</p>
        </div>
        <div className={styles.headerStatus}>
          <span className={styles.statusDot} />
          {workspaceStatus}
        </div>
      </header>

      <section className={styles.uploadCard}>
        <div>
          <span className={styles.stepLabel}>01 · Data</span>
          <h2>Load dyno data</h2>
          <p>CSV timestamps remain authoritative. Crop the traces below to define simulation t = 0.</p>
        </div>
        <label className={styles.filePicker}>
          <span>{data === null ? 'Choose CSV' : 'Replace CSV'}</span>
          <input type="file" accept=".csv,text/csv" onChange={(event) => {
            const file = event.target.files?.[0];
            if (file !== undefined) void handleFile(file);
          }} />
        </label>
        {data !== null && (
          <div className={styles.fileSummary}>
            <strong>{data.filename}</strong>
            <span>{data.timeS.length} samples</span>
            <span>{(data.timeS.at(-1) ?? 0).toFixed(3)} s</span>
          </div>
        )}
      </section>

      <section className={styles.recentRunsCard}>
        <div className={styles.sectionHeadingInline}>
          <div>
            <span className={styles.stepLabel}>Recent</span>
            <h2>Saved validation runs</h2>
          </div>
          <p>Newest saved runs. Open any run to revisit its frozen data and CINDER result.</p>
        </div>

        {recentRunsError !== null ? (
          <p className={styles.recentRunsMessage}>Recent runs unavailable: {recentRunsError}</p>
        ) : recentRuns.length === 0 ? (
          <p className={styles.recentRunsMessage}>No saved validation runs yet.</p>
        ) : (
          <div className={styles.recentRunList}>
            {recentRuns.map((run) => (
              <button
                type="button"
                key={run.id}
                className={styles.recentRunRow}
                onClick={() => navigate(`/validation/runs/${run.id}`)}
              >
                <div className={styles.recentRunIdentity}>
                  <strong>{run.sourceFilename}</strong>
                  <span>{new Date(run.createdAt).toLocaleString()}</span>
                </div>
                <div className={styles.recentRunMeta}>
                  <span>crop {run.cropStartS.toFixed(2)}-{run.cropEndS.toFixed(2)} s</span>
                  <span>{(run.cropEndS - run.cropStartS).toFixed(2)} s selected</span>
                  <span className={run.cinderCompleted ? styles.runComplete : styles.runPartial}>
                    {run.cinderCompleted ? 'Complete' : 'Partial'}
                  </span>
                  {!run.cinderCompleted && <span>{run.terminationReason}</span>}
                </div>
              </button>
            ))}
          </div>
        )}
      </section>

      {data !== null && (
        <>
          <section className={styles.sectionHeading}>
            <div>
              <span className={styles.stepLabel}>02 · Measurements</span>
              <h2>Measured traces</h2>
            </div>
            <p>Choose whether each signal validates CINDER, drives a replay boundary, or is kept only as a diagnostic.</p>
          </section>

          <section className={styles.traceGrid}>
            {primaryRpmChannel !== undefined && renderChannelCard(primaryRpmChannel)}
            {secondaryRpmChannel !== undefined && renderChannelCard(secondaryRpmChannel)}
          </section>

          {otherChannels.length > 0 && (
            <details className={styles.otherChannels}>
              <summary>Other imported channels <span>{otherChannels.length}</span></summary>
              <p>Available for mapping, provenance, initialization, and later validation metrics without crowding the primary RPM workflow.</p>
              <section className={styles.traceGrid}>
                {otherChannels.map((channel) => renderChannelCard(channel))}
              </section>
            </details>
          )}

          <section className={styles.setupCard}>
            <div className={styles.sectionHeadingInline}>
              <div>
                <span className={styles.stepLabel}>03 · Run setup</span>
                <h2>Boundaries and CVT</h2>
                <p>The cards show the boundary that will actually reach CINDER. Physical boundaries remain the saved fallback when replay is off.</p>
              </div>
              <div className={styles.executionBadge}>
                Validation solver · rtol {validationIntegrator.relativeTolerance.toExponential(0)} · atol {validationIntegrator.absoluteTolerance.toExponential(0)} · max {Math.round(validationIntegrator.maxStepS * 1000)} ms
              </div>
            </div>
            {workspaceError !== null && <p className={styles.setupError}>{workspaceError}</p>}

            <div className={styles.setupTiles}>
              <article className={styles.setupTile}>
                <div className={styles.tileHeader}>
                  <div>
                    <span className={styles.tileEyebrow}>Primary shaft</span>
                    <strong>{primaryMode === 'replay_measured_speed' ? 'Measured RPM replay' : boundaryKindLabel(primaryPhysicalKind)}</strong>
                  </div>
                  <span className={`${styles.kindBadge} ${primaryMode === 'replay_measured_speed' ? styles.replayBadge : ''}`}>
                    {primaryMode === 'replay_measured_speed' ? 'speed_replay_shaft' : primaryPhysicalKind}
                  </span>
                </div>
                <label className={styles.modeField}>
                  <span>Boundary used for this run</span>
                  <select value={primaryMode} onChange={(event) => setShaftMode('primary', event.target.value as ShaftValidationMode)}>
                    <option value="physical">Physical · {boundaryKindLabel(primaryPhysicalKind)}</option>
                    <option value="replay_measured_speed" disabled={primaryCandidate === undefined}>
                      Replay RPM{primaryCandidate === undefined ? ' · map a primary-speed channel first' : ` · ${primaryCandidate.label}`}
                    </option>
                  </select>
                </label>
                {primaryMode === 'replay_measured_speed' && (
                  <p className={styles.replayNote}>Replay gain {replayGain} N·m·s/rad · physical fallback remains {boundaryKindLabel(primaryPhysicalKind)}.</p>
                )}
                <button type="button" className={styles.editButton} disabled={workspace === null} onClick={() => setEditor('primary')}>
                  Edit physical primary setup
                </button>
              </article>

              <article className={styles.setupTile}>
                <div className={styles.tileHeader}>
                  <div>
                    <span className={styles.tileEyebrow}>CVT</span>
                    <strong>Mechanical assembly</strong>
                  </div>
                  <span className={styles.kindBadge}>CINDER assembly</span>
                </div>
                <p className={styles.tileDescription}>Geometry, belt, friction, inertias, flyweights, springs, helix, and all ordinary CVT mechanics.</p>
                <button type="button" className={styles.editButton} disabled={workspace === null} onClick={() => setEditor('cvt')}>
                  Edit CVT setup
                </button>
              </article>

              <article className={styles.setupTile}>
                <div className={styles.tileHeader}>
                  <div>
                    <span className={styles.tileEyebrow}>Secondary shaft</span>
                    <strong>{secondaryMode === 'replay_measured_speed' ? 'Measured RPM replay' : boundaryKindLabel(secondaryPhysicalKind)}</strong>
                  </div>
                  <span className={`${styles.kindBadge} ${secondaryMode === 'replay_measured_speed' ? styles.replayBadge : ''}`}>
                    {secondaryMode === 'replay_measured_speed' ? 'speed_replay_shaft' : secondaryPhysicalKind}
                  </span>
                </div>
                <label className={styles.modeField}>
                  <span>Boundary used for this run</span>
                  <select value={secondaryMode} onChange={(event) => setShaftMode('secondary', event.target.value as ShaftValidationMode)}>
                    <option value="physical">Physical · {boundaryKindLabel(secondaryPhysicalKind)}</option>
                    <option value="replay_measured_speed" disabled={secondaryCandidate === undefined}>
                      Replay RPM{secondaryCandidate === undefined ? ' · map a secondary-speed channel first' : ` · ${secondaryCandidate.label}`}
                    </option>
                  </select>
                </label>
                {secondaryMode === 'replay_measured_speed' && (
                  <p className={styles.replayNote}>Replay gain {replayGain} N·m·s/rad · physical fallback remains {boundaryKindLabel(secondaryPhysicalKind)}.</p>
                )}
                <button type="button" className={styles.editButton} disabled={workspace === null} onClick={() => setEditor('secondary')}>
                  Edit physical secondary setup
                </button>
              </article>
            </div>
          </section>

          <section className={styles.stateCard}>
            <div className={styles.sectionHeadingInline}>
              <div>
                <span className={styles.stepLabel}>04 · Initial state</span>
                <h2>State at t = {crop.startS.toFixed(3)} s</h2>
              </div>
              <span className={styles.subtleBadge}>Crop start becomes CINDER t = 0</span>
            </div>
            <fieldset className={styles.sectionFieldset} disabled={workspace === null}>
              <div className={styles.stateGrid}>
                <label>Primary speed [rpm]
                  <input disabled={primaryInitial !== null} value={primaryInitial ?? manual.primaryAngularSpeedRadPerS * RAD_PER_S_TO_RPM} onChange={(event) => updateWorkflow({ manualInitialState: { ...manual, primaryAngularSpeedRadPerS: rpmToRadPerS(Number(event.target.value)) } })} />
                </label>
                <label>Secondary speed [rpm]
                  <input disabled={secondaryInitial !== null} value={secondaryInitial ?? manual.secondaryAngularSpeedRadPerS * RAD_PER_S_TO_RPM} onChange={(event) => updateWorkflow({ manualInitialState: { ...manual, secondaryAngularSpeedRadPerS: rpmToRadPerS(Number(event.target.value)) } })} />
                </label>
                <label>Belt speed [m/s]
                  <input
                    type="number"
                    step="any"
                    disabled={resolvedInitial?.beltSpeedSource === 'deadzone_secondary_lock'}
                    value={resolvedInitial?.beltSpeedSource === 'deadzone_secondary_lock'
                      ? resolvedInitial.beltSpeedMPerS
                      : manual.beltSpeedMPerS}
                    onChange={(event) => updateWorkflow({ manualInitialState: { ...manual, beltSpeedMPerS: Number(event.target.value) } })}
                  />
                  {resolvedInitial?.beltSpeedSource === 'deadzone_secondary_lock' && (
                    <small className={styles.derivedState}>
                      Deadzone constraint: v_b = r_s ω_s, r_s = {resolvedInitial.beltSecondaryLockRadiusM?.toFixed(6)} m
                    </small>
                  )}
                </label>
                <label>Shift position [m]
                  <input
                    type="number"
                    step="any"
                    disabled={mappedShift?.initializeState === true && mappedShift.unit === 'm'}
                    value={mappedShift?.initializeState === true && mappedShift.unit === 'm' && data !== null
                      ? measurementValueAtStart(data, crop, mappedShift) ?? manual.shiftPositionM
                      : manual.shiftPositionM}
                    onChange={(event) => updateWorkflow({ manualInitialState: { ...manual, shiftPositionM: Number(event.target.value) } })}
                  />
                </label>
                <label>Shift speed [m/s]
                  <input type="number" step="any" value={manual.shiftSpeedMPerS} onChange={(event) => updateWorkflow({ manualInitialState: { ...manual, shiftSpeedMPerS: Number(event.target.value) } })} />
                </label>
              </div>
            </fieldset>
          </section>

          <section className={styles.runCard}>
            <div>
              <span className={styles.stepLabel}>05 · Run</span>
              <strong>{(crop.endS - crop.startS).toFixed(3)} s selected</strong>
              <p>
                {primaryMode === 'replay_measured_speed' ? 'Primary RPM replay' : 'Primary physical'} · {' '}
                {secondaryMode === 'replay_measured_speed' ? 'Secondary RPM replay' : 'Secondary physical'}
                {' · '}Slotted secondary helix
              </p>
            </div>
            <button type="button" className={styles.runButton} disabled={workspace === null} onClick={() => void runValidation()}>
              Run CINDER validation
            </button>
          </section>
        </>
      )}

      {workspace !== null && editor !== null && (
        <SetupEditorModal
          section={editor}
          document={workspace.setupDocument}
          metrology={workspace.metrology as unknown as Record<string, MeasurementMetadata>}
          onChange={(setupDocument, metrology) => setWorkspace((current) => current === null ? current : ({
            ...current,
            setupDocument,
            metrology: metrology as unknown as Record<string, Record<string, unknown>>,
          }))}
          onClose={() => setEditor(null)}
        />
      )}

      {data !== null && uncertaintyChannel !== undefined && (
        <MeasurementUncertaintyModal
          channel={uncertaintyChannel}
          values={data.columns[uncertaintyChannel.key]}
          onSave={(uncertainty) => {
            updateChannel(uncertaintyChannel.key, { uncertainty });
            if (uncertaintyChannel.mapping === 'primary_speed') {
              updateWorkflow({
                rpmMeasurementDefaults: {
                  ...workflow.rpmMeasurementDefaults,
                  primary: uncertainty,
                },
              });
            }
            if (uncertaintyChannel.mapping === 'secondary_speed') {
              updateWorkflow({
                rpmMeasurementDefaults: {
                  ...workflow.rpmMeasurementDefaults,
                  secondary: uncertainty,
                },
              });
            }
          }}
          onClose={() => setUncertaintyEditor(null)}
        />
      )}
    </main>
  );
};
