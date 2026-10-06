import type { TuneField } from './api';

export type RampField = Extract<TuneField, { kind: 'ramp' }>;
export type Ramp = RampField['default'];
export type Stage = { end_m: number; angle_rad: number };
export type AngleStages = { start_angle_rad: number; stages: Stage[] };
export const MIN_HELIX_ANGLE = Math.PI / 18;
export const MAX_PROFILE_ANGLE = 89 * Math.PI / 180;
export const displayAngle = (stored: number, helix: boolean) => helix ? Math.PI / 2 - stored : stored;
export const storedAngle = displayAngle;
const close = (a: number, b: number) => Math.abs(a - b) < 1e-10;

export function endpointAngles(segment: Ramp['segments'][number]): [number, number] {
  switch (segment.kind) {
    case 'linear_segment': return [segment.angle_rad, segment.angle_rad];
    case 'circular_segment': return [Math.atan(Math.tan(segment.angle_start_rad)), Math.atan(Math.tan(segment.angle_end_rad))];
    case 'c3_transition_segment': return [Math.atan(segment.slope_start), Math.atan(segment.slope_end)];
  }
}

/** Reading never rewrites a saved profile. Only zero-derivative joins are guided-editable. */
export function readAngleStages(profile: Ramp): AngleStages | null {
  if (!profile.segments.length) return null;
  let end = 0;
  const start = endpointAngles(profile.segments[0])[0];
  let previous = start;
  const stages: Stage[] = [];
  for (const segment of profile.segments) {
    if (segment.kind === 'circular_segment') return null;
    if (segment.kind === 'c3_transition_segment' && [
      segment.curvature_start_per_m, segment.curvature_end_per_m,
      segment.third_derivative_start_per_m2, segment.third_derivative_end_per_m2,
    ].some(x => x !== 0)) return null;
    const [a, b] = endpointAngles(segment);
    if (!close(a, previous) || !(segment.length_m > 0)) return null;
    stages.push({ end_m: end += segment.length_m, angle_rad: b });
    previous = b;
  }
  return { start_angle_rad: start, stages };
}

/** Shared endpoint angle and zero endpoint derivatives give a C3 join in CINDER. */
export function writeAngleStages(value: AngleStages): Ramp {
  let x = 0, angle = value.start_angle_rad;
  return {
    kind: 'piecewise_ramp',
    segments: value.stages.map(stage => {
      const length_m = stage.end_m - x;
      const start = angle;
      x = stage.end_m; angle = stage.angle_rad;
      return close(start, angle) ? {
        kind: 'linear_segment' as const, length_m, angle_rad: angle,
      } : {
        kind: 'c3_transition_segment' as const, length_m,
        slope_start: Math.tan(start), slope_end: Math.tan(angle),
        curvature_start_per_m: 0, curvature_end_per_m: 0,
        third_derivative_start_per_m2: 0, third_derivative_end_per_m2: 0,
      };
    }),
  };
}

export function constantProfile(length: number, angle: number): Ramp {
  return { kind: 'piecewise_ramp', segments: [{ kind: 'linear_segment', length_m: length, angle_rad: angle }] };
}

/** Explicit conversion only: retain endpoint slopes, replace the interior with smooth joins. */
export function convertToAngleStages(profile: Ramp, used?: [number, number]): Ramp {
  let end = 0;
  const total = profile.segments.reduce((sum, segment) => sum + segment.length_m, 0);
  return writeAngleStages({
    start_angle_rad: endpointAngles(profile.segments[0])[0],
    stages: profile.segments.map((segment, i, segments) => ({
      end_m: used && i < segments.length - 1
        ? used[0] + (used[1] - used[0]) * (i + 1) / segments.length
        : used ? total : (end += segment.length_m),
      angle_rad: endpointAngles(segment)[1],
    })),
  });
}

export function splitStage(value: AngleStages, index: number, used?: [number, number]): AngleStages {
  const next = structuredClone(value);
  const previous = next.stages[index - 1];
  const stage = next.stages[index];
  const start = Math.max(previous?.end_m ?? 0, used?.[0] ?? 0);
  const end = Math.min(stage.end_m, used?.[1] ?? stage.end_m);
  if (!(end > start)) return value;
  // A deliberate edit. Linear stages retain their exact line; a curved stage
  // gains a new smooth join rather than a fabricated derivative value.
  const angle = ((previous?.angle_rad ?? value.start_angle_rad) + stage.angle_rad) / 2;
  next.stages.splice(index, 0, { end_m: (start + end) / 2, angle_rad: angle });
  return next;
}

/** Read the usable helix window without pretending its extra material is travel.
 * Only constant sections may be clipped implicitly. Cutting a curved section or
 * replacing a shaped tail requires the user's explicit conversion.
 */
export function readTravelStages(profile: Ramp, [lo, hi]: [number, number]): AngleStages | null {
  const full = readAngleStages(profile);
  if (!full || !(hi > lo) || lo < 0 || hi > full.stages.at(-1)!.end_m + 1e-10) return null;
  const stages: Stage[] = [];
  let start = 0, angle = full.start_angle_rad, first: number | undefined;
  for (const stage of full.stages) {
    const constant = close(angle, stage.angle_rad);
    if ((start < lo - 1e-10 || stage.end_m > hi + 1e-10) && !constant) return null;
    const left = Math.max(start, lo), right = Math.min(stage.end_m, hi);
    if (right > left + 1e-10) {
      first ??= angle;
      stages.push({ end_m: right, angle_rad: stage.angle_rad });
    }
    start = stage.end_m; angle = stage.angle_rad;
  }
  return first === undefined ? null : { start_angle_rad: first, stages };
}

/** Store travel stages and retain the machined extent as constant end coverage.
 * Stage-end angles now occur at the displayed travel positions, including 100%.
 */
export function writeTravelStages(value: AngleStages, [lo, hi]: [number, number], total: number): Ramp {
  const terminal = value.stages.at(-1);
  if (!terminal || !close(terminal.end_m, hi) || total < hi - 1e-10 || lo < 0) {
    throw new Error('Angle stages must cover the usable helix travel.');
  }
  const segments = writeAngleStages({
    start_angle_rad: value.start_angle_rad,
    stages: value.stages.map(stage => ({ ...stage, end_m: stage.end_m - lo })),
  }).segments;
  if (lo > 1e-10) segments.unshift({ kind: 'linear_segment', length_m: lo, angle_rad: value.start_angle_rad });
  if (total > hi + 1e-10) segments.push({ kind: 'linear_segment', length_m: total - hi, angle_rad: terminal.angle_rad });
  return { kind: 'piecewise_ramp', segments };
}
