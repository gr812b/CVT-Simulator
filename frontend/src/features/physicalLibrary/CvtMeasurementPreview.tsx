import { Paper, Stack, Text } from '@mantine/core';
import type { CvtData } from './api';
import { primaryFixedPivot, primaryShaftRadius } from './cvtHardware';
import {
  CVT_MEASUREMENT_LABELS,
  cvtMeasurementKeyForPath,
  type CvtMeasurementKey,
} from './cvtMeasurementPreviewModel';

const WIDTH = 560;
const HEIGHT = 310;
const LEFT = 76;
const RIGHT = 522;
const TOP = 34;
const CENTRELINE_Y = 262;

function clamp(value: number, low: number, high: number) {
  return Math.max(low, Math.min(high, value));
}

function lineStroke(active: boolean) {
  return active
    ? 'var(--mantine-primary-color-filled)'
    : 'var(--mantine-color-gray-6)';
}

function labelFill(active: boolean) {
  return active
    ? 'var(--mantine-primary-color-filled)'
    : 'var(--mantine-color-text)';
}

function ArrowLine({
  x1,
  y1,
  x2,
  y2,
  active,
  dashed = false,
}: {
  x1: number;
  y1: number;
  x2: number;
  y2: number;
  active: boolean;
  dashed?: boolean;
}) {
  const stroke = lineStroke(active);
  return (
    <g>
      <line
        x1={x1}
        y1={y1}
        x2={x2}
        y2={y2}
        stroke={stroke}
        strokeWidth={active ? 3 : 1.6}
        strokeDasharray={dashed ? '6 5' : undefined}
        vectorEffect="non-scaling-stroke"
      />
      {!dashed && (
        <>
          <circle cx={x1} cy={y1} r={active ? 3.3 : 2.3} fill={stroke} />
          <circle cx={x2} cy={y2} r={active ? 3.3 : 2.3} fill={stroke} />
        </>
      )}
    </g>
  );
}


function DirectionArrow({
  x1,
  y1,
  x2,
  y2,
  active,
}: {
  x1: number;
  y1: number;
  x2: number;
  y2: number;
  active: boolean;
}) {
  const stroke = lineStroke(active);
  const angle = Math.atan2(y2 - y1, x2 - x1);
  const size = active ? 10 : 8;
  const wing = Math.PI / 7;
  const p1x = x2 - size * Math.cos(angle - wing);
  const p1y = y2 - size * Math.sin(angle - wing);
  const p2x = x2 - size * Math.cos(angle + wing);
  const p2y = y2 - size * Math.sin(angle + wing);
  return (
    <g>
      <line
        x1={x1}
        y1={y1}
        x2={x2}
        y2={y2}
        stroke={stroke}
        strokeWidth={active ? 3 : 1.8}
        vectorEffect="non-scaling-stroke"
      />
      <path
        d={`M ${p1x} ${p1y} L ${x2} ${y2} L ${p2x} ${p2y}`}
        fill="none"
        stroke={stroke}
        strokeWidth={active ? 3 : 1.8}
        strokeLinecap="round"
        strokeLinejoin="round"
        vectorEffect="non-scaling-stroke"
      />
    </g>
  );
}

function ActiveLabel({
  x,
  y,
  active,
  children,
}: {
  x: number;
  y: number;
  active: boolean;
  children: string;
}) {
  return (
    <text
      x={x}
      y={y}
      fontSize={active ? 13 : 11}
      fontWeight={active ? 700 : 500}
      fill={labelFill(active)}
    >
      {children}
    </text>
  );
}

export function CvtMeasurementPreview({
  value,
  activePath,
}: {
  value: CvtData;
  activePath: string | null;
}) {
  const fixedPivot = primaryFixedPivot(value.assembly);
  const active = cvtMeasurementKeyForPath(activePath);
  if (!fixedPivot) {
    return (
      <Paper withBorder p="md">
        <Text size="sm" fw={600}>Primary measurement guide</Text>
        <Text size="xs" c="dimmed" mt={4}>
          This CVT does not use the fixed-pivot roller geometry shown by the standard hardware guide.
        </Text>
      </Paper>
    );
  }

  const g = fixedPivot.component.geometry;
  const shaftRadius = Math.max(0, primaryShaftRadius(value));
  const beltOuterRadius = value.assembly.geometry.primary_outer_radius_at_zero_shift_m;
  const travel = Math.max(0, value.assembly.geometry.max_shift_m);
  const deadzone = clamp(value.assembly.geometry.deadzone_shift_m, 0, travel || Number.POSITIVE_INFINITY);
  const pivotAxial = g.pivot_axial_position_m;
  const pivotRadius = Math.max(0, g.pivot_radius_m);
  const armLength = Math.max(0, g.arm_length_m);
  const rollerRadius = Math.max(0, g.roller_radius_m);
  const rampAxial = g.ramp_reference_axial_position_m;
  const rampRadius = Math.max(0, g.ramp_reference_radius_m);

  const minAxial = Math.min(-0.012, pivotAxial - 0.015, rampAxial - 0.015, 0);
  const maxAxial = Math.max(0.035, travel + 0.015, pivotAxial + armLength + 0.015, rampAxial + 0.015);
  const maxRadius = Math.max(0.06, beltOuterRadius * 1.25, pivotRadius + armLength + rollerRadius, rampRadius + rollerRadius);
  const x = (axial: number) => LEFT + ((axial - minAxial) / Math.max(1e-9, maxAxial - minAxial)) * (RIGHT - LEFT);
  const y = (radius: number) => CENTRELINE_Y - (radius / Math.max(1e-9, maxRadius)) * (CENTRELINE_Y - TOP);

  const pivotX = x(pivotAxial);
  const pivotY = y(pivotRadius);
  const rampX = x(rampAxial);
  const rampY = y(rampRadius);
  const vectorAxial = rampAxial - pivotAxial;
  const vectorRadius = rampRadius - pivotRadius;
  const vectorLength = Math.hypot(vectorAxial, vectorRadius);
  const directionAxial = vectorLength > 1e-9 ? vectorAxial / vectorLength : 0.75;
  const directionRadius = vectorLength > 1e-9 ? vectorRadius / vectorLength : 0.66;
  const rollerAxial = pivotAxial + directionAxial * armLength;
  const rollerRadial = Math.max(0, pivotRadius + directionRadius * armLength);
  const rollerX = x(rollerAxial);
  const rollerY = y(rollerRadial);
  const rollerPixels = Math.max(5, Math.abs(y(rollerRadial + rollerRadius) - y(rollerRadial)));
  const zeroX = x(0);
  const travelX = x(travel);
  const deadzoneX = x(deadzone);
  const shaftY = y(shaftRadius);
  const beltOuterY = y(beltOuterRadius);

  const is = (key: Exclude<CvtMeasurementKey, null>) => active === key;
  const activeLabel = active ? CVT_MEASUREMENT_LABELS[active] : null;

  return (
    <Paper withBorder p="md">
      <Stack gap={6}>
        <div>
          <Text size="sm" fw={600}>Primary measurement guide</Text>
          <Text size="xs" c="dimmed">
            Hardware reference only. Ramp start is shown for context; roller contact is solved separately in Tunes and validation.
          </Text>
        </div>
        <svg
          viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
          width="100%"
          role="img"
          aria-label="Primary CVT measurement guide with shaft centreline, belt surfaces, flyweight pivot, arm, roller, ramp start and movable-sheave travel"
        >
          <rect x="1" y="1" width={WIDTH - 2} height={HEIGHT - 2} rx="8" fill="none" stroke="var(--mantine-color-gray-3)" />

          <line x1={LEFT - 18} y1={CENTRELINE_Y} x2={RIGHT + 8} y2={CENTRELINE_Y} stroke="var(--mantine-color-gray-5)" strokeDasharray="8 6" />
          <ActiveLabel x={LEFT - 8} y={CENTRELINE_Y - 8} active={false}>Shaft centreline</ActiveLabel>

          <rect
            x={LEFT + 20}
            y={shaftY}
            width={RIGHT - LEFT - 35}
            height={CENTRELINE_Y - shaftY}
            fill="var(--mantine-color-gray-1)"
            stroke={lineStroke(is('shaft-radius'))}
            strokeWidth={is('shaft-radius') ? 2.6 : 1.2}
          />
          <ActiveLabel x={RIGHT - 150} y={shaftY - 7} active={is('shaft-radius')}>Shaft / sleeve OD</ActiveLabel>
          <ArrowLine x1={LEFT + 34} y1={CENTRELINE_Y} x2={LEFT + 34} y2={shaftY} active={is('shaft-radius')} />

          <polygon
            points={`${x(0.008)},${shaftY - 2} ${x(Math.max(0.011, travel + 0.008))},${shaftY - 2} ${x(Math.max(0.011, travel + 0.006))},${beltOuterY} ${x(0.01)},${beltOuterY}`}
            fill="var(--mantine-color-gray-2)"
            stroke="var(--mantine-color-gray-6)"
            strokeWidth="1.2"
          />
          <ActiveLabel x={x(0.012)} y={beltOuterY - 7} active={false}>Belt surfaces</ActiveLabel>

          <line x1={zeroX} y1={shaftY - 22} x2={zeroX - 34} y2={beltOuterY - 20} stroke="var(--mantine-color-gray-6)" strokeWidth="2" />
          <line x1={travelX} y1={shaftY - 22} x2={travelX + 34} y2={beltOuterY - 20} stroke="var(--mantine-color-gray-6)" strokeWidth="2" />

          <DirectionArrow x1={zeroX} y1={48} x2={travelX} y2={48} active={is('primary-travel')} />
          <ActiveLabel x={(zeroX + travelX) / 2 - 55} y={38} active={is('primary-travel')}>Movable-sheave travel</ActiveLabel>
          {deadzone > 0 && (
            <>
              <ArrowLine x1={zeroX} y1={72} x2={deadzoneX} y2={72} active={is('deadzone-travel')} />
              <ActiveLabel x={zeroX} y={90} active={is('deadzone-travel')}>Free travel to belt contact</ActiveLabel>
            </>
          )}

          <line x1={zeroX} y1={TOP + 48} x2={zeroX} y2={CENTRELINE_Y} stroke="var(--mantine-color-gray-4)" strokeDasharray="3 5" />
          <ActiveLabel x={zeroX + 6} y={TOP + 60} active={false}>Axial datum / fully open</ActiveLabel>

          <ArrowLine x1={zeroX} y1={pivotY + 18} x2={pivotX} y2={pivotY + 18} active={is('pivot-axial')} />
          <ArrowLine x1={pivotX - 18} y1={CENTRELINE_Y} x2={pivotX - 18} y2={pivotY} active={is('pivot-radius')} />

          <line x1={pivotX} y1={pivotY} x2={rollerX} y2={rollerY} stroke={lineStroke(is('arm-length'))} strokeWidth={is('arm-length') ? 4 : 2.2} />
          <circle cx={pivotX} cy={pivotY} r={5.5} fill={lineStroke(is('pivot-axial') || is('pivot-radius') || is('arm-length'))} />
          <ActiveLabel x={pivotX + 8} y={pivotY - 8} active={is('pivot-axial') || is('pivot-radius')}>Pivot</ActiveLabel>

          <circle cx={rollerX} cy={rollerY} r={rollerPixels} fill="var(--mantine-color-body)" stroke={lineStroke(is('roller-radius') || is('arm-length'))} strokeWidth={is('roller-radius') ? 3 : 2} />
          <ArrowLine x1={rollerX} y1={rollerY} x2={rollerX + rollerPixels} y2={rollerY} active={is('roller-radius')} />
          <ActiveLabel x={rollerX + rollerPixels + 7} y={rollerY - 5} active={is('roller-radius')}>Roller</ActiveLabel>

          <path
            d={`M ${rampX} ${rampY} Q ${rampX + 42} ${rampY - 24} ${rampX + 82} ${rampY - 8}`}
            fill="none"
            stroke="var(--mantine-color-gray-5)"
            strokeWidth="2.2"
          />
          <rect x={rampX - 4} y={rampY - 4} width="8" height="8" transform={`rotate(45 ${rampX} ${rampY})`} fill="var(--mantine-color-gray-7)" />
          <ActiveLabel x={rampX + 8} y={rampY + 18} active={false}>Ramp start · Tunes</ActiveLabel>

          <text x={LEFT} y={HEIGHT - 16} fontSize="10.5" fill="var(--mantine-color-dimmed)">
            Roller pose is schematic; stored pivot, ramp reference and measurement directions are shown for guidance.
          </text>
        </svg>
        <Text size="xs" c={activeLabel ? 'var(--mantine-primary-color-filled)' : 'dimmed'} fw={activeLabel ? 600 : 400}>
          {activeLabel ? `Highlighted measurement: ${activeLabel}` : 'Focus a geometry measurement to highlight where it is taken.'}
        </Text>
      </Stack>
    </Paper>
  );
}
