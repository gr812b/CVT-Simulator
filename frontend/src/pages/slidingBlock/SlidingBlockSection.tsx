import type { SlidingBlockDemo, SlidingBlockFrame } from '@api/client';
import { colors } from './slidingBlockModels';

type Point = readonly [number, number];
const sx = (z: number) => 90 + (z + 0.07) * 3800;
const sy = (r: number) => 248 - r * 2050;
function path(points: readonly Point[], shift = 0, mirror = false) {
  return points
    .map(
      ([r, z], i) => `${i ? 'L' : 'M'}${sx(z + shift)},${sy(mirror ? -r : r)}`
    )
    .join(' ');
}

export function SlidingBlockSection({
  data,
  frame,
  contacts,
}: {
  data: SlidingBlockDemo;
  frame: SlidingBlockFrame;
  contacts: boolean;
}) {
  const block = data.block_outline_m.map(
    ([r, z]) => [r + frame.datum_m[0], z + frame.datum_m[1]] as const
  );
  const cupLabelPoint =
    data.cup_track_m[Math.floor(data.cup_track_m.length * 0.55)];
  const [a, b] = frame.moving_contact_span_m;
  const movingMidpoint: Point = [(a[0] + b[0]) / 2, (a[1] + b[1]) / 2];
  return (
    <svg
      viewBox="0 0 1000 500"
      role="img"
      aria-label="Axial section of the reaction cup, sliding block and movable sheave"
      data-testid="sliding-section"
    >
      <defs>
        <pattern
          id="sliding-hatch"
          width="9"
          height="9"
          patternUnits="userSpaceOnUse"
          patternTransform="rotate(40)"
        >
          <line y2="9" stroke="#ffffff" strokeWidth="1" opacity=".12" />
        </pattern>
        <marker
          id="sliding-arrow"
          markerWidth="7"
          markerHeight="7"
          refX="6"
          refY="3"
          orient="auto"
        >
          <path
            d="M0,0 L6,3 L0,6"
            fill="none"
            stroke="currentColor"
            strokeWidth="1.5"
          />
        </marker>
      </defs>
      <rect width="1000" height="500" rx="12" fill="#101b24" />
      <line
        x1="48"
        x2="950"
        y1={sy(0)}
        y2={sy(0)}
        stroke="#5c7183"
        strokeDasharray="9 6"
      />
      <rect
        x={sx(data.shaft_limits_m[0])}
        y={sy(data.shaft_radius_m)}
        width={(data.shaft_limits_m[1] - data.shaft_limits_m[0]) * 3800}
        height={data.shaft_radius_m * 4100}
        rx="3"
        fill={colors.shaft}
        opacity=".6"
      />
      {[false, true].map((mirror) => (
        <g key={String(mirror)} opacity={mirror ? 0.55 : 1}>
          {[
            [data.cup_section_m, colors.cup, 0],
            [data.moving_section_m, colors.moving, frame.closure_m],
            [data.fixed_section_m, colors.fixed, 0],
          ].map(([points, color, shift], i) => (
            <g key={i}>
              <path
                d={`${path(points as Point[], shift as number, mirror)} Z`}
                fill={color as string}
                stroke="#c2d0da"
                strokeWidth="1"
              />
              <path
                d={`${path(points as Point[], shift as number, mirror)} Z`}
                fill="url(#sliding-hatch)"
              />
            </g>
          ))}
          <path
            d={path(data.cup_track_m, 0, mirror)}
            fill="none"
            stroke={colors.fixedTrack}
            strokeWidth="3"
          />
          <path
            d={path(data.moving_track_m, frame.closure_m, mirror)}
            fill="none"
            stroke={colors.movingTrack}
            strokeWidth="3"
          />
          <path
            d={`${path(frame.belt_section_m, 0, mirror)} Z`}
            fill={colors.belt}
            stroke="#80909a"
            strokeWidth="1.4"
          />
        </g>
      ))}
      <path
        d={`${path(block)} Z`}
        fill={colors.block}
        stroke="#ffde9a"
        strokeWidth="1.5"
        data-testid="section-block"
        data-radial={frame.datum_m[0]}
        data-axial={frame.datum_m[1]}
      />
      {contacts && (
        <g>
          <path
            d={path(frame.moving_contact_span_m)}
            fill="none"
            stroke={colors.movingTrack}
            strokeWidth="5"
            data-testid="moving-contact-span"
          />
          {[
            [frame.fixed_contact_m, frame.fixed_normal, colors.fixedTrack],
            [movingMidpoint, frame.moving_normal, colors.movingTrack],
          ].map(([point, normal, color], i) => {
            const p = point as Point,
              n = normal as Point;
            return (
              <g key={i} style={{ color: color as string }}>
                <line
                  x1={sx(p[1])}
                  y1={sy(p[0])}
                  x2={sx(p[1] + n[1] * 0.012)}
                  y2={sy(p[0] + n[0] * 0.012)}
                  stroke={color as string}
                  strokeWidth="2"
                  markerEnd="url(#sliding-arrow)"
                />
                {i === 0 && (
                  <circle
                    cx={sx(p[1])}
                    cy={sy(p[0])}
                    r="4"
                    fill={color as string}
                    stroke="#0c141c"
                    strokeWidth="1.5"
                  />
                )}
              </g>
            );
          })}
          <circle
            cx={sx(frame.com_m[1])}
            cy={sy(frame.com_m[0])}
            r="3.5"
            fill="white"
          />
          <text
            x={sx(frame.com_m[1]) - 12}
            y={sy(frame.com_m[0]) - 10}
            fill="white"
            fontSize="12"
          >
            COM
          </text>
        </g>
      )}
      <g fill="#c3d1dc" fontSize="13" fontFamily="inherit">
        <text x="68" y="38">
          Reaction cup
        </text>
        <path
          d={`M165,42 L${sx(cupLabelPoint[1])},${sy(cupLabelPoint[0])}`}
          fill="none"
          stroke={colors.fixedTrack}
        />
        <text x="542" y="32">
          Movable sheave + inclined track
        </text>
        <path
          d={`M605,40 L${sx(data.moving_track_m[22][1] + frame.closure_m)},${sy(data.moving_track_m[22][0])}`}
          fill="none"
          stroke={colors.movingTrack}
        />
        <text x="830" y="72">
          Fixed sheave
        </text>
        <text x="68" y="478">
          One representative block in section · hardware section mirrored below
          shaft
        </text>
        <text x="825" y="478">
          Axial direction →
        </text>
      </g>
    </svg>
  );
}
