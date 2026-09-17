import type { ParsedDynoData, SignalMetric } from './types';

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
