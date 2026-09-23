import type {
  MeasurementUncertainty,
  ParsedDynoData,
  SignalMetric,
} from './types';

const RPM_TO_RAD_PER_S = (2 * Math.PI) / 60;
export const RAD_PER_S_TO_RPM = 60 / (2 * Math.PI);

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

export function parseDynoCsv(filename: string, rawCsv: string): ParsedDynoData {
  const lines = rawCsv.replace(/\r/g, '').split('\n').filter((line) => line.trim().length > 0);
  if (lines.length < 2) throw new Error('CSV must contain a header and at least one data row.');
  const headers = parseCsvRow(lines[0]);
  if (new Set(headers).size !== headers.length) throw new Error('CSV contains duplicate column names.');
  const columns = Object.fromEntries(headers.map((header) => [header, [] as number[]]));
  for (let rowIndex = 1; rowIndex < lines.length; rowIndex += 1) {
    const row = parseCsvRow(lines[rowIndex]);
    if (row.length !== headers.length) throw new Error(`CSV row ${rowIndex + 1} has ${row.length} columns; expected ${headers.length}.`);
    headers.forEach((header, columnIndex) => {
      const value = Number(row[columnIndex]);
      if (!Number.isFinite(value)) throw new Error(`CSV ${header} row ${rowIndex + 1} is not numeric.`);
      columns[header].push(value);
    });
  }

  const timestampKey = headers.includes('timestamp_ms') ? 'timestamp_ms' : headers.find((header) => /time/i.test(header));
  if (timestampKey === undefined) throw new Error('CSV needs timestamp_ms or another time-like numeric column.');
  const rawTime = columns[timestampKey];
  const scale = timestampKey === 'timestamp_ms' ? 1 / 1000 : 1;
  const origin = rawTime[0];
  const timeS = rawTime.map((value) => (value - origin) * scale);
  for (let index = 1; index < timeS.length; index += 1) {
    if (timeS[index] <= timeS[index - 1]) throw new Error('CSV timestamps must be strictly increasing.');
  }
  return { filename, rawCsv, timeS, columns };
}

export function nearestIndex(timeS: number[], targetS: number): number {
  let best = 0;
  let bestDistance = Number.POSITIVE_INFINITY;
  timeS.forEach((time, index) => {
    const distance = Math.abs(time - targetS);
    if (distance < bestDistance) {
      best = index;
      bestDistance = distance;
    }
  });
  return best;
}

export function croppedIndices(timeS: number[], startS: number, endS: number): number[] {
  return timeS.map((time, index) => ({ time, index }))
    .filter(({ time }) => time >= startS && time <= endS)
    .map(({ index }) => index);
}

export function rpmToRadPerS(rpm: number): number {
  return rpm * RPM_TO_RAD_PER_S;
}

export function interpolate(x: number[], y: number[], query: number): number | null {
  if (x.length === 0 || y.length !== x.length || query < x[0] || query > x[x.length - 1]) return null;
  let lo = 0;
  let hi = x.length - 1;
  while (hi - lo > 1) {
    const mid = Math.floor((lo + hi) / 2);
    if (x[mid] <= query) lo = mid;
    else hi = mid;
  }
  if (query === x[hi]) return y[hi];
  if (x[hi] === x[lo]) return y[lo];
  const alpha = (query - x[lo]) / (x[hi] - x[lo]);
  return y[lo] + alpha * (y[hi] - y[lo]);
}

export function resampleLinear(
  timeS: number[],
  values: number[],
  startS: number,
  endS: number,
  intervalS: number,
): Array<[number, number]> {
  if (!(intervalS > 0) || !Number.isFinite(intervalS)) return [];
  if (!(endS > startS)) return [];
  const samples: Array<[number, number]> = [];
  const epsilon = Math.max(1e-12, intervalS * 1e-9);
  for (let index = 0; ; index += 1) {
    const time = startS + index * intervalS;
    if (time >= endS - epsilon) break;
    const value = interpolate(timeS, values, time);
    if (value !== null && Number.isFinite(value)) samples.push([time, value]);
  }
  const endValue = interpolate(timeS, values, endS);
  if (endValue !== null && Number.isFinite(endValue)) samples.push([endS, endValue]);
  return samples;
}

/**
 * Conservative RPM uncertainty for a single-tooth-period estimate.
 *
 * If one tooth interval is Δt and each endpoint timestamp has a ±δt bound,
 * the interval has a conservative ±2δt bound.  We propagate that bound through
 * n = 60 / (N Δt) exactly, then report the larger of the upper/lower RPM errors.
 */
export function rpmToothTimingUncertainty(
  rpm: number,
  teethPerRevolution: number,
  timestampUncertaintyS: number,
): number | null {
  const speed = Math.abs(rpm);
  if (!Number.isFinite(speed)) return null;
  if (speed === 0) return 0;
  if (!(teethPerRevolution > 0) || !Number.isFinite(teethPerRevolution)) return null;
  if (!(timestampUncertaintyS >= 0) || !Number.isFinite(timestampUncertaintyS)) return null;

  const toothIntervalS = 60 / (teethPerRevolution * speed);
  const intervalBoundS = 2 * timestampUncertaintyS;
  if (!(toothIntervalS > intervalBoundS)) return null;

  const fast = 60 / (teethPerRevolution * (toothIntervalS - intervalBoundS));
  const slow = 60 / (teethPerRevolution * (toothIntervalS + intervalBoundS));
  return Math.max(fast - speed, speed - slow);
}

export function measurementUncertaintySeries(
  values: number[],
  uncertainty: MeasurementUncertainty,
): Array<number | null> | undefined {
  if (uncertainty.status !== 'known') return undefined;

  if (uncertainty.model === 'rpm_tooth_timing') {
    const teeth = uncertainty.teethPerRevolution;
    const timestamp = uncertainty.timestampUncertaintyS;
    if (teeth === undefined || timestamp === undefined) return undefined;
    return values.map((rpm) => rpmToothTimingUncertainty(rpm, teeth, timestamp));
  }

  if (uncertainty.absolute !== undefined && Number.isFinite(uncertainty.absolute) && uncertainty.absolute >= 0) {
    return values.map(() => uncertainty.absolute ?? null);
  }

  return undefined;
}

export function summarizeUncertainty(values: Array<number | null> | undefined): {
  minimum: number;
  median: number;
  maximum: number;
} | null {
  if (values === undefined) return null;
  const finite = values.filter((value): value is number => typeof value === 'number' && Number.isFinite(value));
  if (finite.length === 0) return null;
  const sorted = [...finite].sort((left, right) => left - right);
  const middle = Math.floor(sorted.length / 2);
  const median = sorted.length % 2 === 0
    ? 0.5 * (sorted[middle - 1] + sorted[middle])
    : sorted[middle];
  return {
    minimum: sorted[0],
    median,
    maximum: sorted[sorted.length - 1],
  };
}

export function errorMetrics(reference: number[], predicted: Array<number | null>): SignalMetric {
  const errors = reference.map((value, index) => {
    const prediction = predicted[index];
    return prediction === null || !Number.isFinite(prediction) ? null : prediction - value;
  }).filter((value): value is number => value !== null);
  if (errors.length === 0) return { bias: Number.NaN, mae: Number.NaN, rmse: Number.NaN, maxAbs: Number.NaN, count: 0 };
  const bias = errors.reduce((sum, value) => sum + value, 0) / errors.length;
  const mae = errors.reduce((sum, value) => sum + Math.abs(value), 0) / errors.length;
  const rmse = Math.sqrt(errors.reduce((sum, value) => sum + value * value, 0) / errors.length);
  const maxAbs = Math.max(...errors.map(Math.abs));
  return { bias, mae, rmse, maxAbs, count: errors.length };
}
