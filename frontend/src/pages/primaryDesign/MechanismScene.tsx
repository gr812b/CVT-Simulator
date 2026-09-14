import { useMemo } from 'react';
import type { ConcreteDesignAnalysis } from '@api/primaryDesign';

interface Props {
  analysis: ConcreteDesignAnalysis;
  shiftM: number;
}

const MM = 1000;
const Q_LIMIT_DEG = 90;
const EPS = 1.0e-10;

function numericField(analysis: ConcreteDesignAnalysis, key: string): number[] {
  const raw = analysis.geometry.fields[key] ?? [];
  return raw.map((value) => typeof value === 'number' ? value : Number.NaN);
}

function interpolate(axis: number[], values: number[], x: number): number {
  if (!axis.length || axis.length !== values.length) return Number.NaN;
  if (x < axis[0] || x > axis[axis.length - 1]) return Number.NaN;
  if (x === axis[0]) return values[0];
  if (x === axis[axis.length - 1]) return values[values.length - 1];
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
    const exactAngle = interpolate(axis, q, shiftM);
    const contactAvailable = shiftM <= analysis.contact_valid_travel_m + EPS
      && Number.isFinite(exactAngle);
    const qLimitExceeded = contactAvailable && exactAngle > Q_LIMIT_DEG + 1.0e-8;
    const physicalPoseAvailable = contactAvailable && !qLimitExceeded;

    const exactRollerX = interpolate(axis, cx, shiftM);
    const exactRollerR = interpolate(axis, cr, shiftM);
    const exactPointX = interpolate(axis, contactX, shiftM);
    const exactPointR = interpolate(axis, contactR, shiftM);

    // After a hard invalidity the exact mechanism pose is intentionally not
    // extrapolated. The 90 degree pose is only a clear visual marker for the
    // deployment boundary while the ramp continues through its requested travel.
    const rollerX = physicalPoseAvailable ? exactRollerX : pivotX;
    const rollerR = physicalPoseAvailable
      ? exactRollerR
      : pivotR + analysis.architecture.arm_length_m;
    const angle = physicalPoseAvailable ? exactAngle : Q_LIMIT_DEG;

    const currentRampX = analysis.ramp_surface_open.x_m.map((x) => x + shiftM);
    const openRampX = analysis.ramp_surface_open.x_m;
    const fullRampX = openRampX.map((x) => x + analysis.requested_travel_m);
    const rampR = analysis.ramp_surface_open.r_m;
    const pointAX = (
      analysis.architecture.pivot_axial_position_m
      + analysis.ramp.anchor_axial_from_pivot_m
      + shiftM
    );
    const pointAR = (
      analysis.architecture.pivot_radius_m
      + analysis.ramp.anchor_radial_from_pivot_m
    );
    const failureShiftM = analysis.validity.failure?.shift_m ?? null;
    const failureRampX = failureShiftM === null
      ? []
      : openRampX.map((x) => x + failureShiftM);
    const doubleContact = analysis.validity.failure?.geometry?.kind === 'double_contact'
      ? analysis.validity.failure.geometry
      : null;
    const doubleContactPoints = doubleContact?.contacts ?? [];
    let lastAdmittedIndex = cx.length - 1;
    if (failureShiftM !== null && axis.length) {
      const beforeFailure = axis.findIndex((value) => value >= failureShiftM - EPS);
      if (beforeFailure >= 0) lastAdmittedIndex = Math.max(0, beforeFailure - 1);
    }
    const lastValidRollerX = lastAdmittedIndex >= 0 ? cx[lastAdmittedIndex] : Number.NaN;
    const lastValidRollerR = lastAdmittedIndex >= 0 ? cr[lastAdmittedIndex] : Number.NaN;

    const allX = [
      ...openRampX,
      ...fullRampX,
      ...cx.filter(Number.isFinite),
      ...(doubleContact ? [doubleContact.roller_center_x_m] : []),
      ...doubleContactPoints.map((point) => point.x_m),
      pivotX - analysis.architecture.arm_length_m,
      pivotX + analysis.architecture.arm_length_m,
    ].map((value) => value * MM);
    const allR = [
      0,
      ...rampR.map((value) => value * MM),
      ...cr.filter(Number.isFinite).map((value) => value * MM),
      ...(doubleContact ? [doubleContact.roller_center_r_m * MM] : []),
      ...doubleContactPoints.map((point) => point.r_m * MM),
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
      pointX: exactPointX,
      pointR: exactPointR,
      pointAX,
      pointAR,
      angle,
      exactAngle,
      contactAvailable,
      qLimitExceeded,
      physicalPoseAvailable,
      currentRampX,
      openRampX,
      fullRampX,
      failureRampX,
      rampR,
      pathCx: cx,
      pathCr: cr,
      q90X: pivotX,
      q90R: pivotR + analysis.architecture.arm_length_m,
      rollerRadiusPx: analysis.architecture.roller_radius_m * MM * scale,
      armRadiusPx: analysis.architecture.arm_length_m * MM * scale,
      failureShiftM,
      lastValidRollerX,
      lastValidRollerR,
      doubleContact,
      doubleContactPoints,
    };
  }, [analysis, shiftM]);

  const failure = analysis.validity.failure;
  const runtimeWarning = analysis.validity.warnings.find(
    (warning) => warning.code === 'RUNTIME_MAP_COMPILE_FAILED',
  );
  let statusText: string;
  if (!scene.contactAvailable) {
    statusText = failure
      ? `${failure.message} The requested ramp remains shown through the full travel.`
      : 'No admitted mechanism pose exists at this shift. The requested ramp remains shown.';
  } else if (scene.qLimitExceeded) {
    statusText = 'This shift requires q > 90°. The arm is clamped to the 90° deployment limit for display.';
  } else if (!analysis.validity.valid) {
    const location = failure?.shift_m === null || failure?.shift_m === undefined
      ? ''
      : ` near x = ${(failure.shift_m * MM).toFixed(2)} mm`;
    statusText = failure
      ? `Design fails${location}: ${failure.message}`
      : 'Design is inadmissible.';
  } else if (runtimeWarning) {
    statusText = `Exact contact is admissible through full travel. ${runtimeWarning.message}`;
  } else {
    statusText = 'Full required travel is admissible.';
  }

  const mechanismStroke = scene.physicalPoseAvailable ? 'currentColor' : '#ff8080';

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', gap: 16, marginBottom: 10 }}>
        <div>
          <strong>Axial–radial mechanism section</strong>
          <div style={{ opacity: scene.physicalPoseAvailable ? 0.66 : 0.9, fontSize: 12, color: scene.physicalPoseAvailable ? undefined : '#ff9f9f' }}>
            {statusText}
          </div>
        </div>
        <div style={{ textAlign: 'right', fontVariantNumeric: 'tabular-nums' }}>
          <strong>
            {scene.physicalPoseAvailable
              ? `q = ${scene.angle.toFixed(2)}°`
              : 'q = 90.00° (display limit)'}
          </strong>
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
        {scene.failureRampX.length > 0 && (
          <path
            d={scene.path(scene.failureRampX, scene.rampR)}
            fill="none"
            stroke="#ff6b6b"
            opacity="0.72"
            strokeWidth="2.5"
            strokeDasharray="8 5"
          />
        )}
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
          stroke={mechanismStroke}
          strokeWidth="5"
          strokeLinecap="round"
        />
        <circle
          cx={scene.sx(scene.rollerX)}
          cy={scene.sy(scene.rollerR)}
          r={scene.rollerRadiusPx}
          fill="var(--primary-design-canvas, #0d1319)"
          stroke={mechanismStroke}
          strokeWidth="3"
        />
        {scene.doubleContact && scene.doubleContactPoints.length === 2 && (
          <g>
            <line
              x1={scene.sx(scene.pivotX)}
              y1={scene.sy(scene.pivotR)}
              x2={scene.sx(scene.doubleContact.roller_center_x_m)}
              y2={scene.sy(scene.doubleContact.roller_center_r_m)}
              stroke="#ff5f6d"
              strokeWidth="4"
              opacity="0.86"
            />
            <circle
              cx={scene.sx(scene.doubleContact.roller_center_x_m)}
              cy={scene.sy(scene.doubleContact.roller_center_r_m)}
              r={scene.rollerRadiusPx}
              fill="none"
              stroke="#ff5f6d"
              strokeWidth="3"
            />
            {scene.doubleContactPoints.map((point) => (
              <g key={point.label}>
                <line
                  x1={scene.sx(scene.doubleContact!.roller_center_x_m)}
                  y1={scene.sy(scene.doubleContact!.roller_center_r_m)}
                  x2={scene.sx(point.x_m)}
                  y2={scene.sy(point.r_m)}
                  stroke="#ff9b9b"
                  strokeWidth="2"
                  strokeDasharray="5 4"
                />
                <circle
                  cx={scene.sx(point.x_m)}
                  cy={scene.sy(point.r_m)}
                  r="5"
                  fill="#ff5f6d"
                />
                <text
                  x={scene.sx(point.x_m) + 8}
                  y={scene.sy(point.r_m) - 8}
                  fill="#ffb1b1"
                  fontSize="12"
                  fontWeight="700"
                >
                  {point.label}
                </text>
              </g>
            ))}
            <text
              x={scene.sx(scene.doubleContact.roller_center_x_m) + 12}
              y={scene.sy(scene.doubleContact.roller_center_r_m) + scene.rollerRadiusPx + 18}
              fill="#ff9b9b"
              fontSize="12"
              fontWeight="700"
            >
              instantaneous double contact
            </text>
          </g>
        )}
        {!analysis.validity.valid
          && Number.isFinite(scene.lastValidRollerX)
          && Number.isFinite(scene.lastValidRollerR) && (
          <g>
            <line
              x1={scene.sx(scene.lastValidRollerX) - 8}
              y1={scene.sy(scene.lastValidRollerR) - 8}
              x2={scene.sx(scene.lastValidRollerX) + 8}
              y2={scene.sy(scene.lastValidRollerR) + 8}
              stroke="#ff6b6b"
              strokeWidth="3"
            />
            <line
              x1={scene.sx(scene.lastValidRollerX) - 8}
              y1={scene.sy(scene.lastValidRollerR) + 8}
              x2={scene.sx(scene.lastValidRollerX) + 8}
              y2={scene.sy(scene.lastValidRollerR) - 8}
              stroke="#ff6b6b"
              strokeWidth="3"
            />
            <text
              x={scene.sx(scene.lastValidRollerX) + 12}
              y={scene.sy(scene.lastValidRollerR) + 4}
              fill="#ff9f9f"
              fontSize="12"
            >
              last admitted contact
            </text>
          </g>
        )}
        <circle cx={scene.sx(scene.pivotX)} cy={scene.sy(scene.pivotR)} r="6" fill="currentColor" />
        <circle cx={scene.sx(scene.pointAX)} cy={scene.sy(scene.pointAR)} r="5" fill="#f0c56f" />
        {scene.physicalPoseAvailable && Number.isFinite(scene.pointX) && Number.isFinite(scene.pointR) && (
          <circle cx={scene.sx(scene.pointX)} cy={scene.sy(scene.pointR)} r="5" fill="currentColor" />
        )}
        <text x={scene.sx(scene.pivotX) + 9} y={scene.sy(scene.pivotR) - 10} fill="currentColor" fontSize="13">P</text>
        <text x={scene.sx(scene.pointAX) + 9} y={scene.sy(scene.pointAR) - 9} fill="#f0c56f" fontSize="13">A</text>
        {scene.physicalPoseAvailable && Number.isFinite(scene.pointX) && Number.isFinite(scene.pointR) && (
          <text x={scene.sx(scene.pointX) + 9} y={scene.sy(scene.pointR) - 9} fill="currentColor" fontSize="13">C</text>
        )}
      </svg>
      <div style={{ display: 'flex', justifyContent: 'space-between', opacity: 0.62, fontSize: 11, marginTop: 6 }}>
        <span>ghost: fully open</span>
        <span>solid: requested ramp at selected shift</span>
        <span>red dashed: first failed shift</span>
        <span>ghost: requested full shift</span>
      </div>
    </div>
  );
}
