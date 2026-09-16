import { useEffect, useMemo, useState } from 'react';
import type {
  ConditionedPathDomainAnalysis,
  ConditionedRampSolution,
  FixedPivotArchitecture,
  ForceRequirement,
} from '@api/primaryDesign';
import styles from './PrimaryDesign.module.scss';
import ui from './ConditionedSolutionsExplorer.module.scss';

const VIEW_W = 900;
const MECH_H = 500;
const FORCE_W = 560;
const FORCE_H = 300;
const PAD = 34;
const FORCE_LEFT = 52;
const FORCE_RIGHT = 18;
const FORCE_TOP = 18;
const FORCE_BOTTOM = 38;
const MM = 1000;
const G = 1000;

type Bounds = { xMin: number; xMax: number; rMin: number; rMax: number };
type Scene = {
  sx: (x: number) => number;
  sy: (r: number) => number;
  path: (xs: number[], rs: number[]) => string;
  scale: number;
};

type ForcePlot = {
  x: (shiftM: number) => number;
  y: (forceN: number) => number;
  yMin: number;
  yMax: number;
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
  }, [selectedIndex, solutions]);

  const rampBounds = useMemo(() => computeRampBounds(solutions, 0.0045), [solutions]);
  const mechanismBounds = useMemo(
    () => computeMechanismBounds(architecture, solutions, 0.009),
    [architecture, solutions],
  );
  const mechanismScene = useMemo(() => createScene(mechanismBounds, VIEW_W, MECH_H, PAD), [mechanismBounds]);

  if (!selected || solutions.length === 0) {
    return (
      <div className={ui.empty}>
        <button type="button" className={styles.toolButton} onClick={onBack}>← Back to requirements</button>
        <strong>No inspectable representative ramp was extracted.</strong>
        <span>The conditioned graph can still be feasible; this only means the bounded representative search did not return a history-certified example.</span>
      </div>
    );
  }

  const massMin = selected.solution.tip_mass_min_kg;
  const massMax = selected.solution.tip_mass_max_kg;
  const selectedFit = profileFit(selected);
  const forceValues = absoluteForce(selected, massKg, analysis.force_capability.reference_shaft_speed_rad_s);
  const forcePlot = createForcePlot(selected.shift_m, forceValues, requirements, selectedFit?.target_force_N ?? []);
  const guideCount = requirements.filter((item) => item.id.startsWith('guide-')).length;
  const lockCount = requirements.length - guideCount;
  const pose = samplePathAtShift(selected, shiftM);
  const forceAtShift = interpolate(selected.shift_m, forceValues, shiftM);
  const pivotX = architecture.pivot_axial_position_m - shiftM;
  const pivotR = architecture.pivot_radius_m;
  const rollerRadiusPx = Math.max(3, architecture.roller_radius_m * mechanismScene.scale);

  return (
    <div className={ui.page}>
      <header className={ui.header}>
        <div>
          <button type="button" className={styles.toolButton} onClick={onBack}>← Requirements</button>
          <div className={ui.titleBlock}>
            <strong>Best-fit ramp designs</strong>
            <span>Solutions are ranked by whole-profile force error first, then diversified geometrically among near-optimal paths. Every shown ramp is history certified.</span>
          </div>
        </div>
        <div className={ui.headerStats}>
          <Stat label="representatives" value={String(solutions.length)} />
          <Stat label="profile" value={`${guideCount} guides · ${lockCount} locks`} />
          <Stat
            label="selected mass window"
            value={`${(massMin * G).toFixed(1)}–${(massMax * G).toFixed(1)} g`}
          />
          {selectedFit && <Stat label="profile RMS" value={`${selectedFit.rms_error_N.toFixed(1)} N`} />}
        </div>
      </header>

      <div className={ui.workspace}>
        <aside className={ui.gallery}>
          <div className={ui.galleryHeader}>
            <strong>Ranked ramp gallery</strong>
            <span>Ramp 1 is the best force-profile match found; later cards stay near-optimal while exploring different physical shapes.</span>
          </div>
          <div className={ui.galleryList}>
            {solutions.map((solution, index) => (
              <SolutionCard
                key={index}
                solution={solution}
                index={index}
                selected={index === selectedIndex}
                bounds={rampBounds}
                onSelect={() => setSelectedIndex(index)}
              />
            ))}
          </div>
        </aside>

        <main className={ui.inspector}>
          <section className={ui.panel}>
            <div className={ui.panelHeader}>
              <div>
                <strong>Ramp {selectedIndex + 1} · mechanism</strong>
                <span>The family stays faint in the background so changing selections does not change your spatial reference.</span>
              </div>
              <span>{(shiftM * MM).toFixed(2)} mm shift</span>
            </div>

            <svg viewBox={`0 0 ${VIEW_W} ${MECH_H}`} className={ui.mechanismCanvas} role="img" aria-label="Selected surviving ramp and flyweight mechanism">
              <rect width={VIEW_W} height={MECH_H} rx="14" className={ui.canvasBackground} />
              <MechanismGrid scene={mechanismScene} bounds={mechanismBounds} />
              {solutions.map((solution, index) => (
                index === selectedIndex ? null : (
                  <path
                    key={index}
                    d={mechanismScene.path(solution.ramp_surface.x_m, solution.ramp_surface.r_m)}
                    className={ui.familyGhost}
                  />
                )
              ))}
              <path d={mechanismScene.path(selected.roller_center.x_m, selected.roller_center.r_m)} className={ui.rollerPath} />
              <path d={mechanismScene.path(selected.ramp_surface.x_m, selected.ramp_surface.r_m)} className={ui.selectedRamp} />
              <line
                x1={mechanismScene.sx(architecture.pivot_axial_position_m)}
                y1={mechanismScene.sy(pivotR)}
                x2={mechanismScene.sx(architecture.pivot_axial_position_m - architecture.required_travel_m)}
                y2={mechanismScene.sy(pivotR)}
                className={ui.pivotTravel}
              />
              <line
                x1={mechanismScene.sx(pivotX)}
                y1={mechanismScene.sy(pivotR)}
                x2={mechanismScene.sx(pose.rollerCenterX)}
                y2={mechanismScene.sy(pose.rollerCenterR)}
                className={ui.arm}
              />
              <circle cx={mechanismScene.sx(pivotX)} cy={mechanismScene.sy(pivotR)} r="7" className={ui.pivot} />
              <circle cx={mechanismScene.sx(pose.rollerCenterX)} cy={mechanismScene.sy(pose.rollerCenterR)} r={rollerRadiusPx} className={ui.roller} />
              <line
                x1={mechanismScene.sx(pose.rollerCenterX)}
                y1={mechanismScene.sy(pose.rollerCenterR)}
                x2={mechanismScene.sx(pose.contactX)}
                y2={mechanismScene.sy(pose.contactR)}
                className={ui.contactNormal}
              />
              <circle cx={mechanismScene.sx(pose.contactX)} cy={mechanismScene.sy(pose.contactR)} r="5" className={ui.contact} />
            </svg>

            <div className={ui.scrubberRow}>
              <span>0 mm</span>
              <input
                type="range"
                min={0}
                max={architecture.required_travel_m * MM}
                step={0.02}
                value={Math.min(shiftM, architecture.required_travel_m) * MM}
                onChange={(event) => setShiftM(Number(event.target.value) / MM)}
              />
              <span>{(architecture.required_travel_m * MM).toFixed(2)} mm</span>
            </div>

            <div className={ui.readouts}>
              <Readout label="q" value={`${pose.qDeg.toFixed(2)}°`} />
              <Readout label="ramp tangent" value={`${pose.tangentDeg.toFixed(2)}°`} />
              <Readout label="contact x" value={`${(pose.contactX * MM).toFixed(2)} mm`} />
              <Readout label="contact radius" value={`${(pose.contactR * MM).toFixed(2)} mm`} />
              <Readout label="closing force" value={`${forceAtShift.toFixed(1)} N`} />
            </div>
          </section>

          <section className={ui.panel}>
            <div className={ui.panelHeader}>
              <div>
                <strong>Force response</strong>
                <span>The amber target is the shape-preserving profile through your guide handles. The selected mass is the best continuous fit within this ramp’s hard-lock-compatible mass interval.</span>
              </div>
              <span>{(massKg * G).toFixed(1)} g / flyweight</span>
            </div>

            <div className={ui.massControl}>
              <div>
                <span>Tip mass</span>
                <strong>{(massKg * G).toFixed(1)} g</strong>
              </div>
              <input
                type="range"
                min={massMin * G}
                max={Math.max(massMin * G, massMax * G)}
                step={Math.max(0.05, (massMax - massMin) * G / 250)}
                value={massKg * G}
                onChange={(event) => setMassKg(Number(event.target.value) / G)}
              />
              <div className={ui.massEnds}>
                <span>{(massMin * G).toFixed(1)} g</span>
                <span>{(massMax * G).toFixed(1)} g</span>
              </div>
            </div>

            {forcePlot && (
              <svg viewBox={`0 0 ${FORCE_W} ${FORCE_H}`} className={ui.forceCanvas} role="img" aria-label="Selected ramp force curve and requirements">
                <rect width={FORCE_W} height={FORCE_H} rx="12" className={ui.canvasBackground} />
                <ForceGrid plot={forcePlot} travelM={architecture.required_travel_m} />
                {selectedFit && selectedFit.target_shift_m.length > 1 && (
                  <path
                    d={curvePath(selectedFit.target_shift_m, selectedFit.target_force_N, forcePlot)}
                    style={{ fill: 'none', stroke: 'rgba(255, 208, 122, 0.96)', strokeWidth: 2.4, strokeDasharray: '7 4' }}
                  />
                )}
                <path d={curvePath(selected.shift_m, forceValues, forcePlot)} className={ui.forceCurve} />
                {requirements.map((requirement) => (
                  <g key={requirement.id}>
                    <line
                      x1={forcePlot.x(requirement.shift_m)}
                      x2={forcePlot.x(requirement.shift_m)}
                      y1={forcePlot.y(requirement.force_N - requirement.tolerance_N)}
                      y2={forcePlot.y(requirement.force_N + requirement.tolerance_N)}
                      className={ui.requirementTolerance}
                    />
                    <circle cx={forcePlot.x(requirement.shift_m)} cy={forcePlot.y(requirement.force_N)} r={requirement.id.startsWith('guide-') ? 5.5 : 6.5} className={ui.requirementPoint} style={requirement.id.startsWith('guide-') ? undefined : { fill: '#ff9f9f' }} />
                  </g>
                ))}
                <line x1={forcePlot.x(shiftM)} x2={forcePlot.x(shiftM)} y1={FORCE_TOP} y2={FORCE_H - FORCE_BOTTOM} className={ui.shiftCursor} />
                <circle cx={forcePlot.x(shiftM)} cy={forcePlot.y(forceAtShift)} r="5" className={ui.forceCursor} />
              </svg>
            )}
          </section>
        </main>
      </div>
    </div>
  );
}

function SolutionCard({
  solution,
  index,
  selected,
  bounds,
  onSelect,
}: {
  solution: ConditionedRampSolution;
  index: number;
  selected: boolean;
  bounds: Bounds;
  onSelect: () => void;
}) {
  const scene = createScene(bounds, 210, 92, 10);
  const massMin = solution.solution.tip_mass_min_kg * G;
  const massMax = solution.solution.tip_mass_max_kg * G;
  const q0 = solution.q_deg[0];
  const q1 = solution.q_deg[solution.q_deg.length - 1];
  const a0 = solution.ramp_tangent_deg[0];
  const a1 = solution.ramp_tangent_deg[solution.ramp_tangent_deg.length - 1];
  const fit = profileFit(solution);
  return (
    <button type="button" className={selected ? ui.cardSelected : ui.card} onClick={onSelect}>
      <div className={ui.cardTop}>
        <strong>Ramp {index + 1}</strong>
        <span>history certified</span>
      </div>
      <svg viewBox="0 0 210 92" className={ui.cardPlot} aria-hidden="true">
        <path d={scene.path(solution.ramp_surface.x_m, solution.ramp_surface.r_m)} />
      </svg>
      <div className={ui.cardMetrics}>
        <span><em>q</em>{q0.toFixed(1)}° → {q1.toFixed(1)}°</span>
        {fit ? <span><em>fit</em>{fit.rms_error_N.toFixed(0)} N RMS · {fit.max_abs_error_N.toFixed(0)} N max</span> : <span><em>tangent</em>{a0.toFixed(1)}° → {a1.toFixed(1)}°</span>}
        <span><em>mass</em>{massMin.toFixed(0)}–{massMax.toFixed(0)} g</span>
      </div>
    </button>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return <div className={ui.stat}><span>{label}</span><strong>{value}</strong></div>;
}

function Readout({ label, value }: { label: string; value: string }) {
  return <div className={ui.readout}><span>{label}</span><strong>{value}</strong></div>;
}


type ProfileFit = {
  rms_error_N: number;
  max_abs_error_N: number;
  target_shift_m: number[];
  target_force_N: number[];
  history_certified: boolean;
};

function profileFit(solution: ConditionedRampSolution): ProfileFit | null {
  const payload = solution.solution as ConditionedRampSolution['solution'] & { profile_fit?: ProfileFit };
  return payload.profile_fit ?? null;
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

function computeRampBounds(paths: ConditionedRampSolution[], paddingM: number): Bounds {
  const xs = paths.flatMap((path) => path.ramp_surface.x_m);
  const rs = paths.flatMap((path) => path.ramp_surface.r_m);
  if (!xs.length) return { xMin: -0.04, xMax: 0.04, rMin: 0.02, rMax: 0.10 };
  return {
    xMin: Math.min(...xs) - paddingM,
    xMax: Math.max(...xs) + paddingM,
    rMin: Math.max(0, Math.min(...rs) - paddingM),
    rMax: Math.max(...rs) + paddingM,
  };
}

function computeMechanismBounds(
  architecture: FixedPivotArchitecture,
  paths: ConditionedRampSolution[],
  paddingM: number,
): Bounds {
  const xs = [architecture.pivot_axial_position_m, architecture.pivot_axial_position_m - architecture.required_travel_m];
  const rs = [architecture.pivot_radius_m];
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

function createScene(bounds: Bounds, width: number, height: number, padding: number): Scene {
  const xSpan = Math.max(1e-9, bounds.xMax - bounds.xMin);
  const rSpan = Math.max(1e-9, bounds.rMax - bounds.rMin);
  const innerWidth = width - 2 * padding;
  const innerHeight = height - 2 * padding;
  const scale = Math.min(innerWidth / xSpan, innerHeight / rSpan);
  const usedWidth = xSpan * scale;
  const usedHeight = rSpan * scale;
  const xOffset = padding + 0.5 * (innerWidth - usedWidth);
  const yOffset = padding + 0.5 * (innerHeight - usedHeight);
  const sx = (x: number) => xOffset + (x - bounds.xMin) * scale;
  const sy = (r: number) => yOffset + usedHeight - (r - bounds.rMin) * scale;
  const path = (xs: number[], rs: number[]) => xs.map((x, index) => `${index === 0 ? 'M' : 'L'} ${sx(x)} ${sy(rs[index])}`).join(' ');
  return { sx, sy, path, scale };
}

function MechanismGrid({ scene, bounds }: { scene: Scene; bounds: Bounds }) {
  const xTicks = gridValues(bounds.xMin, bounds.xMax, 0.01);
  const rTicks = gridValues(bounds.rMin, bounds.rMax, 0.01);
  return (
    <g className={ui.grid}>
      {xTicks.map((x) => <line key={`x-${x}`} x1={scene.sx(x)} y1={PAD} x2={scene.sx(x)} y2={MECH_H - PAD} />)}
      {rTicks.map((r) => <line key={`r-${r}`} x1={PAD} y1={scene.sy(r)} x2={VIEW_W - PAD} y2={scene.sy(r)} />)}
    </g>
  );
}

function gridValues(min: number, max: number, step: number): number[] {
  const first = Math.ceil(min / step) * step;
  const values: number[] = [];
  for (let value = first; value <= max + 1e-12; value += step) values.push(value);
  return values;
}

function createForcePlot(shifts: number[], forces: number[], requirements: ForceRequirement[], targetForces: number[] = []): ForcePlot | null {
  if (!shifts.length || shifts.length !== forces.length) return null;
  const values = [
    ...forces,
    ...targetForces,
    ...requirements.flatMap((item) => [item.force_N - item.tolerance_N, item.force_N + item.tolerance_N]),
  ].filter(Number.isFinite);
  if (!values.length) return null;
  const rawMin = Math.max(0, Math.min(...values));
  const rawMax = Math.max(...values, 1);
  const margin = Math.max(8, 0.08 * (rawMax - rawMin));
  const yMin = Math.max(0, rawMin - margin);
  const yMax = rawMax + margin;
  const xMin = shifts[0];
  const xMax = shifts[shifts.length - 1];
  const innerW = FORCE_W - FORCE_LEFT - FORCE_RIGHT;
  const innerH = FORCE_H - FORCE_TOP - FORCE_BOTTOM;
  return {
    x: (shiftM: number) => FORCE_LEFT + (shiftM - xMin) / Math.max(1e-12, xMax - xMin) * innerW,
    y: (forceN: number) => FORCE_TOP + (yMax - forceN) / Math.max(1e-12, yMax - yMin) * innerH,
    yMin,
    yMax,
  };
}

function ForceGrid({ plot, travelM }: { plot: ForcePlot; travelM: number }) {
  const forceTicks = niceTicks(plot.yMin, plot.yMax, 5);
  const shiftTicks = Array.from({ length: 5 }, (_, index) => index / 4);
  return (
    <g className={ui.forceGrid}>
      {forceTicks.map((value) => (
        <g key={value}>
          <line x1={FORCE_LEFT} x2={FORCE_W - FORCE_RIGHT} y1={plot.y(value)} y2={plot.y(value)} />
          <text x={8} y={plot.y(value) + 4}>{formatTick(value)}</text>
        </g>
      ))}
      {shiftTicks.map((fraction) => {
        const shift = fraction * travelM;
        const x = plot.x(shift);
        return (
          <g key={fraction}>
            <line x1={x} x2={x} y1={FORCE_TOP} y2={FORCE_H - FORCE_BOTTOM} />
            <text x={x} y={FORCE_H - 12} textAnchor="middle">{(shift * MM).toFixed(fraction === 1 ? 1 : 0)}</text>
          </g>
        );
      })}
    </g>
  );
}

function curvePath(shifts: number[], forces: number[], plot: ForcePlot): string {
  return shifts.map((shift, index) => `${index === 0 ? 'M' : 'L'} ${plot.x(shift)} ${plot.y(forces[index])}`).join(' ');
}

function niceTicks(min: number, max: number, targetCount: number): number[] {
  const span = Math.max(1e-9, max - min);
  const rough = span / Math.max(2, targetCount - 1);
  const magnitude = 10 ** Math.floor(Math.log10(rough));
  const residual = rough / magnitude;
  const nice = residual <= 1 ? 1 : residual <= 2 ? 2 : residual <= 5 ? 5 : 10;
  const step = nice * magnitude;
  const first = Math.ceil(min / step) * step;
  const values: number[] = [];
  for (let value = first; value <= max + 1e-9; value += step) values.push(value);
  return values;
}

function formatTick(value: number): string {
  return Math.abs(value) >= 10 ? value.toFixed(0) : value.toFixed(1);
}
