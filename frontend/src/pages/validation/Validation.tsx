import { useEffect, useMemo, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { LoadingOverlay } from '@components/loadingOverlay/LoadingOverlay';
import { SetupEditorModal } from '@components/validation/SetupEditorModal';
import { ValidationTraceChart } from '@components/validation/ValidationTraceChart';
import { useLoading } from '@contexts/LoadingContext';
import {
  DEMO_ACCOUNT_ID,
  getSimulationResult,
  getValidationWorkspace,
  saveValidationRun,
  saveValidationWorkspace,
  submitSimulationRun,
  waitForSimulationRun,
  type CompletedSimulationRun,
  type SimulationCaseDocument,
  type ValidationWorkspace,
} from '@api/client';
import { reportAxisTimes, reportColumn } from '@utils/reportTable';
import {
  croppedIndices,
  errorMetrics,
  interpolate,
  nearestIndex,
  parseDynoCsv,
  RAD_PER_S_TO_RPM,
  rpmToRadPerS,
} from './data';
import type {
  ChannelConfig,
  CropWindow,
  ParsedDynoData,
  MeasurementMetadata,
  SignalMetric,
  ValidationWorkflowDefaults,
} from './types';
import styles from './Validation.module.scss';

type SetupSection = 'primary' | 'cvt' | 'secondary';
type JsonObject = Record<string, unknown>;

const DEFAULT_MANUAL_STATE = {
  primaryAngularSpeedRadPerS: 0,
  secondaryAngularSpeedRadPerS: 0,
  beltSpeedMPerS: 0,
  shiftPositionM: 0,
  shiftSpeedMPerS: 0,
};

function deepClone<T>(value: T): T {
  return JSON.parse(JSON.stringify(value)) as T;
}

function defaultChannels(data: ParsedDynoData): ChannelConfig[] {
  return Object.keys(data.columns)
    .filter((key) => key !== 'timestamp_ms' && !/^time(_s)?$/i.test(key))
    .map((key) => {
      if (key === 'primary_rpm') return {
        key, label: 'Primary RPM', unit: 'rpm', enabled: true, role: 'comparison' as const,
        mapping: 'primary_speed' as const, initializeState: true,
        uncertainty: { status: 'pending' as const, unit: 'rpm' },
      };
      if (key === 'secondary_rpm') return {
        key, label: 'Secondary RPM', unit: 'rpm', enabled: true, role: 'comparison' as const,
        mapping: 'secondary_speed' as const, initializeState: true,
        uncertainty: { status: 'pending' as const, unit: 'rpm' },
      };
      if (key === 'shift_position') return {
        key, label: 'Shift position', unit: 'raw', enabled: false, role: 'unused' as const,
        mapping: 'shift_position' as const, initializeState: false,
        uncertainty: { status: 'pending' as const, unit: 'raw' },
      };
      if (key === 'primary_power_kw') return {
        key, label: 'Primary power', unit: 'kW', enabled: false, role: 'unused' as const,
        mapping: 'none' as const, initializeState: false,
        uncertainty: { status: 'pending' as const, unit: 'kW' },
      };
      if (key === 'secondary_power_kw') return {
        key, label: 'Secondary power', unit: 'kW', enabled: false, role: 'unused' as const,
        mapping: 'none' as const, initializeState: false,
        uncertainty: { status: 'pending' as const, unit: 'kW' },
      };
      if (key === 'efficiency_percent') return {
        key, label: 'Efficiency', unit: '%', enabled: false, role: 'unused' as const,
        mapping: 'none' as const, initializeState: false,
        uncertainty: { status: 'pending' as const, unit: '%' },
      };
      if (key === 'primary_torque' || key === 'secondary_torque') return {
        key, label: key === 'primary_torque' ? 'Primary torque' : 'Secondary torque', unit: 'N·m',
        enabled: false, role: 'unused' as const, mapping: 'none' as const, initializeState: false,
        uncertainty: { status: 'pending' as const, unit: 'N·m' },
      };
      return {
        key,
        label: key.replaceAll('_', ' '),
        unit: '',
        enabled: false,
        role: 'unused' as const,
        mapping: 'none' as const,
        initializeState: false,
        uncertainty: { status: 'pending' as const },
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
  return croppedIndices(data.timeS, crop.startS, crop.endS).map((index) => ({
    time_s: data.timeS[index] - crop.startS,
    value: convert(values[index]),
  }));
}

function findMapped(channels: ChannelConfig[], mapping: ChannelConfig['mapping']): ChannelConfig | undefined {
  return channels.find((channel) => channel.enabled && channel.mapping === mapping);
}

function numeric(value: number | null | undefined, name: string): number {
  if (value === null || value === undefined || !Number.isFinite(value)) throw new Error(`${name} must be set before running.`);
  return value;
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

function trackingBoundary(
  points: Array<{ time_s: number; value: number }>,
  workflow: ValidationWorkflowDefaults,
): JsonObject {
  const settings = workflow.speedTracking;
  return {
    kind: 'speed_tracking_shaft',
    speed_reference: { points },
    proportional_gain_Nm_s_per_rad: numeric(settings?.proportionalGainNmSPerRad, 'Speed tracking gain'),
    torque_limit_Nm: numeric(settings?.torqueLimitNm, 'Speed tracking torque limit'),
    equivalent_inertia_kg_m2: numeric(settings?.equivalentInertiaKgM2 ?? 0, 'Speed tracking equivalent inertia'),
    feedforward_inertia_kg_m2: numeric(settings?.feedforwardInertiaKgM2 ?? 0, 'Speed tracking feedforward inertia'),
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
  const shift = findMapped(channels, 'shift_position');
  const initial = resolveInitialState(workspace, data, crop, channels);

  const scenario = document.scenario as JsonObject;
  scenario.time_span_s = [0, crop.endS - crop.startS];
  scenario.initial_cvt_state = {
    primary_angular_speed_rad_per_s: initial.primaryAngularSpeedRadPerS,
    secondary_angular_speed_rad_per_s: initial.secondaryAngularSpeedRadPerS,
    belt_speed_m_per_s: initial.beltSpeedMPerS,
    shift_position_m: initial.shiftPositionM,
    shift_speed_m_per_s: initial.shiftSpeedMPerS,
  };

  const boundaries = document.shaft_boundaries as JsonObject;
  if (workflow.primaryMode === 'track_measured_speed') {
    if (primary === undefined) throw new Error('Primary speed tracking requires an enabled primary-speed channel.');
    boundaries.primary = trackingBoundary(referencePoints(data, crop, primary, rpmToRadPerS), workflow);
  }
  if (workflow.secondaryMode === 'track_measured_speed') {
    if (secondary === undefined) throw new Error('Secondary speed tracking requires an enabled secondary-speed channel.');
    boundaries.secondary = trackingBoundary(referencePoints(data, crop, secondary, rpmToRadPerS), workflow);
  }

  if (workflow.axialMode === 'track_measured_position') {
    if (shift === undefined || shift.unit !== 'm') throw new Error('Axial tracking requires an enabled shift-position channel calibrated in metres.');
    const settings = workflow.axialTracking;
    const assembly = document.assembly as JsonObject;
    const pulleys = assembly.pulleys as JsonObject;
    // The uploaded shift-position channel maps to CINDER's global shift / primary
    // local axial coordinate.  Secondary local position is a nonlinear geometry
    // mapping, so do not silently reuse this trace on the secondary.
    const pulley = pulleys.primary as JsonObject;
    const components = Array.isArray(pulley.components) ? pulley.components as JsonObject[] : [];
    pulley.components = [
      ...components.filter((component) => component.kind !== 'axial_motion_tracking'),
      {
        kind: 'axial_motion_tracking',
        position_reference: { points: referencePoints(data, crop, shift, (value) => value) },
        speed_reference: null,
        position_gain_N_per_m: numeric(settings?.positionGainNPerM, 'Axial position gain'),
        speed_gain_N_s_per_m: settings?.speedGainNSPerM ?? 0,
        force_limit_N: numeric(settings?.forceLimitN, 'Axial force limit'),
      },
    ];
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
  const [completed, setCompleted] = useState<CompletedSimulationRun | null>(null);
  const [metrics, setMetrics] = useState<Record<string, SignalMetric>>({});
  const initialWorkspaceRef = useRef(true);

  useEffect(() => {
    setLoading(true, 'Loading validation setup…');
    void getValidationWorkspace(DEMO_ACCOUNT_ID)
      .then((loaded) => {
        setWorkspace(loaded);
        setWorkspaceError(null);
        setWorkspaceStatus('Saved');
      })
      .catch((error) => {
        const message = error instanceof Error ? error.message : String(error);
        setWorkspaceError(message);
        setWorkspaceStatus(`Setup unavailable: ${message}`);
      })
      .finally(() => setLoading(false));
  }, [setLoading]);

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
          // Keep the canonical local objects stable so the successful save does
          // not trigger another autosave solely because the response was parsed
          // into fresh object identities. updatedAt is intentionally excluded
          // from the effect dependencies below.
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

  const workflow = (workspace?.workflowDefaults ?? {}) as ValidationWorkflowDefaults;
  const manual = { ...DEFAULT_MANUAL_STATE, ...(workflow.manualInitialState ?? {}) };

  const updateWorkflow = (patch: Partial<ValidationWorkflowDefaults>) => {
    setWorkspace((current) => current === null ? current : {
      ...current,
      workflowDefaults: { ...current.workflowDefaults, ...patch },
    });
  };

  const handleFile = async (file: File) => {
    const raw = await file.text();
    const parsed = parseDynoCsv(file.name, raw);
    setData(parsed);
    setChannels(defaultChannels(parsed));
    setCrop({ startS: parsed.timeS[0], endS: parsed.timeS[parsed.timeS.length - 1] });
    setCompleted(null);
    setMetrics({});
  };

  const updateChannel = (key: string, patch: Partial<ChannelConfig>) => {
    setChannels((current) => current.map((channel) => channel.key === key ? { ...channel, ...patch } : channel));
  };

  const runValidation = async () => {
    if (workspace === null || data === null) return;
    try {
      const document = resolveDocument(workspace, data, crop, channels);
      setLoading(true, 'Running CINDER validation case…');
      const submitted = await submitSimulationRun(document);
      const status = await waitForSimulationRun(submitted.id);
      if (status.status !== 'completed') throw new Error(status.error?.message ?? `Simulation ${status.status}.`);
      const result = await getSimulationResult(submitted.id);
      setCompleted(result);

      const nextMetrics: Record<string, SignalMetric> = {};
      const primary = findMapped(channels, 'primary_speed');
      const secondary = findMapped(channels, 'secondary_speed');
      if (primary?.role === 'comparison' && workflow.primaryMode !== 'track_measured_speed') {
        nextMetrics[primary.key] = comparisonMetric(data, crop, primary, simSeries(result, 'state.primary_angular_speed', RAD_PER_S_TO_RPM));
      }
      if (secondary?.role === 'comparison' && workflow.secondaryMode !== 'track_measured_speed') {
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
    const uncertainty = channel.uncertainty.status === 'known' ? channel.uncertainty.absolute : undefined;
    const sim = channel.mapping === 'primary_speed' ? resultSeries.primary_speed
      : channel.mapping === 'secondary_speed' ? resultSeries.secondary_speed
      : channel.mapping === 'shift_position' ? resultSeries.shift_position
      : undefined;
    return (
      <div key={channel.key} className={styles.channelCard}>
        <ValidationTraceChart
          title={channel.label}
          unit={channel.unit}
          timeS={data.timeS}
          measured={data.columns[channel.key]}
          cropStartS={crop.startS}
          cropEndS={crop.endS}
          onCropChange={(startS, endS) => setCrop({ startS, endS })}
          simulated={completed === null || !channel.enabled ? undefined : sim}
          uncertaintyAbsolute={uncertainty}
        />
        <div className={styles.channelControls}>
          <label><input type="checkbox" checked={channel.enabled} onChange={(event) => updateChannel(channel.key, { enabled: event.target.checked, role: event.target.checked ? 'comparison' : 'unused' })} /> Enable</label>
          <label>Use as
            <select value={channel.role} disabled={!channel.enabled} onChange={(event) => updateChannel(channel.key, { role: event.target.value as ChannelConfig['role'] })}>
              <option value="comparison">Comparison</option>
              <option value="boundary_input">Boundary input</option>
              <option value="diagnostic">Diagnostic</option>
              <option value="unused">Unused</option>
            </select>
          </label>
          <label>Mapping
            <select value={channel.mapping} onChange={(event) => updateChannel(channel.key, { mapping: event.target.value as ChannelConfig['mapping'] })}>
              <option value="none">None</option>
              <option value="primary_speed">Primary speed</option>
              <option value="secondary_speed">Secondary speed</option>
              <option value="shift_position">Shift position</option>
            </select>
          </label>
          <label>Unit <input value={channel.unit} onChange={(event) => updateChannel(channel.key, { unit: event.target.value })} /></label>
          <label><input type="checkbox" checked={channel.initializeState} disabled={!channel.enabled} onChange={(event) => updateChannel(channel.key, { initializeState: event.target.checked })} /> Initialize state at crop start</label>
          <label>Uncertainty
            <select value={channel.uncertainty.status} onChange={(event) => updateChannel(channel.key, { uncertainty: { ...channel.uncertainty, status: event.target.value as ChannelConfig['uncertainty']['status'] } })}>
              <option value="pending">Pending</option>
              <option value="known">Known</option>
              <option value="not_applicable">N/A</option>
            </select>
          </label>
          {channel.uncertainty.status === 'known' && <label>± <input type="number" step="any" value={channel.uncertainty.absolute ?? 0} onChange={(event) => updateChannel(channel.key, { uncertainty: { ...channel.uncertainty, absolute: Number(event.target.value), unit: channel.unit } })} /> {channel.unit}</label>}
        </div>
        {metrics[channel.key] !== undefined && (
          <dl className={styles.metrics}>
            <div><dt>RMSE</dt><dd>{formatMetric(metrics[channel.key].rmse)} {channel.unit}</dd></div>
            <div><dt>MAE</dt><dd>{formatMetric(metrics[channel.key].mae)} {channel.unit}</dd></div>
            <div><dt>Bias</dt><dd>{formatMetric(metrics[channel.key].bias)} {channel.unit}</dd></div>
            <div><dt>Max |error|</dt><dd>{formatMetric(metrics[channel.key].maxAbs)} {channel.unit}</dd></div>
          </dl>
        )}
      </div>
    );
  };

  const primaryRpmChannel = channels.find((channel) => channel.key === 'primary_rpm');
  const secondaryRpmChannel = channels.find((channel) => channel.key === 'secondary_rpm');
  const otherChannels = channels.filter((channel) => channel.key !== 'primary_rpm' && channel.key !== 'secondary_rpm');

  return (
    <main className={styles.page}>
      <LoadingOverlay isVisible={isLoading} message={loadingMessage} />
      <header className={styles.header}>
        <div>
          <button type="button" onClick={() => navigate('/')}>← Home</button>
          <h1>Dyno validation</h1>
          <p>Experimental data remains independent of CINDER; this page resolves a frozen CINDER case and compares the prediction.</p>
        </div>
        <span className={styles.saveStatus}>{workspaceStatus}</span>
      </header>

      <section className={styles.uploadCard}>
        <h2>1. Dyno data</h2>
        <input type="file" accept=".csv,text/csv" onChange={(event) => {
          const file = event.target.files?.[0];
          if (file !== undefined) void handleFile(file);
        }} />
        {data !== null && <p>{data.filename} · {data.timeS.length} samples · {(data.timeS.at(-1) ?? 0).toFixed(3)} s</p>}
      </section>

      {data !== null && (
        <>
          <section className={styles.traceGrid}>
            {primaryRpmChannel !== undefined && renderChannelCard(primaryRpmChannel)}
            {secondaryRpmChannel !== undefined && renderChannelCard(secondaryRpmChannel)}
          </section>

          {otherChannels.length > 0 && (
            <details className={styles.otherChannels}>
              <summary>View all other data channels ({otherChannels.length})</summary>
              <p>These channels stay available for mapping, provenance, and diagnostics without crowding the primary trimming view.</p>
              <section className={styles.traceGrid}>
                {otherChannels.map((channel) => renderChannelCard(channel))}
              </section>
            </details>
          )}

          <section className={styles.setupCard}>
            <h2>2. Physical setup</h2>
            <p>These are autosaved and reused on the next run. Every validation run still freezes its own snapshot.</p>
            {workspaceError !== null && <p className={styles.setupError}>{workspaceError}</p>}
            <div className={styles.setupButtons}>
              <button type="button" disabled={workspace === null} onClick={() => setEditor('primary')}>Primary boundary · Edit</button>
              <button type="button" disabled={workspace === null} onClick={() => setEditor('cvt')}>CVT setup · Edit</button>
              <button type="button" disabled={workspace === null} onClick={() => setEditor('secondary')}>Secondary boundary · Edit</button>
            </div>
          </section>

          <section className={styles.controllerCard}>
              <h2>3. Experimental boundary / actuator mode</h2>
              <fieldset className={styles.sectionFieldset} disabled={workspace === null}>
              <div className={styles.controllerGrid}>
                <label>Primary
                  <select value={workflow.primaryMode ?? 'physical'} onChange={(event) => updateWorkflow({ primaryMode: event.target.value as ValidationWorkflowDefaults['primaryMode'] })}>
                    <option value="physical">Physical boundary</option>
                    <option value="track_measured_speed">Track measured primary speed</option>
                  </select>
                </label>
                <label>Secondary
                  <select value={workflow.secondaryMode ?? 'physical'} onChange={(event) => updateWorkflow({ secondaryMode: event.target.value as ValidationWorkflowDefaults['secondaryMode'] })}>
                    <option value="physical">Physical boundary</option>
                    <option value="track_measured_speed">Track measured secondary speed</option>
                  </select>
                </label>
                <label>Axial motion
                  <select value={workflow.axialMode ?? 'physical'} onChange={(event) => updateWorkflow({ axialMode: event.target.value as ValidationWorkflowDefaults['axialMode'] })}>
                    <option value="physical">Physical actuation</option>
                    <option value="track_measured_position">Track measured shift position</option>
                  </select>
                </label>
              </div>
              {(workflow.primaryMode === 'track_measured_speed' || workflow.secondaryMode === 'track_measured_speed') && (
                <div className={styles.gainGrid}>
                  <label>Speed gain [N·m/(rad/s)] <input type="number" step="any" value={workflow.speedTracking?.proportionalGainNmSPerRad ?? ''} onChange={(event) => updateWorkflow({ speedTracking: { proportionalGainNmSPerRad: Number(event.target.value), torqueLimitNm: workflow.speedTracking?.torqueLimitNm ?? null, equivalentInertiaKgM2: workflow.speedTracking?.equivalentInertiaKgM2 ?? 0, feedforwardInertiaKgM2: workflow.speedTracking?.feedforwardInertiaKgM2 ?? 0 } })} /></label>
                  <label>Torque limit [N·m] <input type="number" step="any" value={workflow.speedTracking?.torqueLimitNm ?? ''} onChange={(event) => updateWorkflow({ speedTracking: { proportionalGainNmSPerRad: workflow.speedTracking?.proportionalGainNmSPerRad ?? null, torqueLimitNm: Number(event.target.value), equivalentInertiaKgM2: workflow.speedTracking?.equivalentInertiaKgM2 ?? 0, feedforwardInertiaKgM2: workflow.speedTracking?.feedforwardInertiaKgM2 ?? 0 } })} /></label>
                </div>
              )}
              {workflow.axialMode === 'track_measured_position' && (
                <div className={styles.gainGrid}>
                  <label>Position gain [N/m] <input type="number" step="any" value={workflow.axialTracking?.positionGainNPerM ?? ''} onChange={(event) => updateWorkflow({ axialTracking: { positionGainNPerM: Number(event.target.value), speedGainNSPerM: workflow.axialTracking?.speedGainNSPerM ?? 0, forceLimitN: workflow.axialTracking?.forceLimitN ?? null } })} /></label>
                  <label>Speed gain [N/(m/s)] <input type="number" step="any" value={workflow.axialTracking?.speedGainNSPerM ?? 0} onChange={(event) => updateWorkflow({ axialTracking: { positionGainNPerM: workflow.axialTracking?.positionGainNPerM ?? null, speedGainNSPerM: Number(event.target.value), forceLimitN: workflow.axialTracking?.forceLimitN ?? null } })} /></label>
                  <label>Force limit [N] <input type="number" step="any" value={workflow.axialTracking?.forceLimitN ?? ''} onChange={(event) => updateWorkflow({ axialTracking: { positionGainNPerM: workflow.axialTracking?.positionGainNPerM ?? null, speedGainNSPerM: workflow.axialTracking?.speedGainNSPerM ?? 0, forceLimitN: Number(event.target.value) } })} /></label>
                </div>
              )}
              </fieldset>
            </section>

          <section className={styles.stateCard}>
            <h2>4. Initial state at t = {crop.startS.toFixed(3)} s</h2>
            <fieldset className={styles.sectionFieldset} disabled={workspace === null}>
            <div className={styles.stateGrid}>
              <label>Primary speed [rpm]<input disabled={primaryInitial !== null} value={primaryInitial ?? manual.primaryAngularSpeedRadPerS * RAD_PER_S_TO_RPM} onChange={(event) => updateWorkflow({ manualInitialState: { ...manual, primaryAngularSpeedRadPerS: rpmToRadPerS(Number(event.target.value)) } })} /></label>
              <label>Secondary speed [rpm]<input disabled={secondaryInitial !== null} value={secondaryInitial ?? manual.secondaryAngularSpeedRadPerS * RAD_PER_S_TO_RPM} onChange={(event) => updateWorkflow({ manualInitialState: { ...manual, secondaryAngularSpeedRadPerS: rpmToRadPerS(Number(event.target.value)) } })} /></label>
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
                    Derived by deadzone constraint: v_b = r_s ω_s, r_s = {resolvedInitial.beltSecondaryLockRadiusM?.toFixed(6)} m
                  </small>
                )}
              </label>
              <label>Shift position [m]<input type="number" step="any" disabled={mappedShift?.initializeState === true && mappedShift.unit === 'm'} value={mappedShift?.initializeState === true && mappedShift.unit === 'm' && data !== null ? measurementValueAtStart(data, crop, mappedShift) ?? manual.shiftPositionM : manual.shiftPositionM} onChange={(event) => updateWorkflow({ manualInitialState: { ...manual, shiftPositionM: Number(event.target.value) } })} /></label>
              <label>Shift speed [m/s]<input type="number" step="any" value={manual.shiftSpeedMPerS} onChange={(event) => updateWorkflow({ manualInitialState: { ...manual, shiftSpeedMPerS: Number(event.target.value) } })} /></label>
            </div>
            </fieldset>
          </section>

          <section className={styles.runCard}>
            <div><strong>Selected experiment:</strong> {(crop.endS - crop.startS).toFixed(3)} s</div>
            <button type="button" disabled={workspace === null} onClick={() => void runValidation()}>Run CINDER validation</button>
          </section>
        </>
      )}

      {workspace !== null && editor !== null && (
        <SetupEditorModal
          section={editor}
          document={workspace.setupDocument}
          metrology={workspace.metrology as unknown as Record<string, MeasurementMetadata>}
          onChange={(setupDocument, metrology) => setWorkspace((current) => current === null ? current : ({ ...current, setupDocument, metrology: metrology as unknown as Record<string, Record<string, unknown>> }))}
          onClose={() => setEditor(null)}
        />
      )}
    </main>
  );
};
