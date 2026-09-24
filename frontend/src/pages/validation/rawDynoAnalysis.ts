import type { ParsedDynoData } from './types';

export const RAW_DYNO_PRIMARY_TEETH = 16;
export const RAW_DYNO_SECONDARY_TEETH = 12;
export const RAW_DYNO_TIMESTAMP_UNCERTAINTY_S = 1e-6;
export const RAW_DYNO_REPLAY_INTERVAL_S = 0.01;
export const SECONDARY_INERTIA_LOW_KG_M2 = 0.3134;
export const SECONDARY_INERTIA_HIGH_KG_M2 = 0.3147;
export const SECONDARY_INERTIA_MID_KG_M2 = 0.5 * (SECONDARY_INERTIA_LOW_KG_M2 + SECONDARY_INERTIA_HIGH_KG_M2);
export const DYNO_ANALYSIS_WINDOWS_MS = [5, 10, 20, 50, 100, 250] as const;
export type DynoAnalysisWindowMs = typeof DYNO_ANALYSIS_WINDOWS_MS[number];
export const RECOMMENDED_DYNO_WINDOW_MS: DynoAnalysisWindowMs = 100;

const FTLB_TO_NM = 1.355817948;
const RAD_PER_S_PER_RPM = (2 * Math.PI) / 60;
const RPM_PER_RAD_PER_S = 60 / (2 * Math.PI);
const DEFAULT_MAX_INTERPOLATION_GAP_S = 0.35;

/**
 * Fallback curve copied from ArielWolle/CVTDynoViewer/src/protocol.ts.
 * Torque values there are ft*lbf.  A validation run's frozen physical engine
 * curve is preferred whenever it is still available in workspaceSnapshot.
 */
const DEFAULT_CH440_CURVE_FTLB: ReadonlyArray<readonly [number, number]> = [
  [1000, 0],
  [1800, 18],
  [2400, 18.5],
  [2600, 18.1],
  [2800, 17.4],
  [3000, 16.6],
  [3200, 15.4],
  [3400, 14.5],
  [3600, 13.5],
  [3950, 10],
  [4000, 0],
];

export interface EngineTorquePoint {
  rpm: number;
  torqueNm: number;
}

export interface DynoTracePoint {
  timeS: number;
  value: number;
  uncertainty?: number;
  lower?: number;
  upper?: number;
}

export interface EfficiencyRatioPoint {
  ratio: number;
  efficiencyPct: number;
  lowerPct: number;
  upperPct: number;
}

export interface DynoWindowAnalysis {
  windowMs: DynoAnalysisWindowMs;
  primaryRpm: DynoTracePoint[];
  secondaryRpm: DynoTracePoint[];
  primaryPowerKw: DynoTracePoint[];
  secondaryPowerKw: DynoTracePoint[];
  ratio: DynoTracePoint[];
  efficiencyPct: DynoTracePoint[];
  efficiencyVsRatio: EfficiencyRatioPoint[];
}

export interface RawDynoHealth {
  primaryReceivedEdges: number;
  secondaryReceivedEdges: number;
  primaryDeviceMissingEdges: number;
  secondaryDeviceMissingEdges: number;
  primaryDownstreamMissingPackets: number;
  secondaryDownstreamMissingPackets: number;
}

export interface DynoAnalysisResult {
  source: 'per_tooth_raw' | 'wide_rpm';
  sourceLabel: string;
  engineCurveSource: string;
  engineCurve: EngineTorquePoint[];
  recommendedWindowMs: DynoAnalysisWindowMs;
  windows: Record<DynoAnalysisWindowMs, DynoWindowAnalysis>;
  health?: RawDynoHealth;
  warnings: string[];
}

interface RawRpmRow {
  firmwareTimeUs: number;
  channel: number;
  seq: number;
  rawValue: number;
  edgeCount: number | null;
}

interface BaseRpmPoint {
  timeS: number;
  rpm: number;
  uncertaintyRpm: number;
}

interface BaseSignals {
  primary: BaseRpmPoint[];
  secondary: BaseRpmPoint[];
  source: 'per_tooth_raw' | 'wide_rpm';
  sourceLabel: string;
  health?: RawDynoHealth;
  warnings: string[];
}

function parseCsvRow(line: string): string[] {
  const cells: string[] = [];
  let cell = '';
  let quoted = false;
  for (let index = 0; index < line.length; index += 1) {
    const char = line[index];
    if (char === '"') {
      if (quoted && line[index + 1] === '"') {
        cell += '"';
        index += 1;
      } else {
        quoted = !quoted;
      }
    } else if (char === ',' && !quoted) {
      cells.push(cell.trim());
      cell = '';
    } else {
      cell += char;
    }
  }
  cells.push(cell.trim());
  return cells;
}

function csvHeaders(rawCsv: string): string[] {
  const first = rawCsv.replace(/\r/g, '').split('\n').find((line) => line.trim().length > 0);
  return first === undefined ? [] : parseCsvRow(first);
}

export function isPerToothDynoCsv(rawCsv: string): boolean {
  const headers = new Set(csvHeaders(rawCsv));
  return headers.has('firmware_t_us')
    && headers.has('channel')
    && headers.has('seq')
    && headers.has('raw_value');
}

export function hasPhysicalEdgeCounter(rawCsv: string): boolean {
  return csvHeaders(rawCsv).includes('edge_count');
}

function numericCell(value: string, row: number, name: string): number {
  const parsed = Number(value);
  if (!Number.isFinite(parsed)) throw new Error(`Raw dyno CSV ${name} row ${row} is not numeric.`);
  return parsed;
}

function parseRawRpmRows(rawCsv: string): RawRpmRow[] {
  const lines = rawCsv.replace(/\r/g, '').split('\n').filter((line) => line.trim().length > 0);
  if (lines.length < 2) throw new Error('Raw dyno CSV must contain a header and at least one row.');
  const headers = parseCsvRow(lines[0]);
  const index = new Map(headers.map((header, i) => [header, i]));
  for (const required of ['firmware_t_us', 'channel', 'seq', 'raw_value']) {
    if (!index.has(required)) throw new Error(`Raw dyno CSV is missing ${required}.`);
  }

  const edgeIndex = index.get('edge_count');
  const result: RawRpmRow[] = [];
  for (let rowIndex = 1; rowIndex < lines.length; rowIndex += 1) {
    const cells = parseCsvRow(lines[rowIndex]);
    if (cells.length !== headers.length) {
      throw new Error(`Raw dyno CSV row ${rowIndex + 1} has ${cells.length} columns; expected ${headers.length}.`);
    }
    const channel = numericCell(cells[index.get('channel') ?? -1], rowIndex + 1, 'channel');
    if (channel !== 0 && channel !== 1) continue;
    result.push({
      firmwareTimeUs: numericCell(cells[index.get('firmware_t_us') ?? -1], rowIndex + 1, 'firmware_t_us'),
      channel,
      seq: numericCell(cells[index.get('seq') ?? -1], rowIndex + 1, 'seq'),
      rawValue: numericCell(cells[index.get('raw_value') ?? -1], rowIndex + 1, 'raw_value'),
      edgeCount: edgeIndex === undefined ? null : numericCell(cells[edgeIndex], rowIndex + 1, 'edge_count'),
    });
  }
  if (result.length === 0) throw new Error('Raw dyno CSV contains no RPM packets on channels 0 or 1.');
  return result;
}

function channelHealth(rows: RawRpmRow[], channel: number): {
  receivedEdges: number;
  deviceMissingEdges: number;
  downstreamMissingPackets: number;
} {
  const channelRows = rows.filter((row) => row.channel === channel);
  let receivedEdges = 0;
  let deviceMissingEdges = 0;
  let downstreamMissingPackets = 0;
  let previous: RawRpmRow | null = null;

  for (const row of channelRows) {
    if (row.rawValue > 0) receivedEdges += 1;
    if (previous !== null) {
      const seqGap = (Math.round(row.seq) - Math.round(previous.seq) - 1) & 0xff;
      downstreamMissingPackets += seqGap;
      if (
        previous.rawValue > 0 && row.rawValue > 0
        && previous.edgeCount !== null && row.edgeCount !== null
      ) {
        const edgeDelta = (Math.round(row.edgeCount) - Math.round(previous.edgeCount)) >>> 0;
        const edgeGap = Math.max(0, edgeDelta - 1);
        deviceMissingEdges += Math.max(0, edgeGap - seqGap);
      }
    }
    previous = row;
  }
  return { receivedEdges, deviceMissingEdges, downstreamMissingPackets };
}

function fullRevolutionRpm(
  rows: RawRpmRow[],
  channel: number,
  teeth: number,
  originUs: number,
): BaseRpmPoint[] {
  const channelRows = rows.filter((row) => row.channel === channel);
  const timestampsByEdge = new Map<number, number>();
  const result: BaseRpmPoint[] = [];
  let fallbackOrdinal = 0;
  let previousSeq: number | null = null;

  for (const row of channelRows) {
    const seqGap = previousSeq === null ? 0 : (Math.round(row.seq) - previousSeq - 1) & 0xff;
    previousSeq = Math.round(row.seq);
    if (row.rawValue === 0) {
      timestampsByEdge.clear();
      fallbackOrdinal = 0;
      continue;
    }

    // Legacy raw logs predate edge_count.  A sequence gap means the physical
    // tooth phase is no longer knowable exactly, so begin a fresh local epoch
    // instead of pretending the next received packet is the next tooth.  New
    // logs use edge_count directly and can bridge downstream packet loss safely.
    if (row.edgeCount === null && seqGap > 0) {
      timestampsByEdge.clear();
      fallbackOrdinal = 0;
    }

    const key = row.edgeCount === null ? fallbackOrdinal : Math.round(row.edgeCount);
    fallbackOrdinal += 1;
    const previousKey = key - teeth;
    const previousUs = timestampsByEdge.get(previousKey);
    timestampsByEdge.set(key, row.firmwareTimeUs);

    if (previousUs === undefined) continue;
    const revolutionDtS = (row.firmwareTimeUs - previousUs) * 1e-6;
    if (!(revolutionDtS > 0)) continue;
    const rpm = 60 / revolutionDtS;
    const uncertaintyRpm = rpm * (Math.sqrt(2) * RAW_DYNO_TIMESTAMP_UNCERTAINTY_S) / revolutionDtS;
    result.push({
      timeS: ((row.firmwareTimeUs + previousUs) * 0.5 - originUs) * 1e-6,
      rpm,
      uncertaintyRpm,
    });

    // Retain only the amount of history required for one-revolution lookup.
    for (const storedKey of timestampsByEdge.keys()) {
      if (storedKey < key - 2 * teeth) timestampsByEdge.delete(storedKey);
    }
  }
  return result;
}

function baseSignalsFromRaw(rawCsv: string): BaseSignals {
  const rows = parseRawRpmRows(rawCsv);
  const originUs = Math.min(...rows.map((row) => row.firmwareTimeUs));
  const primary = fullRevolutionRpm(rows, 0, RAW_DYNO_PRIMARY_TEETH, originUs);
  const secondary = fullRevolutionRpm(rows, 1, RAW_DYNO_SECONDARY_TEETH, originUs);
  if (primary.length < 2 || secondary.length < 2) {
    throw new Error('Per-tooth raw CSV does not contain enough continuous revolutions on both shafts.');
  }

  const primaryHealth = channelHealth(rows, 0);
  const secondaryHealth = channelHealth(rows, 1);
  const warnings: string[] = [];
  if (!hasPhysicalEdgeCounter(rawCsv)) {
    warnings.push('This is a legacy per-tooth log without edge_count; device-side edge loss cannot be separated exactly.');
  }

  return {
    primary,
    secondary,
    source: 'per_tooth_raw',
    sourceLabel: `Per-tooth raw · ${RAW_DYNO_PRIMARY_TEETH}T primary / ${RAW_DYNO_SECONDARY_TEETH}T secondary`,
    health: {
      primaryReceivedEdges: primaryHealth.receivedEdges,
      secondaryReceivedEdges: secondaryHealth.receivedEdges,
      primaryDeviceMissingEdges: primaryHealth.deviceMissingEdges,
      secondaryDeviceMissingEdges: secondaryHealth.deviceMissingEdges,
      primaryDownstreamMissingPackets: primaryHealth.downstreamMissingPackets,
      secondaryDownstreamMissingPackets: secondaryHealth.downstreamMissingPackets,
    },
    warnings,
  };
}

function finitePairs(timeS: number[], values: number[]): BaseRpmPoint[] {
  const result: BaseRpmPoint[] = [];
  const count = Math.min(timeS.length, values.length);
  for (let i = 0; i < count; i += 1) {
    if (Number.isFinite(timeS[i]) && Number.isFinite(values[i])) {
      result.push({ timeS: timeS[i], rpm: values[i], uncertaintyRpm: 0 });
    }
  }
  return result;
}

function baseSignalsFromWide(data: ParsedDynoData): BaseSignals {
  const primaryValues = data.columns.primary_rpm;
  const secondaryValues = data.columns.secondary_rpm;
  if (primaryValues === undefined || secondaryValues === undefined) {
    throw new Error('Dyno analysis requires primary_rpm and secondary_rpm.');
  }
  const primary = finitePairs(data.timeS, primaryValues);
  const secondary = finitePairs(data.timeS, secondaryValues);
  if (primary.length < 2 || secondary.length < 2) throw new Error('Dyno RPM channels are too short to analyze.');
  return {
    primary,
    secondary,
    source: 'wide_rpm',
    sourceLabel: 'Legacy/wide RPM CSV',
    warnings: ['Per-tooth timestamps are unavailable, so RP2040 timing uncertainty and edge-loss diagnostics cannot be reconstructed for this run.'],
  };
}

function bracket(points: BaseRpmPoint[], query: number): [BaseRpmPoint, BaseRpmPoint] | null {
  if (points.length < 2 || query < points[0].timeS || query > points[points.length - 1].timeS) return null;
  let lo = 0;
  let hi = points.length - 1;
  while (hi - lo > 1) {
    const mid = Math.floor((lo + hi) / 2);
    if (points[mid].timeS <= query) lo = mid;
    else hi = mid;
  }
  return [points[lo], points[hi]];
}

function interpolateBase(points: BaseRpmPoint[], query: number): BaseRpmPoint | null {
  const pair = bracket(points, query);
  if (pair === null) return null;
  const [left, right] = pair;
  const span = right.timeS - left.timeS;
  if (!(span > 0) || span > DEFAULT_MAX_INTERPOLATION_GAP_S) return null;
  const alpha = (query - left.timeS) / span;
  return {
    timeS: query,
    rpm: left.rpm + alpha * (right.rpm - left.rpm),
    uncertaintyRpm: left.uncertaintyRpm + alpha * (right.uncertaintyRpm - left.uncertaintyRpm),
  };
}

function uniformRpmTrace(
  points: BaseRpmPoint[],
  intervalMs: number,
  cropStartS?: number,
  cropEndS?: number,
): DynoTracePoint[] {
  const intervalS = intervalMs / 1000;
  const requestedStart = cropStartS ?? points[0].timeS;
  const requestedEnd = cropEndS ?? points[points.length - 1].timeS;
  const start = Math.max(points[0].timeS, requestedStart);
  const end = Math.min(points[points.length - 1].timeS, requestedEnd);
  if (!(end > start)) return [];
  const alignedStart = Math.ceil((start - 1e-12) / intervalS) * intervalS;
  const result: DynoTracePoint[] = [];
  for (let index = 0; ; index += 1) {
    const timeS = alignedStart + index * intervalS;
    if (timeS > end + intervalS * 1e-8) break;
    const sample = interpolateBase(points, timeS);
    if (sample === null) continue;
    result.push({ timeS, value: sample.rpm, uncertainty: sample.uncertaintyRpm });
  }
  return result;
}

function interpolateTrace(points: DynoTracePoint[], query: number): DynoTracePoint | null {
  if (points.length < 2 || query < points[0].timeS || query > points[points.length - 1].timeS) return null;
  let lo = 0;
  let hi = points.length - 1;
  while (hi - lo > 1) {
    const mid = Math.floor((lo + hi) / 2);
    if (points[mid].timeS <= query) lo = mid;
    else hi = mid;
  }
  const left = points[lo];
  const right = points[hi];
  const span = right.timeS - left.timeS;
  if (!(span > 0) || span > DEFAULT_MAX_INTERPOLATION_GAP_S) return null;
  const alpha = (query - left.timeS) / span;
  const uncertaintyLeft = left.uncertainty ?? 0;
  const uncertaintyRight = right.uncertainty ?? 0;
  return {
    timeS: query,
    value: left.value + alpha * (right.value - left.value),
    uncertainty: uncertaintyLeft + alpha * (uncertaintyRight - uncertaintyLeft),
  };
}

function percentileMedian(values: number[]): number {
  if (values.length === 0) return Number.NaN;
  const sorted = [...values].sort((a, b) => a - b);
  const middle = Math.floor(sorted.length / 2);
  return sorted.length % 2 === 0 ? 0.5 * (sorted[middle - 1] + sorted[middle]) : sorted[middle];
}

function nestedObject(value: unknown, path: string[]): Record<string, unknown> | null {
  let current: unknown = value;
  for (const key of path) {
    if (typeof current !== 'object' || current === null || Array.isArray(current)) return null;
    current = (current as Record<string, unknown>)[key];
  }
  return typeof current === 'object' && current !== null && !Array.isArray(current)
    ? current as Record<string, unknown>
    : null;
}

function curveFromBoundary(boundary: Record<string, unknown> | null): EngineTorquePoint[] | null {
  if (boundary === null || !Array.isArray(boundary.points)) return null;
  const points: EngineTorquePoint[] = [];
  for (const raw of boundary.points) {
    if (typeof raw !== 'object' || raw === null || Array.isArray(raw)) continue;
    const record = raw as Record<string, unknown>;
    const omega = record.angular_speed_rad_per_s;
    const torque = record.torque_Nm;
    if (typeof omega !== 'number' || !Number.isFinite(omega) || typeof torque !== 'number' || !Number.isFinite(torque)) continue;
    points.push({ rpm: omega * RPM_PER_RAD_PER_S, torqueNm: torque });
  }
  return points.length >= 2 ? points.sort((a, b) => a.rpm - b.rpm) : null;
}

export function engineCurveFromValidationSnapshots(
  workspaceSnapshot: unknown,
  resolvedDocument: unknown,
): { points: EngineTorquePoint[]; source: string } {
  const workspaceBoundary = nestedObject(workspaceSnapshot, ['setupDocument', 'shaft_boundaries', 'primary']);
  const workspaceCurve = curveFromBoundary(workspaceBoundary);
  if (workspaceCurve !== null) return { points: workspaceCurve, source: 'Frozen validation workspace engine curve' };

  const resolvedBoundary = nestedObject(resolvedDocument, ['shaft_boundaries', 'primary']);
  const resolvedCurve = curveFromBoundary(resolvedBoundary);
  if (resolvedCurve !== null) return { points: resolvedCurve, source: 'Resolved validation engine curve' };

  return {
    points: DEFAULT_CH440_CURVE_FTLB.map(([rpm, torqueFtLb]) => ({ rpm, torqueNm: torqueFtLb * FTLB_TO_NM })),
    source: 'CH440 fallback curve from CVTDynoViewer',
  };
}

function engineTorqueNm(rpm: number, curve: EngineTorquePoint[]): number {
  if (!Number.isFinite(rpm) || rpm <= 0 || curve.length === 0) return 0;
  if (rpm <= curve[0].rpm) return curve[0].torqueNm;
  if (rpm >= curve[curve.length - 1].rpm) return curve[curve.length - 1].torqueNm;
  let lo = 0;
  let hi = curve.length - 1;
  while (hi - lo > 1) {
    const mid = Math.floor((lo + hi) / 2);
    if (curve[mid].rpm <= rpm) lo = mid;
    else hi = mid;
  }
  const span = curve[hi].rpm - curve[lo].rpm;
  if (!(span > 0)) return curve[lo].torqueNm;
  const alpha = (rpm - curve[lo].rpm) / span;
  return curve[lo].torqueNm + alpha * (curve[hi].torqueNm - curve[lo].torqueNm);
}

function primaryPowerAtRpmKw(rpm: number, curve: EngineTorquePoint[]): number {
  return Math.max(0, engineTorqueNm(rpm, curve) * rpm * RAD_PER_S_PER_RPM / 1000);
}

function primaryPowerTrace(rpm: DynoTracePoint[], curve: EngineTorquePoint[]): DynoTracePoint[] {
  return rpm.map((point) => {
    const value = primaryPowerAtRpmKw(point.value, curve);
    const rpmUncertainty = point.uncertainty ?? 0;
    const epsilon = Math.max(0.05, rpmUncertainty || 0.05);
    const slope = (
      primaryPowerAtRpmKw(point.value + epsilon, curve)
      - primaryPowerAtRpmKw(point.value - epsilon, curve)
    ) / (2 * epsilon);
    const uncertainty = Math.abs(slope) * rpmUncertainty;
    return { timeS: point.timeS, value, uncertainty, lower: Math.max(0, value - uncertainty), upper: value + uncertainty };
  });
}

function secondaryPowerTrace(rpm: DynoTracePoint[]): DynoTracePoint[] {
  const result: DynoTracePoint[] = [];
  for (let index = 1; index < rpm.length; index += 1) {
    const previous = rpm[index - 1];
    const current = rpm[index];
    const dt = current.timeS - previous.timeS;
    if (!(dt > 0) || dt > DEFAULT_MAX_INTERPOLATION_GAP_S) continue;
    const omega0 = previous.value * RAD_PER_S_PER_RPM;
    const omega1 = current.value * RAD_PER_S_PER_RPM;
    const sigmaOmega0 = (previous.uncertainty ?? 0) * RAD_PER_S_PER_RPM;
    const sigmaOmega1 = (current.uncertainty ?? 0) * RAD_PER_S_PER_RPM;
    const specificEnergyRate = (omega1 * omega1 - omega0 * omega0) / (2 * dt) / 1000;
    const value = SECONDARY_INERTIA_MID_KG_M2 * specificEnergyRate;
    const timingSigma = (SECONDARY_INERTIA_MID_KG_M2 / dt / 1000) * Math.sqrt(
      (omega1 * sigmaOmega1) ** 2 + (omega0 * sigmaOmega0) ** 2,
    );
    const lowJ = SECONDARY_INERTIA_LOW_KG_M2 * specificEnergyRate;
    const highJ = SECONDARY_INERTIA_HIGH_KG_M2 * specificEnergyRate;
    const lower = Math.min(lowJ, highJ) - timingSigma;
    const upper = Math.max(lowJ, highJ) + timingSigma;
    result.push({
      timeS: 0.5 * (previous.timeS + current.timeS),
      value,
      uncertainty: timingSigma,
      lower,
      upper,
    });
  }
  return result;
}

function ratioTrace(primaryRpm: DynoTracePoint[], secondaryRpm: DynoTracePoint[]): DynoTracePoint[] {
  const result: DynoTracePoint[] = [];
  for (const primary of primaryRpm) {
    const secondary = interpolateTrace(secondaryRpm, primary.timeS);
    if (secondary === null || Math.abs(secondary.value) < 1e-9) continue;
    const value = primary.value / secondary.value;
    const relPrimary = primary.value === 0 ? 0 : (primary.uncertainty ?? 0) / Math.abs(primary.value);
    const relSecondary = (secondary.uncertainty ?? 0) / Math.abs(secondary.value);
    const uncertainty = Math.abs(value) * Math.sqrt(relPrimary * relPrimary + relSecondary * relSecondary);
    result.push({ timeS: primary.timeS, value, uncertainty, lower: value - uncertainty, upper: value + uncertainty });
  }
  return result;
}

function efficiencyTrace(
  primaryPower: DynoTracePoint[],
  secondaryPower: DynoTracePoint[],
  ratio: DynoTracePoint[],
): { time: DynoTracePoint[]; ratio: EfficiencyRatioPoint[] } {
  const time: DynoTracePoint[] = [];
  const ratioPoints: EfficiencyRatioPoint[] = [];
  for (const secondary of secondaryPower) {
    if (!(secondary.value > 0.1)) continue;
    const primary = interpolateTrace(primaryPower, secondary.timeS);
    const speedRatio = interpolateTrace(ratio, secondary.timeS);
    if (primary === null || speedRatio === null || !(primary.value > 1)) continue;
    const primaryUncertainty = primary.uncertainty ?? 0;
    const secondaryLower = Math.max(0, secondary.lower ?? secondary.value);
    const secondaryUpper = Math.max(0, secondary.upper ?? secondary.value);
    const efficiency = 100 * secondary.value / primary.value;
    const lower = 100 * secondaryLower / Math.max(primary.value + primaryUncertainty, 1e-9);
    const upper = 100 * secondaryUpper / Math.max(primary.value - primaryUncertainty, 1e-9);
    if (!Number.isFinite(efficiency) || !Number.isFinite(lower) || !Number.isFinite(upper)) continue;
    const point = {
      timeS: secondary.timeS,
      value: efficiency,
      lower,
      upper,
      uncertainty: 0.5 * Math.max(0, upper - lower),
    };
    time.push(point);
    ratioPoints.push({ ratio: speedRatio.value, efficiencyPct: efficiency, lowerPct: lower, upperPct: upper });
  }
  return { time, ratio: ratioPoints };
}

function cropBase(points: BaseRpmPoint[], startS: number | undefined, endS: number | undefined): BaseRpmPoint[] {
  const start = startS ?? Number.NEGATIVE_INFINITY;
  const end = endS ?? Number.POSITIVE_INFINITY;
  // Keep one point of padding on each side so interpolation reaches the crop boundary.
  const first = points.findIndex((point) => point.timeS >= start);
  let last = -1;
  for (let index = points.length - 1; index >= 0; index -= 1) {
    if (points[index].timeS <= end) { last = index; break; }
  }
  if (first < 0 || last < 0) return [];
  return points.slice(Math.max(0, first - 1), Math.min(points.length, last + 2));
}

export function buildDynoAnalysis(args: {
  rawCsv: string;
  parsedData: ParsedDynoData;
  cropStartS?: number;
  cropEndS?: number;
  workspaceSnapshot?: unknown;
  resolvedDocument?: unknown;
}): DynoAnalysisResult {
  const base = isPerToothDynoCsv(args.rawCsv)
    ? baseSignalsFromRaw(args.rawCsv)
    : baseSignalsFromWide(args.parsedData);
  const engine = engineCurveFromValidationSnapshots(args.workspaceSnapshot, args.resolvedDocument);
  const primaryBase = cropBase(base.primary, args.cropStartS, args.cropEndS);
  const secondaryBase = cropBase(base.secondary, args.cropStartS, args.cropEndS);
  if (primaryBase.length < 2 || secondaryBase.length < 2) throw new Error('Selected crop does not contain enough RPM data for dyno analysis.');

  const windows = {} as Record<DynoAnalysisWindowMs, DynoWindowAnalysis>;
  for (const windowMs of DYNO_ANALYSIS_WINDOWS_MS) {
    const primaryRpm = uniformRpmTrace(primaryBase, windowMs, args.cropStartS, args.cropEndS);
    const secondaryRpm = uniformRpmTrace(secondaryBase, windowMs, args.cropStartS, args.cropEndS);
    const primaryPowerKw = primaryPowerTrace(primaryRpm, engine.points);
    const secondaryPowerKw = secondaryPowerTrace(secondaryRpm);
    const ratio = ratioTrace(primaryRpm, secondaryRpm);
    const efficiency = efficiencyTrace(primaryPowerKw, secondaryPowerKw, ratio);
    windows[windowMs] = {
      windowMs,
      primaryRpm,
      secondaryRpm,
      primaryPowerKw,
      secondaryPowerKw,
      ratio,
      efficiencyPct: efficiency.time,
      efficiencyVsRatio: efficiency.ratio,
    };
  }

  return {
    source: base.source,
    sourceLabel: base.sourceLabel,
    engineCurveSource: engine.source,
    engineCurve: engine.points,
    recommendedWindowMs: RECOMMENDED_DYNO_WINDOW_MS,
    windows,
    health: base.health,
    warnings: base.warnings,
  };
}

function commonGrid(primary: BaseRpmPoint[], secondary: BaseRpmPoint[], intervalS: number): number[] {
  const start = Math.max(primary[0].timeS, secondary[0].timeS);
  const end = Math.min(primary[primary.length - 1].timeS, secondary[secondary.length - 1].timeS);
  if (!(end > start)) return [];
  const alignedStart = Math.ceil((start - 1e-12) / intervalS) * intervalS;
  const result: number[] = [];
  for (let index = 0; ; index += 1) {
    const time = alignedStart + index * intervalS;
    if (time > end + intervalS * 1e-8) break;
    const primarySample = interpolateBase(primary, time);
    const secondarySample = interpolateBase(secondary, time);
    if (primarySample !== null && secondarySample !== null) result.push(time);
  }
  return result;
}

/**
 * Convert the long per-tooth logger CSV into the ordinary wide RPM shape the
 * validation setup already consumes for crop/replay/CINDER comparison.  The
 * original raw CSV is retained verbatim in ParsedDynoData.rawCsv and therefore
 * remains available for the higher-fidelity analysis on the saved-run page.
 */
export function perToothCsvToParsedDynoData(filename: string, rawCsv: string): ParsedDynoData {
  const base = baseSignalsFromRaw(rawCsv);
  const grid = commonGrid(base.primary, base.secondary, RAW_DYNO_REPLAY_INTERVAL_S);
  if (grid.length < 2) throw new Error('Per-tooth raw CSV does not have overlapping primary/secondary RPM data.');
  const timeS: number[] = [];
  const primaryRpm: number[] = [];
  const secondaryRpm: number[] = [];
  for (const time of grid) {
    const primary = interpolateBase(base.primary, time);
    const secondary = interpolateBase(base.secondary, time);
    if (primary === null || secondary === null) continue;
    timeS.push(time);
    primaryRpm.push(primary.rpm);
    secondaryRpm.push(secondary.rpm);
  }
  const count = timeS.length;
  return {
    filename,
    rawCsv,
    timeS,
    columns: {
      timestamp_ms: timeS.map((time) => time * 1000),
      primary_rpm: primaryRpm,
      secondary_rpm: secondaryRpm,
    },
    sourceFormat: 'per_tooth_raw',
    sourceMetadata: {
      primaryTeethPerRevolution: RAW_DYNO_PRIMARY_TEETH,
      secondaryTeethPerRevolution: RAW_DYNO_SECONDARY_TEETH,
      timestampUncertaintyS: RAW_DYNO_TIMESTAMP_UNCERTAINTY_S,
      edgeCountPresent: hasPhysicalEdgeCounter(rawCsv),
    },
  };
}

export function summarizeWindowStability(analysis: DynoAnalysisResult): Array<{
  windowMs: DynoAnalysisWindowMs;
  medianEfficiencyPct: number;
  medianEfficiencyStepPct: number;
  medianSecondaryPowerStepKw: number;
}> {
  return DYNO_ANALYSIS_WINDOWS_MS.map((windowMs) => {
    const window = analysis.windows[windowMs];
    const efficiencies = window.efficiencyPct.map((point) => point.value).filter(Number.isFinite);
    const efficiencySteps = window.efficiencyPct.slice(1).map((point, index) => Math.abs(point.value - window.efficiencyPct[index].value));
    const powerSteps = window.secondaryPowerKw.slice(1).map((point, index) => Math.abs(point.value - window.secondaryPowerKw[index].value));
    return {
      windowMs,
      medianEfficiencyPct: percentileMedian(efficiencies),
      medianEfficiencyStepPct: percentileMedian(efficiencySteps),
      medianSecondaryPowerStepKw: percentileMedian(powerSteps),
    };
  });
}
