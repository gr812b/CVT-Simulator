import type { Tune, TunePreview } from './api';

/** A quick preview may enable submission only for the exact draft it checked.
 * The server still runs the full construction audit when saving/running.
 */
export type TuneCheck = {
  inputKey: string;
  validation?: TunePreview['validation'];
  error?: string | null;
};

export function tuneInputKey(value: Pick<Tune, 'cvt_revision_id' | 'values'>): string {
  return JSON.stringify({ cvt_revision_id: value.cvt_revision_id, values: value.values });
}

export function tuneGeometryBlocker(value: Tune, check: TuneCheck | null): string | undefined {
  if (!check || check.inputKey !== tuneInputKey(value)) return 'Updating contact preview…';
  if (check.error) return 'Contact preview unavailable. Correct the inputs or retry the preview.';
  if (!check.validation) return 'Updating contact preview…';
  const error = check.validation.findings.find(finding => finding.severity === 'error');
  if (check.validation.is_valid !== true || error) {
    return error?.message ?? 'Correct the contact preview before saving or using this tune.';
  }
  return undefined;
}
