import { useEffect, useMemo, useState } from 'react';
import type {
  ConditionedPathDomainAnalysis,
  ConditionedRampSolution,
  FixedPivotArchitecture,
  ForceRequirement,
} from '@api/primaryDesign';
import styles from './PrimaryDesign.module.scss';

const WIDTH = 980;
const HEIGHT = 360;
const MECH_HEIGHT = 430;
const PAD_LEFT = 58;
const PAD_RIGHT = 22;
const PAD_TOP = 24;
const PAD_BOTTOM = 46;
const MM = 1000;
const G = 1000;

type ViewBounds = { xMin: number; xMax: number; rMin: number; rMax: number };
type Scene = {
  sx: (x: number) => number;
  sy: (r: number) => number;
  path: (xs: number[], rs: number[]) => string;
  scale: number;
};

export function ConditionedSolutionsExplorer({
  architecture,
  analysis,
  requirements,
  onBack,
}: {
  architecture: FixedPivotArchitecture;
  analysis: ConditionedPathDomainAnalysis;
  requirements: ForceRequirement[];
  onBack: () => void;
}) {
  const solutions = analysis.representative_solutions;
  const [selectedIndex, setSelectedIndex] = useState(0);
  const selected = solutions[Math.min(selectedIndex, Math.max(0, solutions.length - 1))] ?? null;
  const [shiftM, setShiftM] = useState(0);
  const [massKg, setMassKg] = useState(selected?.solution.example_tip_mass_kg ?? 0);

  useEffect(() => {
    const next = solutions[Math.min(selectedIndex, Math.max(0, solutions.length - 1))] ?? null;
    if (!next) return;
    setMassKg(next.solution.example_tip_mass_kg);
    setShiftM((value) => Math.min(value, architecture.required_travel_m));
  }, [selectedIndex, solutions, architecture.required_travel_m]);

  const familyBounds = useMemo(
    () => computeBounds(architecture, solutions, 0.012),
    [architecture, solutions],
  );
  const familyScene = useMemo(() => createScene(familyBounds, WIDTH, HEIGHT), [familyBounds]);
  const mechanismBounds = useMemo(
    () => selected ? computeBounds(architecture, [selected], 0.014) : familyBounds,
    [architecture, selected, familyBounds],
  );
  const mechanismScene = useMemo(
    () => createScene(mechanismBounds, WIDTH, MECH_HEIGHT),
    [mechanismBounds],
  );

  if (!selected || solutions.length === 0) {
    return (
      <div className={styles.rampFamilyExplorer}>
        <button type="button" className={styles.toolButton} onClick={onBack}>← Back to requirements</button>
        <div className={styles.loading}>The conditioned graph is feasible, but no history-certified solution examples were extracted.</div>
      </div>
    );
  }

  const forceValues = absoluteForce(selected, massKg, analysis.force_capability.reference_shaft_speed_rad_s);
  const forcePlot = createForcePlot(selected.shift_m, forceValues, requirements);
  const pose = samplePathAtShift(selected, shiftM);
  const pivotX = architecture.pivot_axial_position_m - shiftM;
  const pivotR = architecture.pivot_radius_m;
  const rollerRadiusPx = Math.max(2, architecture.roller_radius_m * mechanismScene.scale);
  const massMin = selected.solution.tip_mass_min_kg;
  const massMax = selected.solution.tip_mass_max_kg;

  return (
    <div className={styles.rampFamilyExplorer}>
      <div className={styles.requirementControlBar}>
        <div className={styles.requirementControlActions}>
          <button type="button" className={styles.toolButton} onClick={onBack}>← Back to requirements</button>
        </div>
        <div className={styles.requirementField}>
          <span>Conditioned solutions</span>
          <div><strong>{solutions.length}</strong><em>diverse complete ramps</em></div>
        </div>
        <div className={styles.requirementField}>
          <span>Selected mass range</span>
          <div><strong>{(massMin * G).toFixed(1)}–{(massMax * G).toFixed(1)}</strong><em>g / flyweight</em></div>
        </div>
      </div>

      <div className={styles.rampFamilySection}>
        <div className={styles.rampFamilyHeader}>
          <div>
            <strong>Surviving ramp family</strong>
            <span>These ramps were extracted from the force-conditioned graph itself. Pick one, then scrub the mechanism and its compatible flyweight mass.</span>
          </div>
          <span>Ramp {selectedIndex + 1} / {solutions.length}</span>
        </div>

        <svg viewBox={`0 0 ${WIDTH} ${HEIGHT}`} className={styles.rampFamilyCanvas} role="img" aria-label="Force-conditioned ramp family">
          <rect width={WIDTH} height={HEIGHT} rx="12" fill="var(--primary-design-canvas, #0d1319)" />
          <Grid scene={familyScene} bounds={familyBounds} width={WIDTH} height={HEIGHT} />
          {solutions.map((solution, index) => {
            const d = familyScene.path(solution.ramp_surface.x_m, solution.ramp_surface.r_m);
            return (
              <g key={index}>
                <path d={d} className={index === selectedIndex ? styles.rampFamilySelected : styles.rampFamilyPath} />
                <path d={d} className={styles.rampFamilyHitTarget} onClick={() => setSelectedIndex(index)} />
              </g>
            );
          })}
        </svg>

        <div className={styles.rampFamilyStrip}>
          {solutions.map((solution, index) => (
            <button
              key={index}
              type="button"
              className={index === selectedIndex ? styles.rampFamilyChipSelected : styles.rampFamilyChip}
              onClick={() => setSelectedIndex(index)}
            >
              <strong>Ramp {index + 1}</strong>
              <span>{solution.q_deg[0].toFixed(1)}° → {solution.q_deg[solution.q_deg.length - 1].toFixed(1)}°</span>
              <span>{(solution.solution.tip_mass_min_kg * G).toFixed(0)}–{(solution.solution.tip_mass_max_kg * G).toFixed(0)} g</span>
            </button>
          ))}
        </div>
      </div>

      <div className={styles.rampFamilySection}>
        <div className={styles.rampFamilyHeader}>
          <div>
            <strong>Selected force curve</strong>
            <span>The mass slider stays inside this ramp's analytically refined compatible interval. Requirement tolerances are shown on the same curve.</span>
          </div>
          <span>{(massKg * G).toFixed(1)} g / flyweight</span>
        </div>

        <label className={styles.field}>
          <span>Flyweight tip mass</span>
          <input
            className={styles.shiftSlider}
            type="range"
            min={massMin * G}
            max={Math.max(massMin * G, massMax * G)}
            step={Math.max(0.1, (massMax - massMin) * G / 200)}
            value={massKg * G}
            onChange={(event) => setMassKg(Number(event.target.value) / G)}
          />
        </label>

        {forcePlot && (
          <svg viewBox={`0 0 ${WIDTH} ${HEIGHT}`} className={styles.requirementForceCanvas} role="img" aria-label="Selected conditioned ramp force curve">
            <rect width={WIDTH} height={HEIGHT} rx="12" className={styles.requirementCanvasBackground} />
            <ForceGrid plot={forcePlot} />
            <path d={curvePath(selected.shift_m, forceValues, forcePlot)} className={styles.capabilitySelectedCurve} />
            {requirements.map((requirement) => (
              <g key={requirement.id}>
                <line
                  x1={forcePlot.x(requirement.shift_m)}
                  x2={forcePlot.x(requirement.shift_m)}
                  y1={forcePlot.y(requirement.force_N - requirement.tolerance_N)}
                  y2={forcePlot.y(requirement.force_N + requirement.tolerance_N)}
                  className={styles.requirementTolerance}
                />
                <circle cx={forcePlot.x(requirement.shift_m)} cy={forcePlot.y(requirement.force_N)} r="6" className={styles.requirementPoint} />
              </g>
            ))}
            <text x={PAD_LEFT} y={HEIGHT - 12} className={styles.requirementAxisTitle}>shift</text>
            <text x={12} y={PAD_TOP + 4} className={styles.requirementAxisTitle}>closing force (N)</text>
          </svg>
        )}
      </div>

      <div className={styles.rampFamilySection}>
        <div className={styles.rampFamilyHeader}>
          <div>
            <strong>Mechanism inspection</strong>
            <span>Scrub through the full primary travel to inspect the physical ramp, arm, finite roller, and selected contact branch.</span>
          </div>
          <span>{(shiftM * MM).toFixed(2)} mm</span>
        </div>

        <svg viewBox={`0 0 ${WIDTH} ${MECH_HEIGHT}`} className={styles.rampMechanismCanvas} role="img" aria-label="Selected force-conditioned ramp mechanism">
          <rect width={WIDTH} height={MECH_HEIGHT} rx="12" fill="var(--primary-design-canvas, #0d1319)" />
          <Grid scene={mechanismScene} bounds={mechanismBounds} width={WIDTH} height={MECH_HEIGHT} />
          <path d={mechanismScene.path(selected.ramp_surface.x_m, selected.ramp_surface.r_m)} className={styles.rampMechanismRamp} />
          <path d={mechanismScene.path(selected.roller_center.x_m, selected.roller_center.r_m)} className={styles.rampMechanismRollerPath} />
          <line
            x1={mechanismScene.sx(architecture.pivot_axial_position_m)}
            y1={mechanismScene.sy(pivotR)}
            x2={mechanismScene.sx(pivotX)}
            y2={mechanismScene.sy(pivotR)}
            className={styles.rampMechanismPivotTravel}
          />
          <line
            x1={mechanismScene.sx(pivotX)}
            y1={mechanismScene.sy(pivotR)}
            x2={mechanismScene.sx(pose.rollerCenterX)}
            y2={mechanismScene.sy(pose.rollerCenterR)}
            className={styles.rampMechanismArm}
          />
          <circle cx={mechanismScene.sx(pivotX)} cy={mechanismScene.sy(pivotR)} r="7" className={styles.rampMechanismPivot} />
          <circle cx={mechanismScene.sx(pose.rollerCenterX)} cy={mechanismScene.sy(pose.rollerCenterR)} r={rollerRadiusPx} className={styles.rampMechanismRoller} />
          <circle cx={mechanismScene.sx(pose.contactX)} cy={mechanismScene.sy(pose.contactR)} r="5" className={styles.rampMechanismContact} />
          <line
            x1={mechanismScene.sx(pose.rollerCenterX)}
            y1={mechanismScene.sy(pose.rollerCenterR)}
            x2={mechanismScene.sx(pose.contactX)}
            y2={mechanismScene.sy(pose.contactR)}
            className={styles.rampMechanismNormal}
          />
        </svg>

        <div className={styles.rampMechanismControls}>
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

function absoluteForce(solution: ConditionedRampSolution, massKg: number, omega: number): number[] {
  const omega2 = omega * omega;
  return solution.capability.arm_force_per_omega2.map((arm, index) => (
    omega2 * (arm + massKg * solution.capability.tip_force_per_omega2_per_kg[index])
  ));
}

function samplePathAtShift(path: ConditionedRampSolution, shiftM: number) {
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
  const t = (x - axis[lo]) / Math.max(1e-12, axis[hi] - axis[lo]);
  return values[lo] + t * (values[hi] - values[lo]);
}

function computeBounds(
  architecture: FixedPivotArchitecture,
  paths: ConditionedRampSolution[],
  paddingM: number,
): ViewBounds {
  const xs: number[] = [architecture.pivot_axial_position_m, architecture.pivot_axial_position_m - architecture.required_travel_m];
  const rs: number[] = [architecture.pivot_radius_m];
  for (const path of paths) {
    xs.push(...path.ramp_surface.x_m, ...path.roller_center.x_m);
    rs.push(...path.ramp_surface.r_m, ...path.roller_center.r_m);
  }
  return {
    xMin: Math.min(...xs) - paddingM,
    xMax: Math.max(...xs) + paddingM,
    rMin: Math.max(0, Math.min(...rs) - paddingM),
    rMax: Math.max(...rs) + paddingM,
  };
}

function createScene(bounds: ViewBounds, width: number, height: number): Scene {
  const xSpan = Math.max(1e-9, bounds.xMax - bounds.xMin);
  const rSpan = Math.max(1e-9, bounds.rMax - bounds.rMin);
  const innerWidth = width - 2 * 38;
  const innerHeight = height - 2 * 38;
  const scale = Math.min(innerWidth / xSpan, innerHeight / rSpan);
  const usedWidth = xSpan * scale;
  const usedHeight = rSpan * scale;
  const xOffset = 38 + 0.5 * (innerWidth - usedWidth);
  const yOffset = 38 + 0.5 * (innerHeight - usedHeight);
  const sx = (x: number) => xOffset + (x - bounds.xMin) * scale;
  const sy = (r: number) => yOffset + usedHeight - (r - bounds.rMin) * scale;
  const path = (xs: number[], rs: number[]) => xs.map((x, index) => `${index === 0 ? 'M' : 'L'} ${sx(x)} ${sy(rs[index])}`).join(' ');
  return { sx, sy, path, scale };
}

function Grid({ scene, bounds, width, height }: { scene: Scene; bounds: ViewBounds; width: number; height: number }) {
  const xTicks = gridValues(bounds.xMin, bounds.xMax, 0.01);
  const rTicks = gridValues(bounds.rMin, bounds.rMax, 0.01);
  return (
    <g className={styles.rampFamilyGrid}>
      {xTicks.map((x) => <line key={`x-${x}`} x1={scene.sx(x)} y1={38} x2={scene.sx(x)} y2={height - 38} />)}
      {rTicks.map((r) => <line key={`r-${r}`} x1={38} y1={scene.sy(r)} x2={width - 38} y2={scene.sy(r)} />)}
    </g>
  );
}

function gridValues(min: number, max: number, step: number): number[] {
  const first = Math.ceil(min / step) * step;
  const values: number[] = [];
  for (let value = first; value <= max + 1e-12; value += step) values.push(value);
  return values;
}

type ForcePlot = {
  x: (shiftM: number) => number;
  y: (forceN: number) => number;
  yMin: number;
  yMax: number;
};

function createForcePlot(shifts: number[], forces: number[], requirements: ForceRequirement[]): ForcePlot | null {
  if (!shifts.length || shifts.length !== forces.length) return null;
  const values = [...forces, ...requirements.flatMap((item) => [item.force_N - item.tolerance_N, item.force_N + item.tolerance_N])].filter(Number.isFinite);
  if (!values.length) return null;
  const yRawMin = Math.max(0, Math.min(...values));
  const yRawMax = Math.max(...values, 1);
  const margin = Math.max(10, 0.08 * (yRawMax - yRawMin));
  const yMin = Math.max(0, yRawMin - margin);
  const yMax = yRawMax + margin;
  const xMin = shifts[0];
  const xMax = shifts[shifts.length - 1];
  const innerW = WIDTH - PAD_LEFT - PAD_RIGHT;
  const innerH = HEIGHT - PAD_TOP - PAD_BOTTOM;
  return {
    x: (shiftM: number) => PAD_LEFT + (shiftM - xMin) / Math.max(1e-12, xMax - xMin) * innerW,
    y: (forceN: number) => PAD_TOP + (yMax - forceN) / Math.max(1e-12, yMax - yMin) * innerH,
    yMin,
    yMax,
  };
}

function ForceGrid({ plot }: { plot: ForcePlot }) {
  const forceTicks = Array.from({ length: 6 }, (_, index) => plot.yMin + index / 5 * (plot.yMax - plot.yMin));
  const shiftTicks = Array.from({ length: 5 }, (_, index) => index / 4);
  return (
    <g>
      {forceTicks.map((value) => (
        <g key={value}>
          <line x1={PAD_LEFT} x2={WIDTH - PAD_RIGHT} y1={plot.y(value)} y2={plot.y(value)} className={styles.requirementGrid} />
          <text x={8} y={plot.y(value) + 4} className={styles.requirementTick}>{value.toFixed(0)}</text>
        </g>
      ))}
      {shiftTicks.map((fraction) => {
        const x = PAD_LEFT + fraction * (WIDTH - PAD_LEFT - PAD_RIGHT);
        return <g key={fraction}><line x1={x} x2={x} y1={PAD_TOP} y2={HEIGHT - PAD_BOTTOM} className={styles.requirementGrid} /></g>;
      })}
    </g>
  );
}

function curvePath(shifts: number[], forces: number[], plot: ForcePlot): string {
  return shifts.map((shift, index) => `${index === 0 ? 'M' : 'L'} ${plot.x(shift)} ${plot.y(forces[index])}`).join(' ');
}

function Readout({ label, value }: { label: string; value: string }) {
  return <div className={styles.rampMechanismReadout}><span>{label}</span><strong>{value}</strong></div>;
}
