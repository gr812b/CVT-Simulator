import type { RunStatus } from '../experiments/api';
import type { RunInspection } from './api';

export type RunOutcome = NonNullable<RunStatus['outcome']>;
type OutcomeSource = Pick<RunStatus, 'id' | 'status'> &
  Partial<Pick<RunStatus, 'outcome' | 'error' | 'has_result' | 'summary_scalars'>>;
type InspectionContext = Pick<RunInspection, 'availability' | 'termination_reason'>;

const pending = (status: RunStatus['status']) =>
  status === 'queued' || status === 'validating' || status === 'running';
const record = (value: unknown): Record<string, unknown> =>
  typeof value === 'object' && value !== null && !Array.isArray(value)
    ? value as Record<string, unknown>
    : {};
const finite = (value: unknown) =>
  typeof value === 'number' && Number.isFinite(value) ? value : null;

/** The server owns diagnosis. The fallback keeps older saved responses safe to display. */
export function describeRunOutcome(
  run: OutcomeSource,
  inspection?: InspectionContext,
): RunOutcome {
  const active = pending(run.status);
  if (run.outcome && (run.outcome.category === 'pending') === active)
    return run.outcome;

  const metrics = record(run.summary_scalars?.metrics);
  const savedReason = inspection?.termination_reason ?? metrics.termination_reason;
  // A terminal error takes precedence over the last running checkpoint's label.
  const reason = active ? run.status : run.error?.code ??
    (typeof savedReason === 'string' && !['running', 'checkpoint'].includes(savedReason)
      ? savedReason : 'unknown');
  const hasData = Boolean(run.has_result || inspection?.availability.preview);
  const partial = hasData && (active || run.status !== 'completed' ||
    inspection?.availability.partial === true || metrics.completed === false);
  const base = {
    reason,
    has_data: hasData,
    partial,
    reached_time_s: hasData ? finite(metrics.duration_s) : null,
    reached_distance_m: hasData ? finite(metrics.vehicle_distance_final_m) : null,
    support_run_id: run.id,
    action: null,
  };
  if (active)
    return { ...base, category: 'pending', severity: 'info',
      title: run.status === 'running' ? 'Simulation running' : 'Waiting to run',
      message: 'The run continues on the server. Activity will show its outcome.' };
  if (run.status === 'cancelled')
    return { ...base, category: 'cancelled', severity: 'info', title: 'Run cancelled',
      message: 'The simulation was stopped by request.' };
  if (run.status === 'timed_out')
    return { ...base, category: 'resource_limit', severity: 'warning', title: 'Run limit reached',
      message: 'The run reached the server’s execution limit.',
      action: 'Try a shorter simulation or ask the maintainer to review the run limit.' };
  if (['time_limit', 'rollback_limit', 'no_forward_progress'].includes(reason))
    return { ...base, category: 'vehicle_stopped', severity: 'warning', title: 'Course not completed',
      message: reason === 'rollback_limit' ? 'The vehicle reached the course’s rollback limit.'
        : reason === 'no_forward_progress' ? 'The vehicle stopped making forward progress.'
        : 'The vehicle did not finish the course within the allowed simulated time.',
      action: 'Review the saved trajectory and compare the vehicle setup with the course requirements.' };
  if (reason === 'mechanism_contact_unsupported')
    return { ...base, category: 'model_limit', severity: 'warning', title: 'Model limit reached',
      message: 'CINDER encountered a contact condition that this version does not model.',
      action: 'Review the saved trajectory and share the run ID with the maintainer.' };
  if (['maximum_transitions', 'numerical_failure', 'integration_failed'].includes(reason))
    return { ...base, category: 'numerical_error', severity: 'error', title: 'Solver stopped early',
      message: 'The numerical solver could not continue this simulation.',
      action: 'Share the run ID with the maintainer if the problem continues.' };
  if (run.status === 'completed' && !partial)
    return { ...base, category: 'success', severity: 'success', title: 'Run completed',
      message: 'The simulation reached its requested finish condition.' };
  return { ...base, category: 'internal_error', severity: 'error', title: 'Simulation error',
    message: 'The simulation stopped because of an internal error. The available information does not identify an input you need to change.',
    action: 'Try again, or share the run ID with the maintainer so the error can be investigated.' };
}

const labels: Record<RunOutcome['category'], string> = {
  pending: 'In progress',
  success: 'Completed',
  vehicle_stopped: 'Course not completed',
  model_limit: 'Model limit',
  numerical_error: 'Solver error',
  configuration_error: 'Check configuration',
  internal_error: 'Simulation error',
  service_error: 'Service interrupted',
  cancelled: 'Cancelled',
  resource_limit: 'Run limit reached',
};

export function outcomeLabel(outcome: RunOutcome, status?: RunStatus['status']) {
  return outcome.category === 'pending' && status
    ? status.replace(/_/g, ' ')
    : labels[outcome.category];
}

export function outcomeProgress(outcome: RunOutcome): string | null {
  if (!outcome.has_data) return null;
  const format = (value: number) => new Intl.NumberFormat(undefined, {
    maximumFractionDigits: 3,
  }).format(value);
  const time = finite(outcome.reached_time_s);
  const distance = finite(outcome.reached_distance_m);
  const parts = [
    time === null ? null : `Saved through ${format(time)} s of simulated time`,
    distance === null ? null : `road position ${format(distance)} m`,
  ].filter(Boolean);
  return parts.length ? `${parts.join(' · ')}.` : null;
}

export function outcomeDataMessage(
  outcome: RunOutcome,
  availability?: RunInspection['availability'],
): string {
  if (outcome.category === 'pending')
    return outcome.has_data ? 'Charts show the latest saved progress.' : 'No saved progress yet.';
  if (!outcome.has_data)
    return 'No simulation data was saved. Playback is unavailable.';
  if (availability && !availability.full_result)
    return availability.preview
      ? 'A saved preview is available in the run details. Full playback and report exports are unavailable.'
      : 'The recorded trajectory is no longer available for playback. Its summary and frozen inputs remain available.';
  if (!availability)
    return outcome.partial
      ? 'Partial result: only the saved portion is available. Open the run details to see its playback and export options.'
      : 'Simulation data was saved. Open the run details to see its playback and export options.';
  return outcome.partial
    ? 'Partial result: playback and exports contain only the saved portion of this run.'
    : 'The saved result is available for playback and export.';
}
