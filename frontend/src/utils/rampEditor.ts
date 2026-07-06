import type { JsonValue } from '@utils/jsonPointer';
export type RampEditorSegment =
  | { type: 'linear'; length: number; angle: number }
  | { type: 'circular'; length: number; angle_start: number; angle_end: number; quadrant: 1 | 2 };

export interface RampEditorValue { segments: RampEditorSegment[]; }

type CinderSegment = Record<string, unknown>;
type CinderRamp = { kind: 'piecewise_ramp'; segments: CinderSegment[] };
const RAD_TO_DEG = 180 / Math.PI;
const DEG_TO_RAD = Math.PI / 180;

export function rampToEditor(value: unknown): RampEditorValue {
  const ramp = value as CinderRamp;
  const segments = Array.isArray(ramp?.segments) ? ramp.segments : [];
  return {
    segments: segments.map((segment): RampEditorSegment => {
      if (segment.kind === 'circular_segment') {
        return {
          type: 'circular',
          length: Number(segment.length_m ?? 0),
          angle_start: Number(segment.angle_start_rad ?? 0) * RAD_TO_DEG,
          angle_end: Number(segment.angle_end_rad ?? 0) * RAD_TO_DEG,
          quadrant: Number(segment.quadrant) === -1 ? 2 : 1,
        };
      }
      return { type: 'linear', length: Number(segment.length_m ?? 0), angle: Number(segment.angle_rad ?? 0) * RAD_TO_DEG };
    }),
  };
}

export function editorToRamp(value: RampEditorValue): JsonValue {
  return {
    kind: 'piecewise_ramp',
    segments: value.segments.map((segment) => segment.type === 'circular'
      ? {
          kind: 'circular_segment', length_m: segment.length,
          angle_start_rad: segment.angle_start * DEG_TO_RAD,
          angle_end_rad: segment.angle_end * DEG_TO_RAD,
          quadrant: segment.quadrant === 2 ? -1 : 1,
        }
      : { kind: 'linear_segment', length_m: segment.length, angle_rad: segment.angle * DEG_TO_RAD }),
  } as unknown as JsonValue;
}

/** Browser-local preview only; no preview endpoint or solver dependence. */
export function previewRamp(value: RampEditorValue, samplesPerSegment = 40): { x: number[]; y: number[]; slopes: number[] } {
  let x = 0;
  let y = 0;
  const xs = [x]; const ys = [y]; const slopes = [0];
  value.segments.forEach((segment) => {
    const count = Math.max(2, samplesPerSegment);
    for (let index = 1; index <= count; index += 1) {
      const t0 = (index - 1) / count;
      const t1 = index / count;
      const angle0 = segment.type === 'linear'
        ? segment.angle : segment.angle_start + (segment.angle_end - segment.angle_start) * t0;
      const angle1 = segment.type === 'linear'
        ? segment.angle : segment.angle_start + (segment.angle_end - segment.angle_start) * t1;
      const dx = segment.length / count;
      const slope0 = Math.tan(angle0 * DEG_TO_RAD);
      const slope1 = Math.tan(angle1 * DEG_TO_RAD);
      y += 0.5 * (slope0 + slope1) * dx;
      x += dx;
      xs.push(x); ys.push(y); slopes.push(slope1);
    }
  });
  return { x: xs, y: ys, slopes };
}
