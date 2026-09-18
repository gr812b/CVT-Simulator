import { useEffect, useMemo, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import {
  getValidationRun,
  type SimulationResult,
  type ValidationRunRecord,
} from '@api/client';
import { LoadingOverlay } from '@components/loadingOverlay/LoadingOverlay';
import { ValidationTraceChart } from '@components/validation/ValidationTraceChart';
import { ValidationXYChart } from '@components/validation/ValidationXYChart';
import { useLoading } from '@contexts/LoadingContext';
import { reportAxisTimes, reportColumn } from '@utils/reportTable';
import {
  croppedIndices,
  errorMetrics,
  interpolate,
  measurementUncertaintySeries,
  parseDynoCsv,
  RAD_PER_S_TO_RPM,
  summarizeUncertainty,
} from '@pages/validation/data';
import type {
  ChannelConfig,
  ParsedDynoData,
  SignalMetric,
  ValidationWorkflowDefaults,
} from '@pages/validation/types';
import styles from './ValidationResults.module.scss';

interface RpmComparison {
  channel: ChannelConfig | undefined;
  timeS: number[];
  measured: number[];
  simulated: Array<[number, number]>;
  metric: SignalMetric;
  uncertainty: Array<number | null> | undefined;
  uncertaintySummary: { minimum: number; median: number; maximum: number } | null;
  independent: boolean;
}

interface ResultViews {
  primary: RpmComparison | null;
  secondary: RpmComparison | null;
  shiftMeasured: Array<[number, number]>;
  shiftCinder: Array<[number, number]>;
  powerTimeS: number[];
  primaryPowerMeasuredKw: number[] | null;
  primaryPowerCinderKw: Array<[number, number]>;
  secondaryPowerMeasuredKw: number[] | null;
  secondaryPowerCinderKw: Array<[number, number]>;
  efficiencyMeasured: Array<[number, number]>;
  efficiencyCinder: Array<[number, number]>;
}

interface CinderCompletion {
  completed: boolean;
  terminationReason: string;
  durationS: number;
}

function cinderCompletion(result: SimulationResult): CinderCompletion {
  return {
    completed: result.metrics.completed,
    terminationReason: result.metrics.termination_reason,
    durationS: result.metrics.duration_s,
  };
}

function csvCell(value: unknown): string {
  if (value === null || value === undefined) return '';
  const text = String(value);
  if (!/[",\r\n]/.test(text)) return text;
  return `"${text.split('"').join('""')}"`;
}

function cinderReportCsv(result: SimulationResult): string {
  const table = result.report_table;
  const header = table.columns.map((column) => csvCell(column.key)).join(',');
  const rows = Array.from({ length: table.row_count }, (_, index) => (
    table.columns.map((column) => csvCell(column.values[index] ?? null)).join(',')
  ));
  return [header, ...rows].join('\r\n');
}

function downloadCinderReport(run: ValidationRunRecord): void {
  const blob = new Blob([cinderReportCsv(run.resultSnapshot)], { type: 'text/csv;charset=utf-8' });
  const href = URL.createObjectURL(blob);
  const link = document.createElement('a');
  const cinderRun = run.simulationRunId ?? run.id;
  link.href = href;
  link.download = `cinder-run-${cinderRun}.csv`;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(href);
}

function channelConfigs(raw: Record<string, unknown>): ChannelConfig[] {
  return Object.values(raw).filter((value): value is ChannelConfig => (
    typeof value === 'object'
    && value !== null
    && typeof (value as ChannelConfig).key === 'string'
    && typeof (value as ChannelConfig).mapping === 'string'
  ));
}

function mappedChannel(channels: ChannelConfig[], mapping: ChannelConfig['mapping']): ChannelConfig | undefined {
  return channels.find((channel) => channel.mapping === mapping)
    ?? channels.find((channel) => (
      (mapping === 'primary_speed' && channel.key === 'primary_rpm')
      || (mapping === 'secondary_speed' && channel.key === 'secondary_rpm')
    ));
}

function dataColumn(data: ParsedDynoData, ...keys: string[]): number[] | null {
  for (const key of keys) {
    const values = data.columns[key];
    if (values !== undefined) return values;
  }
  return null;
}

function simulationSeries(
  result: SimulationResult,
  key: string,
  scale: number,
  timeOffsetS: number,
): Array<[number, number]> {
  const table = result.report_table;
  const times = reportAxisTimes(table);
  const column = reportColumn(table, key);
  if (column === undefined) return [];
  const series: Array<[number, number]> = [];
  column.values.forEach((value, index) => {
    if (typeof value === 'number' && Number.isFinite(value)) {
      series.push([times[index] + timeOffsetS, value * scale]);
    }
  });
  return series;
}

function pairedSimulationSeries(
  result: SimulationResult,
  xKey: string,
  yKey: string,
  xScale = 1,
  yScale = 1,
): Array<[number, number]> {
  const x = reportColumn(result.report_table, xKey);
  const y = reportColumn(result.report_table, yKey);
  if (x === undefined || y === undefined) return [];
  const points: Array<[number, number]> = [];
  const count = Math.min(x.values.length, y.values.length);
  for (let index = 0; index < count; index += 1) {
    const xv = x.values[index];
    const yv = y.values[index];
    if (typeof xv === 'number' && Number.isFinite(xv) && typeof yv === 'number' && Number.isFinite(yv)) {
      points.push([xv * xScale, yv * yScale]);
    }
  }
  return points;
}

function nestedNumber(value: unknown, path: string[]): number | null {
  let current: unknown = value;
  for (const key of path) {
    if (typeof current !== 'object' || current === null || Array.isArray(current)) return null;
    current = (current as Record<string, unknown>)[key];
  }
  return typeof current === 'number' && Number.isFinite(current) ? current : null;
}

function secondaryEquivalentInertia(document: unknown): number {
  return nestedNumber(document, ['shaft_boundaries', 'secondary', 'equivalent_inertia_kg_m2']) ?? 0;
}

function fiveSampleLocalSlope(
  times: number[],
  values: Array<number | null>,
): Array<number | null> {
  const slope: Array<number | null> = Array.from({ length: times.length }, () => null);
  if (times.length < 2 || values.length !== times.length) return slope;

  for (let index = 0; index < times.length; index += 1) {
    const windowSize = Math.min(5, times.length);
    const maxStart = times.length - windowSize;
    const start = Math.max(0, Math.min(index - 2, maxStart));
    const end = start + windowSize;
    const samples: Array<[number, number]> = [];
    for (let sampleIndex = start; sampleIndex < end; sampleIndex += 1) {
      const value = values[sampleIndex];
      if (typeof value === 'number' && Number.isFinite(value) && Number.isFinite(times[sampleIndex])) {
        samples.push([times[sampleIndex], value]);
      }
    }
    if (samples.length < 2) continue;

    // Center the fit around the target sample to keep the least-squares slope
    // numerically well conditioned for large absolute timestamps.  For interior
    // points this is the requested i-2..i+2 window; near either endpoint the
    // five-sample window shifts inward instead of shrinking abruptly.
    const centerTime = times[index];
    let sumDt = 0;
    let sumValue = 0;
    for (const [time, value] of samples) {
      sumDt += time - centerTime;
      sumValue += value;
    }
    const meanDt = sumDt / samples.length;
    const meanValue = sumValue / samples.length;
    let covariance = 0;
    let variance = 0;
    for (const [time, value] of samples) {
      const dt = (time - centerTime) - meanDt;
      covariance += dt * (value - meanValue);
      variance += dt * dt;
    }
    if (variance > 0) slope[index] = covariance / variance;
  }
  return slope;
}

function uniqueSeries(series: Array<[number, number]>): Array<[number, number]> {
  const byTime = new Map<number, number>();
  for (const [time, value] of series) byTime.set(time, value);
  return [...byTime.entries()].sort((left, right) => left[0] - right[0]);
}

function sampleSeriesAtTimes(
  series: Array<[number, number]>,
  times: number[],
): Array<number | null> {
  const unique = uniqueSeries(series);
  const sourceTime = unique.map(([time]) => time);
  const sourceValue = unique.map(([, value]) => value);
  return times.map((time) => interpolate(sourceTime, sourceValue, time));
}

function measuredSecondaryOutputPower(
  times: number[],
  secondaryRpm: number[],
  inertia: number,
): number[] | null {
  if (times.length !== secondaryRpm.length || times.length < 2 || inertia <= 0) return null;
  const omega = secondaryRpm.map((rpm) => (
    Number.isFinite(rpm) ? rpm / RAD_PER_S_TO_RPM : null
  ));
  const alpha = fiveSampleLocalSlope(times, omega);
  return omega.map((angularSpeed, index) => {
    const angularAcceleration = alpha[index];
    if (
      typeof angularSpeed !== 'number' || !Number.isFinite(angularSpeed)
      || typeof angularAcceleration !== 'number' || !Number.isFinite(angularAcceleration)
    ) return Number.NaN;
    return (inertia * angularSpeed * angularAcceleration) / 1000;
  });
}

function secondaryBoundaryOutputPowerAtMeasuredTimes(
  result: SimulationResult,
  resolvedDocument: unknown,
  measuredTimes: number[],
  timeOffsetS: number,
): Array<[number, number]> {
  const inertia = secondaryEquivalentInertia(resolvedDocument);
  if (inertia <= 0 || measuredTimes.length < 2) return [];

  const omegaSeries = simulationSeries(result, 'state.secondary_angular_speed', 1, timeOffsetS);
  const torqueSeries = simulationSeries(result, 'boundary.secondary_external_torque', 1, timeOffsetS);
  const omega = sampleSeriesAtTimes(omegaSeries, measuredTimes);
  const externalTorque = sampleSeriesAtTimes(torqueSeries, measuredTimes);
  const alpha = fiveSampleLocalSlope(measuredTimes, omega);
  const points: Array<[number, number]> = [];
  for (let index = 0; index < measuredTimes.length; index += 1) {
    const angularSpeed = omega[index];
    const angularAcceleration = alpha[index];
    const tauExternal = externalTorque[index];
    if (
      typeof angularSpeed !== 'number' || !Number.isFinite(angularSpeed)
      || typeof angularAcceleration !== 'number' || !Number.isFinite(angularAcceleration)
      || typeof tauExternal !== 'number' || !Number.isFinite(tauExternal)
    ) continue;
    const outputW = inertia * angularSpeed * angularAcceleration - tauExternal * angularSpeed;
    points.push([measuredTimes[index], outputW / 1000]);
  }
  return points;
}

function cinderEfficiencyVsSpeedRatioAtMeasuredTimes(
  result: SimulationResult,
  resolvedDocument: unknown,
  measuredTimes: number[],
  timeOffsetS: number,
): Array<[number, number]> {
  const outputPower = secondaryBoundaryOutputPowerAtMeasuredTimes(
    result,
    resolvedDocument,
    measuredTimes,
    timeOffsetS,
  );
  const outputByTime = new Map(outputPower);
  const inputPowerW = sampleSeriesAtTimes(
    simulationSeries(result, 'observer.primary_boundary_power', 1, timeOffsetS),
    measuredTimes,
  );
  const primarySpeed = sampleSeriesAtTimes(
    simulationSeries(result, 'state.primary_angular_speed', 1, timeOffsetS),
    measuredTimes,
  );
  const secondarySpeed = sampleSeriesAtTimes(
    simulationSeries(result, 'state.secondary_angular_speed', 1, timeOffsetS),
    measuredTimes,
  );
  const points: Array<[number, number]> = [];
  for (let index = 0; index < measuredTimes.length; index += 1) {
    const primary = primarySpeed[index];
    const secondary = secondarySpeed[index];
    const inputW = inputPowerW[index];
    const outputKw = outputByTime.get(measuredTimes[index]);
    if (
      typeof primary !== 'number' || !Number.isFinite(primary)
      || typeof secondary !== 'number' || !Number.isFinite(secondary) || Math.abs(secondary) < 1e-9
      || typeof inputW !== 'number' || !Number.isFinite(inputW) || inputW <= 1
      || typeof outputKw !== 'number' || !Number.isFinite(outputKw)
    ) continue;
    points.push([primary / secondary, 100 * (outputKw * 1000) / inputW]);
  }
  return points;
}

function efficiencyVsSpeedRatioFromPower(
  primaryRpm: number[] | null,
  secondaryRpm: number[] | null,
  primaryPowerKw: number[] | null,
  secondaryPowerKw: number[] | null,
): Array<[number, number]> {
  if (
    primaryRpm === null || secondaryRpm === null
    || primaryPowerKw === null || secondaryPowerKw === null
  ) return [];
  const count = Math.min(
    primaryRpm.length,
    secondaryRpm.length,
    primaryPowerKw.length,
    secondaryPowerKw.length,
  );
  const points: Array<[number, number]> = [];
  for (let index = 0; index < count; index += 1) {
    const primary = primaryRpm[index];
    const secondary = secondaryRpm[index];
    const inputKw = primaryPowerKw[index];
    const outputKw = secondaryPowerKw[index];
    if (
      !Number.isFinite(primary) || !Number.isFinite(secondary) || Math.abs(secondary) < 1e-9
      || !Number.isFinite(inputKw) || inputKw <= 0.001
      || !Number.isFinite(outputKw)
    ) continue;
    points.push([primary / secondary, 100 * outputKw / inputKw]);
  }
  return points;
}

function rpmComparison(
  data: ParsedDynoData,
  indices: number[],
  cropStartS: number,
  result: SimulationResult,
  channel: ChannelConfig | undefined,
  fallbackKey: string,
  signalKey: string,
  independent: boolean,
): RpmComparison | null {
  const key = channel?.key ?? fallbackKey;
  const values = data.columns[key];
  if (values === undefined) return null;
  const times = indices.map((index) => data.timeS[index]);
  const measured = indices.map((index) => values[index]);
  const uncertainty = channel === undefined
    ? undefined
    : measurementUncertaintySeries(measured, channel.uncertainty);
  const simulated = simulationSeries(result, signalKey, RAD_PER_S_TO_RPM, cropStartS);
  const simTime = simulated.map(([time]) => time);
  const simValue = simulated.map(([, value]) => value);
  const predicted = times.map((time) => interpolate(simTime, simValue, time));
  return {
    channel,
    timeS: times,
    measured,
    simulated,
    metric: errorMetrics(measured, predicted),
    uncertainty,
    uncertaintySummary: summarizeUncertainty(uncertainty),
    independent,
  };
}

function formatMetric(value: number): string {
  return Number.isFinite(value) ? value.toFixed(2) : '—';
}

function isReplayMode(mode: ValidationWorkflowDefaults['primaryMode']): boolean {
  return mode === 'replay_measured_speed' || mode === 'track_measured_speed';
}

function MetricStrip({ comparison }: { comparison: RpmComparison }) {
  const unit = comparison.channel?.unit || 'rpm';
  if (!comparison.independent) {
    return <p className={styles.diagnosticNote}>This RPM trace was used as a shaft replay boundary, so its speed error is a replay diagnostic rather than independent validation evidence.</p>;
  }
  return (
    <dl className={styles.metrics}>
      <div><dt>RMSE</dt><dd>{formatMetric(comparison.metric.rmse)} {unit}</dd></div>
      <div><dt>MAE</dt><dd>{formatMetric(comparison.metric.mae)} {unit}</dd></div>
      <div><dt>Bias</dt><dd>{formatMetric(comparison.metric.bias)} {unit}</dd></div>
      <div><dt>Max |error|</dt><dd>{formatMetric(comparison.metric.maxAbs)} {unit}</dd></div>
      <div><dt>Samples</dt><dd>{comparison.metric.count}</dd></div>
      {comparison.uncertaintySummary !== null && (
        <div>
          <dt>Median meas. uncertainty</dt>
          <dd>±{formatMetric(comparison.uncertaintySummary.median)} {unit}</dd>
        </div>
      )}
    </dl>
  );
}

export const ValidationResults = () => {
  const { runId } = useParams<{ runId: string }>();
  const navigate = useNavigate();
  const { isLoading, loadingMessage, setLoading } = useLoading();
  const [run, setRun] = useState<ValidationRunRecord | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (runId === undefined) {
      setError('Validation run id is missing.');
      return;
    }
    setLoading(true, 'Loading validation result…');
    void getValidationRun(runId)
      .then((loaded) => {
        setRun(loaded);
        setError(null);
      })
      .catch((cause) => setError(cause instanceof Error ? cause.message : String(cause)))
      .finally(() => setLoading(false));
  }, [runId, setLoading]);

  const views = useMemo<ResultViews | null>(() => {
    if (run === null) return null;
    const data = parseDynoCsv(run.sourceFilename, run.rawCsv);
    const indices = croppedIndices(data.timeS, run.cropStartS, run.cropEndS);
    const channels = channelConfigs(run.channelConfig);
    const workflow = (run.workspaceSnapshot.workflowDefaults ?? {}) as unknown as ValidationWorkflowDefaults;
    const primaryChannel = mappedChannel(channels, 'primary_speed');
    const secondaryChannel = mappedChannel(channels, 'secondary_speed');
    const primaryRpm = dataColumn(data, primaryChannel?.key ?? 'primary_rpm', 'primary_rpm');
    const secondaryRpm = dataColumn(data, secondaryChannel?.key ?? 'secondary_rpm', 'secondary_rpm');

    const primary = rpmComparison(
      data,
      indices,
      run.cropStartS,
      run.resultSnapshot,
      primaryChannel,
      'primary_rpm',
      'state.primary_angular_speed',
      primaryChannel?.role === 'comparison' && !isReplayMode(workflow.primaryMode),
    );
    const secondary = rpmComparison(
      data,
      indices,
      run.cropStartS,
      run.resultSnapshot,
      secondaryChannel,
      'secondary_rpm',
      'state.secondary_angular_speed',
      secondaryChannel?.role === 'comparison' && !isReplayMode(workflow.secondaryMode),
    );

    const shiftMeasured: Array<[number, number]> = [];
    if (primaryRpm !== null && secondaryRpm !== null) {
      for (const index of indices) {
        const p = primaryRpm[index];
        const s = secondaryRpm[index];
        if (Number.isFinite(p) && Number.isFinite(s)) shiftMeasured.push([s, p]);
      }
    }
    const shiftCinder = pairedSimulationSeries(
      run.resultSnapshot,
      'state.secondary_angular_speed',
      'state.primary_angular_speed',
      RAD_PER_S_TO_RPM,
      RAD_PER_S_TO_RPM,
    );

    const powerTimeS = indices.map((index) => data.timeS[index]);
    const primaryPowerRaw = dataColumn(data, 'primary_power_kw');
    const secondaryPowerRaw = dataColumn(data, 'secondary_power_kw');
    const primaryPowerMeasuredKw = primaryPowerRaw === null ? null : indices.map((index) => primaryPowerRaw[index]);
    const secondaryRpmCropped = secondaryRpm === null ? null : indices.map((index) => secondaryRpm[index]);
    const primaryRpmCropped = primaryRpm === null ? null : indices.map((index) => primaryRpm[index]);
    const reconstructedSecondaryPower = secondaryRpmCropped === null
      ? null
      : measuredSecondaryOutputPower(
        powerTimeS,
        secondaryRpmCropped,
        secondaryEquivalentInertia(run.resolvedDocument),
      );
    // Prefer the validation layer's RPM-derived secondary power so measured and
    // CINDER use the same centered five-sample derivative. Retain the imported
    // CSV power only as a fallback for legacy runs without a usable inertia.
    const secondaryPowerMeasuredKw = reconstructedSecondaryPower
      ?? (secondaryPowerRaw === null ? null : indices.map((index) => secondaryPowerRaw[index]));
    const secondaryPowerCinderKw = secondaryBoundaryOutputPowerAtMeasuredTimes(
      run.resultSnapshot,
      run.resolvedDocument,
      powerTimeS,
      run.cropStartS,
    );

    return {
      primary,
      secondary,
      shiftMeasured,
      shiftCinder,
      powerTimeS,
      primaryPowerMeasuredKw,
      primaryPowerCinderKw: simulationSeries(run.resultSnapshot, 'observer.primary_boundary_power', 1 / 1000, run.cropStartS),
      secondaryPowerMeasuredKw,
      secondaryPowerCinderKw,
      efficiencyMeasured: efficiencyVsSpeedRatioFromPower(
        primaryRpmCropped,
        secondaryRpmCropped,
        primaryPowerMeasuredKw,
        secondaryPowerMeasuredKw,
      ),
      efficiencyCinder: cinderEfficiencyVsSpeedRatioAtMeasuredTimes(
        run.resultSnapshot,
        run.resolvedDocument,
        powerTimeS,
        run.cropStartS,
      ),
    };
  }, [run]);

  return (
    <main className={styles.page}>
      <LoadingOverlay isVisible={isLoading} message={loadingMessage} />
      <header className={styles.header}>
        <div className={styles.headerActions}>
          <button type="button" onClick={() => navigate('/validation')}>← Validation setup</button>
          <button type="button" onClick={() => navigate('/')}>Home</button>
          {run !== null && (
            <button type="button" onClick={() => downloadCinderReport(run)}>
              Download CINDER CSV
            </button>
          )}
        </div>
        <div>
          <h1>Dyno validation result</h1>
          {run !== null && (
            <p>
              {run.sourceFilename} · selected {run.cropStartS.toFixed(3)}–{run.cropEndS.toFixed(3)} s
              {' · '}saved {new Date(run.createdAt).toLocaleString()}
            </p>
          )}
        </div>
      </header>

      {error !== null && <section className={styles.errorCard}>{error}</section>}

      {run !== null && !cinderCompletion(run.resultSnapshot).completed && (
        <section className={styles.errorCard}>
          CINDER terminated early after {cinderCompletion(run.resultSnapshot).durationS.toFixed(3)} s: {' '}
          {cinderCompletion(run.resultSnapshot).terminationReason}. Partial results are shown for debugging.
        </section>
      )}

      {run !== null && views !== null && (
        <>
          <section className={styles.summaryCard}>
            <div><span>Validation run</span><strong>{run.id}</strong></div>
            <div><span>CINDER run</span><strong>{run.simulationRunId ?? 'snapshot only'}</strong></div>
            <div><span>Selected duration</span><strong>{(run.cropEndS - run.cropStartS).toFixed(3)} s</strong></div>
            <div>
              <span>CINDER integration</span>
              <strong>{cinderCompletion(run.resultSnapshot).completed ? 'Complete' : 'Stopped early'}</strong>
            </div>
            <div>
              <span>Simulated duration</span>
              <strong>{cinderCompletion(run.resultSnapshot).durationS.toFixed(3)} s</strong>
            </div>
            <div>
              <span>Termination</span>
              <strong>{cinderCompletion(run.resultSnapshot).terminationReason}</strong>
            </div>
            <div>
              <span>Hybrid transitions</span>
              <strong>{run.resultSnapshot.metrics.transition_count}</strong>
            </div>
            <div>
              <span>Transition density</span>
              <strong>
                {cinderCompletion(run.resultSnapshot).durationS > 0
                  ? `${(run.resultSnapshot.metrics.transition_count / cinderCompletion(run.resultSnapshot).durationS).toFixed(1)} /s`
                  : '—'}
              </strong>
            </div>
          </section>

          <section className={styles.sectionHeader}>
            <div>
              <h2>Direct RPM validation</h2>
              <p>Measured shaft speeds are the primary experimental observables.</p>
            </div>
          </section>

          <section className={styles.plotGrid}>
            <article className={styles.resultCard}>
              {views.primary === null ? (
                <p className={styles.signalWarning}>Primary RPM is not available in the saved CSV.</p>
              ) : (
                <>
                  <ValidationTraceChart
                    title="Primary RPM: measured vs CINDER"
                    unit="rpm"
                    timeS={views.primary.timeS}
                    measured={views.primary.measured}
                    measuredLabel="Measured"
                    cropStartS={run.cropStartS}
                    cropEndS={run.cropEndS}
                    simulated={views.primary.simulated}
                    simulatedLabel="CINDER"
                    uncertaintyBySample={views.primary.uncertainty}
                  />
                  <MetricStrip comparison={views.primary} />
                </>
              )}
            </article>

            <article className={styles.resultCard}>
              {views.secondary === null ? (
                <p className={styles.signalWarning}>Secondary RPM is not available in the saved CSV.</p>
              ) : (
                <>
                  <ValidationTraceChart
                    title="Secondary RPM: measured vs CINDER"
                    unit="rpm"
                    timeS={views.secondary.timeS}
                    measured={views.secondary.measured}
                    measuredLabel="Measured"
                    cropStartS={run.cropStartS}
                    cropEndS={run.cropEndS}
                    simulated={views.secondary.simulated}
                    simulatedLabel="CINDER"
                    uncertaintyBySample={views.secondary.uncertainty}
                  />
                  <MetricStrip comparison={views.secondary} />
                </>
              )}
            </article>
          </section>

          <section className={styles.sectionHeader}>
            <div>
              <h2>Shift behaviour and derived energetics</h2>
              <p>Primary power is an imported derived channel. Secondary power is reconstructed from measured RPM with the same centered five-sample derivative used for CINDER; neither is an independent power-sensor measurement.</p>
            </div>
          </section>

          <section className={styles.plotGrid}>
            <article className={styles.resultCard}>
              <ValidationXYChart
                title="Shift curve"
                xLabel="Secondary speed [rpm]"
                yLabel="Primary speed [rpm]"
                measured={views.shiftMeasured}
                simulated={views.shiftCinder}
                note="Parametric trajectory; time remains implicit"
              />
            </article>

            <article className={styles.resultCard}>
              {views.primaryPowerMeasuredKw === null ? (
                <p className={styles.signalWarning}>CSV channel primary_power_kw is not available.</p>
              ) : (
                <ValidationTraceChart
                  title="Primary power: derived experiment vs CINDER"
                  unit="kW"
                  timeS={views.powerTimeS}
                  measured={views.primaryPowerMeasuredKw}
                  measuredLabel="Derived experiment"
                  cropStartS={run.cropStartS}
                  cropEndS={run.cropEndS}
                  simulated={views.primaryPowerCinderKw}
                  simulatedLabel="CINDER boundary power"
                />
              )}
            </article>

            <article className={styles.resultCard}>
              {views.secondaryPowerMeasuredKw === null ? (
                <p className={styles.signalWarning}>CSV channel secondary_power_kw is not available.</p>
              ) : (
                <ValidationTraceChart
                  title="Secondary power: derived experiment vs CINDER"
                  unit="kW"
                  timeS={views.powerTimeS}
                  measured={views.secondaryPowerMeasuredKw}
                  measuredLabel="RPM-derived experiment (5-sample)"
                  cropStartS={run.cropStartS}
                  cropEndS={run.cropEndS}
                  simulated={views.secondaryPowerCinderKw}
                  simulatedLabel="CINDER output (same 5-sample derivative)"
                />
              )}
            </article>

            <article className={styles.resultCard}>
              {views.efficiencyMeasured.length === 0 ? (
                <p className={styles.signalWarning}>The RPM and primary-power channels required to derive efficiency are not available.</p>
              ) : (
                <ValidationXYChart
                  title="Efficiency vs ratio"
                  xLabel="Speed ratio ωp / ωs"
                  yLabel="Efficiency [%]"
                  measured={views.efficiencyMeasured}
                  simulated={views.efficiencyCinder}
                  measuredLabel="Derived experiment"
                  simulatedLabel="CINDER"
                  xMin={0}
                  xMax={6}
                  yMin={0}
                  yMax={120}
                  note="Both efficiencies use the centered five-sample secondary-power derivative at the measured timestamps; ratio is each side's own ωp / ωs"
                />
              )}
            </article>
          </section>
        </>
      )}
    </main>
  );
};
