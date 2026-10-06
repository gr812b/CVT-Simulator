import type { Tune, TunePreview } from './api';

/** A result may authorize only the exact geometry-bearing draft it checked. */
export type TuneCheck = {
  inputKey: string;
  validation?: TunePreview['validation'];
  error?: string | null;
};

export function tuneInputKey(value: Pick<Tune, 'cvt_revision_id' | 'values'>): string {
  return JSON.stringify({ cvt_revision_id: value.cvt_revision_id, values: value.values });
}

export function tuneGeometryBlocker(value: Tune, check: TuneCheck | null): string | undefined {
  if (!check || check.inputKey !== tuneInputKey(value)) return 'Checking geometry…';
  if (check.error) return 'Geometry could not be checked. Correct the inputs or retry the preview.';
  if (!check.validation) return 'Checking geometry…';
  const error = check.validation.findings.find(finding => finding.severity === 'error');
  if (check.validation.is_valid !== true || error) {
    return error?.message ?? 'Correct the geometry before saving or using this tune.';
  }
  return undefined;
}
