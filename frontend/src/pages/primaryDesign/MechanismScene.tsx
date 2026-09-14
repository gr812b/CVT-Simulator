import { useMemo } from 'react';
import type { ConcreteDesignAnalysis } from '@api/primaryDesign';

interface Props {
  analysis: ConcreteDesignAnalysis;
  shiftM: number;
}

const MM = 1000;

function numericField(analysis: ConcreteDesignAnalysis, key: string): number[] {
  const raw = analysis.geometry.fields[key] ?? [];
  return raw.map((value) => typeof value === 'number' ? value : Number.NaN);
}

function interpolate(axis: number[], values: number[], x: number): number {
  if (!axis.length || axis.length !== values.length) return Number.NaN;
  if (x <= axis[0]) return values[0];
  if (x >= axis[axis.length - 1]) return values[values.length - 1];
  let lo = 0;
  let hi = axis.length - 1;
  while (hi - lo > 1) {
    const mid = Math.floor((lo + hi) / 2);
    if (axis[mid] <= x) lo = mid;
    else hi = mid;
  }
  const span = axis[hi] - axis[lo];
  const t = span === 0 ? 0 : (x - axis[lo]) / span;
  return values[lo] + t * (values[hi] - values[lo]);
}

export function MechanismScene({ analysis, shiftM }: Props) {
  const scene = useMemo(() => {
    const axis = analysis.geometry.axis_values;
    const cx = numericField(analysis, 'roller_center_x_m');
    const cr = numericField(analysis, 'roller_center_r_m');
    const contactX = numericField(analysis, 'contact_x_m');
    const contactR = numericField(analysis, 'contact_r_m');
    const q = numericField(analysis, 'arm_angle_deg');

    const pivotX = analysis.architecture.pivot_axial_position_m;
    const pivotR = analysis.architecture.pivot_radius_m;
    const rollerX = interpolate(axis, cx, shiftM);
    const rollerR = interpolate(axis, cr, shiftM);
    const pointX = interpolate(axis, contactX, shiftM);
    const pointR = interpolate(axis, contactR, shiftM);
    const angle = interpolate(axis, q, shiftM);

    const currentRampX = analysis.ramp_surface_open.x_m.map((x) => x + shiftM);
    const openRampX = analysis.ramp_surface_open.x_m;
    const fullRampX = openRampX.map((x) => x + analysis.requested_travel_m);
    const rampR = analysis.ramp_surface_open.r_m;

    const allX = [
      ...openRampX,
      ...fullRampX,
      ...cx,
      pivotX - analysis.architecture.arm_length_m,
      pivotX + analysis.architecture.arm_length_m,
    ].map((value) => value * MM);
    const allR = [
      0,
      ...rampR.map((value) => value * MM),
      ...cr.map((value) => value * MM),
      (pivotR + analysis.architecture.arm_length_m + analysis.architecture.roller_radius_m) * MM,
    ];

    const minX = Math.min(...allX) - 8;
    const maxX = Math.max(...allX) + 8;
    const minR = Math.min(...allR) - 6;
    const maxR = Math.max(...allR) + 8;
    const width = 900;
    const height = 520;
    const scale = Math.min(width / (maxX - minX), height / (maxR - minR));
    const sx = (xM: number) => (xM * MM - minX) * scale;
    const sy = (rM: number) => height - (rM * MM - minR) * scale;
    const path = (xs: number[], rs: number[]) => xs.map((x, index) => {
      const command = index === 0 ? 'M' : 'L';
      return `${command}${sx(x).toFixed(2)},${sy(rs[index]).toFixed(2)}`;
    }).join(' ');

    return {
      width,
      height,
      sx,
      sy,
      path,
      pivotX,
      pivotR,
      rollerX,
      rollerR,
      pointX,
      pointR,
      angle,
      currentRampX,
      openRampX,
      fullRampX,
      rampR,
      pathCx: cx,
      pathCr: cr,
      q90X: pivotX,
      q90R: pivotR + analysis.architecture.arm_length_m,
      rollerRadiusPx: analysis.architecture.roller_radius_m * MM * scale,
      armRadiusPx: analysis.architecture.arm_length_m * MM * scale,
    };
  }, [analysis, shiftM]);

  const failure = analysis.validity.failure;
  const statusText = analysis.validity.valid
    ? 'Full required travel is admissible.'
    : failure?.message ?? 'Design is inadmissible.';

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', gap: 16, marginBottom: 10 }}>
        <div>
          <strong>Axial–radial mechanism section</strong>
          <div style={{ opacity: 0.66, fontSize: 12 }}>{statusText}</div>
        </div>
        <div style={{ textAlign: 'right', fontVariantNumeric: 'tabular-nums' }}>
          <strong>q = {scene.angle.toFixed(2)}°</strong>
          <div style={{ opacity: 0.66, fontSize: 12 }}>90° is a hard deployment limit</div>
        </div>
      </div>
      <svg
        viewBox={`0 0 ${scene.width} ${scene.height}`}
        role="img"
        aria-label="Fixed-pivot primary mechanism"
        style={{ width: '100%', height: 'auto', display: 'block' }}
      >
        <rect width={scene.width} height={scene.height} rx="12" fill="var(--primary-design-canvas, #0d1319)" />
        <line
          x1={0}
          y1={scene.sy(0)}
          x2={scene.width}
          y2={scene.sy(0)}
          stroke="currentColor"
          opacity="0.22"
          strokeDasharray="7 7"
        />
        <path
          d={scene.path(scene.openRampX, scene.rampR)}
          fill="none"
          stroke="currentColor"
          opacity="0.18"
          strokeWidth="2"
          strokeDasharray="6 6"
        />
        <path
          d={scene.path(scene.fullRampX, scene.rampR)}
          fill="none"
          stroke="currentColor"
          opacity="0.18"
          strokeWidth="2"
          strokeDasharray="3 7"
        />
        <path
          d={scene.path(scene.currentRampX, scene.rampR)}
          fill="none"
          stroke="currentColor"
          opacity="0.95"
          strokeWidth="4"
        />
        <path
          d={scene.path(scene.pathCx, scene.pathCr)}
          fill="none"
          stroke="currentColor"
          opacity="0.24"
          strokeWidth="2"
          strokeDasharray="4 6"
        />
        <circle
          cx={scene.sx(scene.pivotX)}
          cy={scene.sy(scene.pivotR)}
          r={scene.armRadiusPx}
          fill="none"
          stroke="currentColor"
          opacity="0.12"
          strokeDasharray="5 7"
        />
        <line
          x1={scene.sx(scene.pivotX)}
          y1={scene.sy(scene.pivotR)}
          x2={scene.sx(scene.q90X)}
          y2={scene.sy(scene.q90R)}
          stroke="currentColor"
          opacity="0.38"
          strokeWidth="2"
          strokeDasharray="8 7"
        />
        <text
          x={scene.sx(scene.q90X) + 8}
          y={scene.sy(scene.q90R) + 18}
          fill="currentColor"
          opacity="0.65"
          fontSize="13"
        >
          q = 90° limit
        </text>
        <line
          x1={scene.sx(scene.pivotX)}
          y1={scene.sy(scene.pivotR)}
          x2={scene.sx(scene.rollerX)}
          y2={scene.sy(scene.rollerR)}
          stroke="currentColor"
          strokeWidth="5"
          strokeLinecap="round"
        />
        <circle
          cx={scene.sx(scene.rollerX)}
          cy={scene.sy(scene.rollerR)}
          r={scene.rollerRadiusPx}
          fill="var(--primary-design-canvas, #0d1319)"
          stroke="currentColor"
          strokeWidth="3"
        />
        <circle cx={scene.sx(scene.pivotX)} cy={scene.sy(scene.pivotR)} r="6" fill="currentColor" />
        <circle cx={scene.sx(scene.pointX)} cy={scene.sy(scene.pointR)} r="5" fill="currentColor" />
        <text x={scene.sx(scene.pivotX) + 9} y={scene.sy(scene.pivotR) - 10} fill="currentColor" fontSize="13">P</text>
        <text x={scene.sx(scene.pointX) + 9} y={scene.sy(scene.pointR) - 9} fill="currentColor" fontSize="13">C</text>
      </svg>
      <div style={{ display: 'flex', justifyContent: 'space-between', opacity: 0.62, fontSize: 11, marginTop: 6 }}>
        <span>ghost: fully open</span>
        <span>solid: selected shift</span>
        <span>ghost: requested full shift</span>
      </div>
    </div>
  );
}
