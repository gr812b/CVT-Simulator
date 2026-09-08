import type { ReportColumn, ReportTable } from '@api/client';

export function reportColumn(table: ReportTable, key: string): ReportColumn | undefined {
  return table.columns.find((column) => column.key === key);
}

export function requireReportColumn(table: ReportTable, key: string): ReportColumn {
  const column = reportColumn(table, key);
  if (column === undefined) throw new Error(`CINDER report table does not contain '${key}'.`);
  return column;
}

export function reportAxisTimes(table: ReportTable): number[] {
  const axis = requireReportColumn(table, table.axis_key);
  if (axis.values.length !== table.row_count) {
    throw new Error(`CINDER report axis '${table.axis_key}' has ${axis.values.length} rows; expected ${table.row_count}.`);
  }
  let previous = 0;
  return axis.values.map((value, index) => {
    if (typeof value !== 'number' || !Number.isFinite(value)) {
      throw new Error(`CINDER report axis '${table.axis_key}' contains a non-finite time at row ${index}.`);
    }
    if (index > 0 && value < previous) {
      throw new Error(`CINDER report axis '${table.axis_key}' is not time ordered at row ${index}.`);
    }
    previous = value;
    return value;
  });
}

export function reportValue(column: ReportColumn | undefined, index: number): number | null {
  if (column === undefined || index < 0 || index >= column.values.length) return null;
  return column.values[index];
}

export function numericPairs(table: ReportTable, xKey: string, yKey: string): Array<[number, number]> {
  const x = reportColumn(table, xKey);
  const y = reportColumn(table, yKey);
  if (x === undefined || y === undefined) return [];
  const count = Math.min(x.values.length, y.values.length);
  const pairs: Array<[number, number]> = [];
  for (let index = 0; index < count; index += 1) {
    const xValue = x.values[index];
    const yValue = y.values[index];
    if (xValue !== null && yValue !== null) pairs.push([xValue, yValue]);
  }
  return pairs;
}

export function reportRows(table: ReportTable): Array<Record<string, number | null>> {
  return Array.from({ length: table.row_count }, (_, index) => Object.fromEntries(
    table.columns.map((column) => [column.key, column.values[index] ?? null]),
  ));
}

export function valueAt(table: ReportTable, key: string, index: number): number | null {
  return reportValue(reportColumn(table, key), index);
}

export function interpolatedValue(
  table: ReportTable,
  key: string,
  lowerIndex: number,
  upperIndex: number,
  alpha: number,
): number | null {
  const lower = valueAt(table, key, lowerIndex);
  if (lowerIndex === upperIndex) return lower;

  const upper = valueAt(table, key, upperIndex);
  const mix = Math.min(1, Math.max(0, alpha));

  if (mix <= 0) return lower;
  if (mix >= 1) return upper;
  if (
    typeof lower !== 'number'
    || !Number.isFinite(lower)
    || typeof upper !== 'number'
    || !Number.isFinite(upper)
  ) {
    return null;
  }

  return lower + (upper - lower) * mix;
}
