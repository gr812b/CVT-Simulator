import type { ReportTable } from '@api/client';
import type { VisualReplaySample } from '@utils/reportReplay';

function finiteNumber(value: number | null | undefined): value is number {
  return typeof value === 'number' && Number.isFinite(value);
}

export function integratedAngularPosition(
  table: ReportTable,
  speedKey: string,
): number[] {
  const time = table.columns.find((column) => column.key === table.axis_key);
  const speed = table.columns.find((column) => column.key === speedKey);
  const angles = new Array<number>(table.row_count).fill(0);

  if (time === undefined || speed === undefined) return angles;

  for (let index = 1; index < table.row_count; index += 1) {
    const t0 = time.values[index - 1];
    const t1 = time.values[index];
    const w0 = speed.values[index - 1];
    const w1 = speed.values[index];

    if (
      finiteNumber(t0)
      && finiteNumber(t1)
      && finiteNumber(w0)
      && finiteNumber(w1)
      && t1 >= t0
    ) {
      angles[index] = angles[index - 1] + 0.5 * (w0 + w1) * (t1 - t0);
    } else {
      angles[index] = angles[index - 1];
    }
  }

  return angles;
}

export function interpolatedArrayValue(
  values: readonly number[],
  sample: Pick<VisualReplaySample, 'lowerIndex' | 'upperIndex' | 'alpha'>,
): number {
  const lower = values[sample.lowerIndex] ?? 0;
  if (sample.lowerIndex === sample.upperIndex) return lower;
  const upper = values[sample.upperIndex] ?? lower;
  return lower + (upper - lower) * Math.min(1, Math.max(0, sample.alpha));
}
