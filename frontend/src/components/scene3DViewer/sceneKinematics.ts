import type { SimulationCaseDocument, ReportTable } from '@api/client';
import { valueAt } from '@utils/reportTable';

interface LinearHelixSegment {
  kind: 'linear_segment';
  length_m: number;
  angle_rad: number;
}

interface HelixCouplingView {
  profile: {
    kind: 'helix_profile';
    circumferential_profile: {
      kind: 'piecewise_ramp';
      segments: Array<LinearHelixSegment | { kind: string }>;
    };
    radius_m: number;
  };
  opening_per_axial_position: number;
  opening_offset_m: number;
}

interface HelixAssemblyView {
  geometry: {
    secondary_outer_radius_at_zero_shift_m: number;
    sheave_half_angle_rad: number;
  };
  pulleys: {
    secondary: {
      helical_coupling?: HelixCouplingView;
    };
  };
}

function finiteNumber(value: number | null | undefined): value is number {
  return typeof value === 'number' && Number.isFinite(value);
}

/**
 * Integrate a reported angular-speed channel once for visualization.
 *
 * The report grid may contain duplicate transition timestamps; those simply
 * contribute zero angle because dt=0. Missing/non-finite speed samples hold the
 * previous visual angle rather than inventing a jump.
 */
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

function linearProfileDisplacement(
  coupling: HelixCouplingView,
  openingTravel: number,
): number | null {
  const segments = coupling.profile.circumferential_profile.segments;
  if (!Number.isFinite(openingTravel) || openingTravel < -1e-10) return null;

  let remaining = Math.max(0, openingTravel);
  let displacement = 0;

  for (const rawSegment of segments) {
    if (rawSegment.kind !== 'linear_segment') return null;
    const segment = rawSegment as LinearHelixSegment;
    if (
      !Number.isFinite(segment.length_m)
      || segment.length_m <= 0
      || !Number.isFinite(segment.angle_rad)
    ) {
      return null;
    }

    const travel = Math.min(remaining, segment.length_m);
    displacement += Math.tan(segment.angle_rad) * travel;
    remaining -= travel;
    if (remaining <= 1e-10) return displacement;
  }

  return remaining <= 1e-10 ? displacement : null;
}

function helixTheta(coupling: HelixCouplingView, openingTravel: number): number | null {
  if (!Number.isFinite(coupling.profile.radius_m) || coupling.profile.radius_m <= 0) {
    return null;
  }
  const displacement = linearProfileDisplacement(coupling, openingTravel);
  return displacement === null ? null : -displacement / coupling.profile.radius_m;
}

/**
 * Relative movable-secondary clocking caused by the physical helix.
 *
 * CINDER's conventional secondary coordinate is positive closing:
 *   x_s = 2 tan(beta) [r_s,out - r_s,out(0)]
 * and the installed coupling maps x_s into positive opening travel q.
 *
 * This helper restores the visual relative rotation that the legacy playback
 * received directly from the helix-force breakdown. It is intentionally
 * separate from shaft spin so hiding shaft rotation still leaves the mechanism
 * motion visible.
 *
 * Current released/seeded CINDER helix documents use linear piecewise-ramp
 * segments. If a future assembly uses a nonlinear segment, this visual helper
 * safely returns zero until CINDER exports relative helix angle directly.
 */
export function secondaryHelixRelativeAngle(
  document: SimulationCaseDocument,
  table: ReportTable,
  frameIndex: number,
): number {
  const assembly = document.assembly as unknown as HelixAssemblyView;
  const coupling = assembly.pulleys?.secondary?.helical_coupling;
  if (coupling === undefined) return 0;

  const secondaryOuterRadius = valueAt(
    table,
    'geometry.secondary_outer_radius',
    frameIndex,
  );
  if (!finiteNumber(secondaryOuterRadius)) return 0;

  const geometry = assembly.geometry;
  const localAxialPosition = 2
    * Math.tan(geometry.sheave_half_angle_rad)
    * (
      secondaryOuterRadius
      - geometry.secondary_outer_radius_at_zero_shift_m
    );

  const currentOpening = coupling.opening_offset_m
    + coupling.opening_per_axial_position * localAxialPosition;
  const initialOpening = coupling.opening_offset_m;

  const currentTheta = helixTheta(coupling, currentOpening);
  const initialTheta = helixTheta(coupling, initialOpening);
  if (currentTheta === null || initialTheta === null) return 0;

  return currentTheta - initialTheta;
}
