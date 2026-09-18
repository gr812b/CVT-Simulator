import { useMemo, useState } from 'react';
import type {
  FixedPivotArchitecture,
  HistoryCertifiedRampPath,
  PrimaryPathDomainAnalysis,
} from '@api/primaryDesign';
import styles from './PrimaryDesign.module.scss';

const FAMILY_WIDTH = 980;
const FAMILY_HEIGHT = 360;
const MECH_WIDTH = 980;
const MECH_HEIGHT = 430;
const PAD = 38;
const MM = 1000;

interface ViewBounds {
  xMin: number;
  xMax: number;
  rMin: number;
  rMax: number;
}

interface Scene {
  sx: (x: number) => number;
  sy: (r: number) => number;
  path: (xs: number[], rs: number[]) => string;
  scale: number;
}

export function RampFamilyExplorer({
  architecture,
  analysis,
  selectedRepresentativeIndex,
  onSelectedRepresentativeIndexChange,
}: {
  architecture: FixedPivotArchitecture;
  analysis: PrimaryPathDomainAnalysis;
  selectedRepresentativeIndex: number;
  onSelectedRepresentativeIndexChange: (value: number) => void;
}) {
  const [shiftM, setShiftM] = useState(0);
  const paths = analysis.representative_paths;
  const selectedIndex = Math.min(Math.max(0, selectedRepresentativeIndex), Math.max(0, paths.length - 1));
  const selected = paths[selectedIndex] ?? null;

  const familyBounds = useMemo(
    () => computeBounds(architecture, paths, 0.012),
    [architecture, paths],
  );
  const familyScene = useMemo(
    () => createScene(familyBounds, FAMILY_WIDTH, FAMILY_HEIGHT),
    [familyBounds],
  );
  const mechanismBounds = useMemo(
    () => selected ? computeBounds(architecture, [selected], 0.014) : familyBounds,
    [architecture, selected, familyBounds],
  );
  const mechanismScene = useMemo(
    () => createScene(mechanismBounds, MECH_WIDTH, MECH_HEIGHT),
    [mechanismBounds],
  );

  if (!selected || paths.length === 0) {
    return <div className={styles.loading}>No history-certified representative ramps are available for this architecture.</div>;
  }

  const pose = samplePathAtShift(selected, shiftM);
  const pivotX = architecture.pivot_axial_position_m - shiftM;
  const pivotR = architecture.pivot_radius_m;
  const rollerRadiusPx = Math.max(2, architecture.roller_radius_m * mechanismScene.scale);

  return (
    <div className={styles.rampFamilyExplorer}>
      <div className={styles.rampFamilySection}>
        <div className={styles.rampFamilyHeader}>
          <div>
            <strong>History-certified physical ramp family</strong>
            <span>Every visible curve below is a complete ramp that passed the Phase-3.1 local graph and Phase-3.2 history checks.</span>
          </div>
          <span>{paths.length} representative ramps</span>
        </div>

        <svg
          viewBox={`0 0 ${FAMILY_WIDTH} ${FAMILY_HEIGHT}`}
          className={styles.rampFamilyCanvas}
          role="img"
          aria-label="Overlay of history-certified physical ramp shapes"
        >
          <rect width={FAMILY_WIDTH} height={FAMILY_HEIGHT} rx="12" fill="var(--primary-design-canvas, #0d1319)" />
          <Grid scene={familyScene} bounds={familyBounds} width={FAMILY_WIDTH} height={FAMILY_HEIGHT} />
          {paths.map((path, index) => {
            const d = familyScene.path(path.ramp_surface.x_m, path.ramp_surface.r_m);
            return (
              <g key={index}>
                <path
                  d={d}
                  className={index === selectedIndex ? styles.rampFamilySelected : styles.rampFamilyPath}
                />
                <path
                  d={d}
                  className={styles.rampFamilyHitTarget}
                  onClick={() => onSelectedRepresentativeIndexChange(index)}
                />
              </g>
            );
          })}
          {paths.map((path, index) => {
            const x = path.ramp_surface.x_m[0];
            const r = path.ramp_surface.r_m[0];
            return (
              <text
                key={`label-${index}`}
                x={familyScene.sx(x) + 5}
                y={familyScene.sy(r) - 5}
                className={index === selectedIndex ? styles.rampFamilyLabelSelected : styles.rampFamilyLabel}
              >
                {index + 1}
              </text>
            );
          })}
        </svg>

        <div className={styles.rampFamilyStrip}>
          {paths.map((path, index) => (
            <button
              key={index}
              type="button"
              className={index === selectedIndex ? styles.rampFamilyChipSelected : styles.rampFamilyChip}
              onClick={() => onSelectedRepresentativeIndexChange(index)}
            >
              <strong>Ramp {index + 1}</strong>
              <span>{path.q_deg[0].toFixed(1)}° → {path.q_deg[path.q_deg.length - 1].toFixed(1)}°</span>
            </button>
          ))}
        </div>
      </div>

      <div className={styles.rampFamilySection}>
        <div className={styles.rampFamilyHeader}>
          <div>
            <strong>Selected ramp mechanism inspection</strong>
            <span>The ramp stays fixed in its own frame while the pivot translates through primary shift. Scrub the slider to inspect the actual flyarm and finite roller pose.</span>
          </div>
          <span>Ramp {selectedIndex + 1}</span>
        </div>

        <svg
          viewBox={`0 0 ${MECH_WIDTH} ${MECH_HEIGHT}`}
          className={styles.rampMechanismCanvas}
          role="img"
          aria-label="Selected ramp with flyweight arm and roller pose through shift"
        >
          <rect width={MECH_WIDTH} height={MECH_HEIGHT} rx="12" fill="var(--primary-design-canvas, #0d1319)" />
          <Grid scene={mechanismScene} bounds={mechanismBounds} width={MECH_WIDTH} height={MECH_HEIGHT} />

          <path
            d={mechanismScene.path(selected.ramp_surface.x_m, selected.ramp_surface.r_m)}
            className={styles.rampMechanismRamp}
          />
          <path
            d={mechanismScene.path(selected.roller_center.x_m, selected.roller_center.r_m)}
            className={styles.rampMechanismRollerPath}
          />

          <line
            x1={mechanismScene.sx(architecture.pivot_axial_position_m)}
            y1={mechanismScene.sy(pivotR)}
            x2={mechanismScene.sx(pivotX)}
            y2={mechanismScene.sy(pivotR)}
            className={styles.rampMechanismPivotTravel}
          />
          <circle
            cx={mechanismScene.sx(architecture.pivot_axial_position_m)}
            cy={mechanismScene.sy(pivotR)}
            r="4"
            className={styles.rampMechanismPivotReference}
          />
          <text
            x={mechanismScene.sx(architecture.pivot_axial_position_m) + 7}
            y={mechanismScene.sy(pivotR) - 8}
            className={styles.rampMechanismText}
          >
            P₀
          </text>

          <line
            x1={mechanismScene.sx(pivotX)}
            y1={mechanismScene.sy(pivotR)}
            x2={mechanismScene.sx(pose.rollerCenterX)}
            y2={mechanismScene.sy(pose.rollerCenterR)}
            className={styles.rampMechanismArm}
          />
          <circle
            cx={mechanismScene.sx(pivotX)}
            cy={mechanismScene.sy(pivotR)}
            r="7"
            className={styles.rampMechanismPivot}
          />
          <circle
            cx={mechanismScene.sx(pose.rollerCenterX)}
            cy={mechanismScene.sy(pose.rollerCenterR)}
            r={rollerRadiusPx}
            className={styles.rampMechanismRoller}
          />
          <circle
            cx={mechanismScene.sx(pose.contactX)}
            cy={mechanismScene.sy(pose.contactR)}
            r="5"
            className={styles.rampMechanismContact}
          />
          <line
            x1={mechanismScene.sx(pose.rollerCenterX)}
            y1={mechanismScene.sy(pose.rollerCenterR)}
            x2={mechanismScene.sx(pose.contactX)}
            y2={mechanismScene.sy(pose.contactR)}
            className={styles.rampMechanismNormal}
          />

          <text x={mechanismScene.sx(pivotX) + 9} y={mechanismScene.sy(pivotR) + 20} className={styles.rampMechanismText}>P</text>
          <text x={mechanismScene.sx(pose.rollerCenterX) + 10} y={mechanismScene.sy(pose.rollerCenterR) - 8} className={styles.rampMechanismText}>roller</text>
          <text x={mechanismScene.sx(pose.contactX) + 8} y={mechanismScene.sy(pose.contactR) + 17} className={styles.rampMechanismText}>contact</text>
        </svg>

        <div className={styles.rampMechanismControls}>
          <div className={styles.shiftHeader}>
            <div>
              <strong>Shift position</strong>
              <span>{(shiftM * MM).toFixed(2)} / {(architecture.required_travel_m * MM).toFixed(2)} mm</span>
            </div>
            <span className={styles.valid}>history-selected path</span>
          </div>
          <input
            className={styles.shiftSlider}
            type="range"
            min={0}
            max={architecture.required_travel_m * MM}
            step={0.02}
            value={Math.min(shiftM, architecture.required_travel_m) * MM}
            onChange={(event) => setShiftM(Number(event.target.value) / MM)}
          />
          <div className={styles.rampMechanismReadouts}>
            <Readout label="q" value={`${pose.qDeg.toFixed(2)}°`} />
            <Readout label="Ramp tangent" value={`${pose.tangentDeg.toFixed(2)}°`} />
            <Readout label="Contact x" value={`${(pose.contactX * MM).toFixed(2)} mm`} />
            <Readout label="Contact radius" value={`${(pose.contactR * MM).toFixed(2)} mm`} />
            <Readout label="Math roots at worst shift" value={String(selected.history.max_contact_root_count)} />
          </div>
        </div>
      </div>
    </div>
  );
}

function Readout({ label, value }: { label: string; value: string }) {
  return (
    <div className={styles.rampMechanismReadout}>
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function samplePathAtShift(path: HistoryCertifiedRampPath, shiftM: number) {
  const shift = Math.min(Math.max(shiftM, path.shift_m[0]), path.shift_m[path.shift_m.length - 1]);
  return {
    qDeg: interpolate(path.shift_m, path.q_deg, shift),
    tangentDeg: interpolate(path.shift_m, path.ramp_tangent_deg, shift),
    rollerCenterX: interpolate(path.shift_m, path.roller_center.x_m, shift),
    rollerCenterR: interpolate(path.shift_m, path.roller_center.r_m, shift),
    contactX: interpolate(path.shift_m, path.ramp_surface.x_m, shift),
    contactR: interpolate(path.shift_m, path.ramp_surface.r_m, shift),
  };
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
  if (span <= 0) return values[lo];
  const t = (x - axis[lo]) / span;
  return values[lo] + t * (values[hi] - values[lo]);
}

function computeBounds(
  architecture: FixedPivotArchitecture,
  paths: HistoryCertifiedRampPath[],
  paddingM: number,
): ViewBounds {
  const xs: number[] = [
    architecture.pivot_axial_position_m,
    architecture.pivot_axial_position_m - architecture.required_travel_m,
  ];
  const rs: number[] = [architecture.pivot_radius_m];
  for (const path of paths) {
    xs.push(...path.ramp_surface.x_m, ...path.roller_center.x_m);
    rs.push(...path.ramp_surface.r_m, ...path.roller_center.r_m);
  }
  const xMin = Math.min(...xs) - paddingM;
  const xMax = Math.max(...xs) + paddingM;
  const rMin = Math.max(0, Math.min(...rs) - paddingM);
  const rMax = Math.max(...rs) + paddingM;
  return { xMin, xMax, rMin, rMax };
}

function createScene(bounds: ViewBounds, width: number, height: number): Scene {
  const xSpan = Math.max(1e-9, bounds.xMax - bounds.xMin);
  const rSpan = Math.max(1e-9, bounds.rMax - bounds.rMin);
  const innerWidth = width - 2 * PAD;
  const innerHeight = height - 2 * PAD;
  const scale = Math.min(innerWidth / xSpan, innerHeight / rSpan);
  const usedWidth = xSpan * scale;
  const usedHeight = rSpan * scale;
  const xOffset = PAD + 0.5 * (innerWidth - usedWidth);
  const yOffset = PAD + 0.5 * (innerHeight - usedHeight);
  const sx = (x: number) => xOffset + (x - bounds.xMin) * scale;
  const sy = (r: number) => yOffset + usedHeight - (r - bounds.rMin) * scale;
  const path = (xs: number[], rs: number[]) => xs.map((x, index) => `${index === 0 ? 'M' : 'L'} ${sx(x)} ${sy(rs[index])}`).join(' ');
  return { sx, sy, path, scale };
}

function Grid({
  scene,
  bounds,
  width,
  height,
}: {
  scene: Scene;
  bounds: ViewBounds;
  width: number;
  height: number;
}) {
  const xTicks = gridValues(bounds.xMin, bounds.xMax, 0.01);
  const rTicks = gridValues(bounds.rMin, bounds.rMax, 0.01);
  return (
    <g className={styles.rampFamilyGrid}>
      {xTicks.map((x) => <line key={`x-${x}`} x1={scene.sx(x)} y1={PAD} x2={scene.sx(x)} y2={height - PAD} />)}
      {rTicks.map((r) => <line key={`r-${r}`} x1={PAD} y1={scene.sy(r)} x2={width - PAD} y2={scene.sy(r)} />)}
    </g>
  );
}

function gridValues(min: number, max: number, step: number): number[] {
  const first = Math.ceil(min / step) * step;
  const result: number[] = [];
  for (let value = first; value <= max + 1e-12; value += step) result.push(value);
  return result;
}
