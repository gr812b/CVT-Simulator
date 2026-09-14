import { useCallback, useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  analyzeConcretePrimaryDesign,
  evaluateConcretePrimaryDesign,
  getPrimaryDesignDefaults,
  type ConcreteDesignAnalysis,
  type ConcreteDesignResponse,
  type FixedPivotArchitecture,
  type FixedPivotRamp,
  type PrimaryDesignOperating,
} from '@api/primaryDesign';
import { ForceChart } from './ForceChart';
import { MechanismScene } from './MechanismScene';
import styles from './PrimaryDesign.module.scss';

const MM = 1000;
const G = 1000;
const RPM_PER_RAD_S = 60 / (2 * Math.PI);
const RAD_S_PER_RPM = 2 * Math.PI / 60;

function interpolateNullable(
  axis: number[],
  values: Array<number | boolean | null>,
  x: number,
): number | null {
  const numeric = values.map((value) => typeof value === 'number' ? value : null);
  if (!axis.length || axis.length !== numeric.length) return null;
  if (x <= axis[0]) return numeric[0];
  if (x >= axis[axis.length - 1]) return numeric[numeric.length - 1];
  let lo = 0;
  let hi = axis.length - 1;
  while (hi - lo > 1) {
    const mid = Math.floor((lo + hi) / 2);
    if (axis[mid] <= x) lo = mid;
    else hi = mid;
  }
  const a = numeric[lo];
  const b = numeric[hi];
  if (a === null || b === null) return null;
  const span = axis[hi] - axis[lo];
  const t = span === 0 ? 0 : (x - axis[lo]) / span;
  return a + t * (b - a);
}

function fmt(value: number | null, digits = 1): string {
  return value === null || !Number.isFinite(value) ? '—' : value.toFixed(digits);
}

export const PrimaryDesign = () => {
  const navigate = useNavigate();
  const [architecture, setArchitecture] = useState<FixedPivotArchitecture | null>(null);
  const [ramp, setRamp] = useState<FixedPivotRamp | null>(null);
  const [operating, setOperating] = useState<PrimaryDesignOperating | null>(null);
  const [analysis, setAnalysis] = useState<ConcreteDesignAnalysis | null>(null);
  const [response, setResponse] = useState<ConcreteDesignResponse | null>(null);
  const [shiftM, setShiftM] = useState(0);
  const [geometryDirty, setGeometryDirty] = useState(false);
  const [geometryLoading, setGeometryLoading] = useState(false);
  const [responseLoading, setResponseLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const analyze = useCallback(async (
    nextArchitecture: FixedPivotArchitecture,
    nextRamp: FixedPivotRamp,
    nextOperating: PrimaryDesignOperating,
  ) => {
    setGeometryLoading(true);
    setError(null);
    try {
      const nextAnalysis = await analyzeConcretePrimaryDesign(nextArchitecture, nextRamp, 161);
      setAnalysis(nextAnalysis);
      setGeometryDirty(false);
      const axisValues = nextAnalysis.geometry.axis_values;
      const end = axisValues.length ? axisValues[axisValues.length - 1] : 0;
      setShiftM((value) => Math.min(value, end));
      setResponseLoading(true);
      const nextResponse = await evaluateConcretePrimaryDesign(
        nextAnalysis.analysis_id,
        nextOperating,
      );
      setResponse(nextResponse);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Primary design analysis failed.');
    } finally {
      setGeometryLoading(false);
      setResponseLoading(false);
    }
  }, []);

  useEffect(() => {
    let active = true;
    void getPrimaryDesignDefaults()
      .then(async (defaults) => {
        if (!active) return;
        setArchitecture(defaults.architecture);
        setRamp(defaults.ramp);
        setOperating(defaults.operating);
        await analyze(defaults.architecture, defaults.ramp, defaults.operating);
      })
      .catch((caught: unknown) => {
        if (active) setError(caught instanceof Error ? caught.message : 'Could not load primary design defaults.');
      });
    return () => { active = false; };
  }, [analyze]);

  useEffect(() => {
    if (!analysis || !operating || geometryDirty) return undefined;
    const handle = window.setTimeout(() => {
      setResponseLoading(true);
      void evaluateConcretePrimaryDesign(analysis.analysis_id, operating)
        .then(setResponse)
        .catch((caught: unknown) => setError(caught instanceof Error ? caught.message : 'Load response failed.'))
        .finally(() => setResponseLoading(false));
    }, 70);
    return () => window.clearTimeout(handle);
  }, [analysis, operating, geometryDirty]);

  const current = useMemo(() => {
    if (!analysis) return null;
    const axis = analysis.geometry.axis_values;
    const q = interpolateNullable(axis, analysis.geometry.fields.arm_angle_deg ?? [], shiftM);
    const tangent = interpolateNullable(axis, analysis.geometry.fields.ramp_tangent_deg ?? [], shiftM);
    const loads = response?.loads;
    return {
      q,
      tangent,
      closing: loads ? interpolateNullable(loads.axis_values, loads.fields.flyweight_total_closing_force_N ?? [], shiftM) : null,
      normal: loads ? interpolateNullable(loads.axis_values, loads.fields.ramp_force_normal_N ?? [], shiftM) : null,
      pivot: loads ? interpolateNullable(loads.axis_values, loads.fields.pivot_reaction_resultant_N ?? [], shiftM) : null,
    };
  }, [analysis, response, shiftM]);

  if (!architecture || !ramp || !operating) {
    return <div className={styles.page}><div className={styles.loading}>Loading primary design tool…</div></div>;
  }

  const updateRamp = (patch: Partial<FixedPivotRamp>) => {
    setRamp((value) => value ? { ...value, ...patch } : value);
    setGeometryDirty(true);
  };
  const updateOperating = (patch: Partial<PrimaryDesignOperating>) => {
    setOperating((value) => value ? { ...value, ...patch } : value);
  };
  const analysisAxis = analysis?.geometry.axis_values ?? [];
  const maxShift = analysisAxis.length
    ? analysisAxis[analysisAxis.length - 1]
    : architecture.required_travel_m;

  return (
    <div className={styles.page}>
      <header className={styles.header}>
        <div>
          <button type="button" className={styles.back} onClick={() => navigate('/')}>← Simulator</button>
          <h1>Fixed-Pivot Primary Design</h1>
          <p>Concrete ramp geometry, exact roller contact, flyweight force, and structural load inspection.</p>
        </div>
        <div className={styles.phaseBadge}>Concrete design · Phase 1</div>
      </header>

      {error && <div className={styles.error}>{error}</div>}

      <main className={styles.layout}>
        <aside className={styles.sidebar}>
          <section className={styles.card}>
            <div className={styles.cardTitleRow}>
              <h2>Architecture</h2>
              <span className={styles.locked}>fixed for Phase 1</span>
            </div>
            <div className={styles.readoutGrid}>
              <Readout label="Pivot radius" value={`${(architecture.pivot_radius_m * MM).toFixed(2)} mm`} />
              <Readout label="Arm length" value={`${(architecture.arm_length_m * MM).toFixed(2)} mm`} />
              <Readout label="Roller radius" value={`${(architecture.roller_radius_m * MM).toFixed(2)} mm`} />
              <Readout label="Required travel" value={`${(architecture.required_travel_m * MM).toFixed(2)} mm`} />
              <Readout label="Flyweights" value={String(architecture.number_of_flyweights)} />
              <Readout label="Arm mass / flyweight" value={`${(architecture.arm_mass_per_flyweight_kg * G).toFixed(3)} g`} />
            </div>
          </section>

          <section className={styles.card}>
            <div className={styles.cardTitleRow}>
              <h2>Ramp geometry</h2>
              {geometryDirty && <span className={styles.dirty}>reanalyze</span>}
            </div>
            <label className={styles.field}>
              <span>Profile</span>
              <select value={ramp.kind} onChange={(event) => updateRamp({ kind: event.target.value as FixedPivotRamp['kind'] })}>
                <option value="progressive">Progressive start → end</option>
                <option value="constant">Constant tangent</option>
              </select>
            </label>
            <NumberField label="Start tangent" suffix="°" value={ramp.start_angle_deg} min={1} max={89} step={0.5} onChange={(value) => updateRamp({ start_angle_deg: value })} />
            {ramp.kind === 'progressive' && (
              <NumberField label="End tangent" suffix="°" value={ramp.end_angle_deg} min={1} max={89} step={0.5} onChange={(value) => updateRamp({ end_angle_deg: value })} />
            )}
            <div className={styles.twoCol}>
              <NumberField label="Ramp A axial" suffix="mm" value={ramp.anchor_axial_from_pivot_m * MM} step={0.5} onChange={(value) => updateRamp({ anchor_axial_from_pivot_m: value / MM })} />
              <NumberField label="Ramp A radial" suffix="mm" value={ramp.anchor_radial_from_pivot_m * MM} step={0.5} onChange={(value) => updateRamp({ anchor_radial_from_pivot_m: value / MM })} />
            </div>
            <div className={styles.threeCol}>
              <NumberField label="Linear" suffix="mm" value={ramp.linear_length_m * MM} min={0.5} step={0.5} onChange={(value) => updateRamp({ linear_length_m: value / MM })} />
              <NumberField label="C³ blend" suffix="mm" value={ramp.blend_length_m * MM} min={0.5} step={0.5} onChange={(value) => updateRamp({ blend_length_m: value / MM })} />
              <NumberField label="Circular" suffix="mm" value={ramp.circular_length_m * MM} min={0.5} step={0.5} onChange={(value) => updateRamp({ circular_length_m: value / MM })} />
            </div>
            <button
              type="button"
              className={styles.primaryButton}
              disabled={geometryLoading}
              onClick={() => void analyze(architecture, ramp, operating)}
            >
              {geometryLoading ? 'Analyzing geometry…' : 'Analyze ramp'}
            </button>
          </section>

          <section className={styles.card}>
            <h2>Operating condition</h2>
            <SliderField
              label="Tip mass / flyweight"
              suffix="g"
              value={operating.tip_mass_per_flyweight_kg * G}
              min={0}
              max={650}
              step={1}
              onChange={(value) => updateOperating({ tip_mass_per_flyweight_kg: value / G })}
            />
            <SliderField
              label="Primary speed"
              suffix="rpm"
              value={operating.shaft_speed_rad_s * RPM_PER_RAD_S}
              min={0}
              max={6000}
              step={25}
              onChange={(value) => updateOperating({ shaft_speed_rad_s: value * RAD_S_PER_RPM })}
            />
            <NumberField
              label="Shift speed"
              suffix="mm/s"
              value={operating.shift_speed_m_s * MM}
              step={1}
              onChange={(value) => updateOperating({ shift_speed_m_s: value / MM })}
            />
            <NumberField
              label="Shift acceleration"
              suffix="m/s²"
              value={operating.shift_acceleration_m_s2}
              step={0.1}
              onChange={(value) => updateOperating({ shift_acceleration_m_s2: value })}
            />
            {responseLoading && <div className={styles.muted}>updating loads…</div>}
          </section>
        </aside>

        <div className={styles.workspace}>
          <section className={styles.card}>
            {analysis ? (
              <MechanismScene analysis={analysis} shiftM={shiftM} />
            ) : (
              <div className={styles.loading}>Analyze a ramp to build the mechanism.</div>
            )}
          </section>

          <section className={styles.card}>
            <div className={styles.shiftHeader}>
              <div>
                <h2>Shift position</h2>
                <span>{(shiftM * MM).toFixed(2)} / {(architecture.required_travel_m * MM).toFixed(2)} mm requested</span>
              </div>
              {analysis && <ValidityBadge analysis={analysis} />}
            </div>
            <input
              className={styles.shiftSlider}
              type="range"
              min={0}
              max={Math.max(0.001, maxShift * MM)}
              step={0.05}
              value={Math.min(shiftM, maxShift) * MM}
              onChange={(event) => setShiftM(Number(event.target.value) / MM)}
            />
            <div className={styles.metrics}>
              <Metric label="Arm angle q" value={`${fmt(current?.q ?? null, 2)}°`} />
              <Metric label="Ramp tangent" value={`${fmt(current?.tangent ?? null, 2)}°`} />
              <Metric label="Flyweight closing" value={`${fmt(current?.closing ?? null)} N`} />
              <Metric label="Ramp normal / ramp" value={`${fmt(current?.normal ?? null)} N`} />
              <Metric label="Pivot resultant / flyweight" value={`${fmt(current?.pivot ?? null)} N`} />
            </div>
          </section>

          <section className={styles.card}>
            <div className={styles.chartHeader}>
              <div>
                <h2>Loads through shift</h2>
                <span>Geometry is solved on the backend; moving the shift cursor is local and instantaneous.</span>
              </div>
            </div>
            <ForceChart response={response} shiftM={shiftM} />
          </section>
        </div>
      </main>
    </div>
  );
};

function Readout({ label, value }: { label: string; value: string }) {
  return <div className={styles.readout}><span>{label}</span><strong>{value}</strong></div>;
}

function Metric({ label, value }: { label: string; value: string }) {
  return <div className={styles.metric}><span>{label}</span><strong>{value}</strong></div>;
}

function NumberField({
  label,
  suffix,
  value,
  min,
  max,
  step = 0.1,
  onChange,
}: {
  label: string;
  suffix: string;
  value: number;
  min?: number;
  max?: number;
  step?: number;
  onChange: (value: number) => void;
}) {
  return (
    <label className={styles.field}>
      <span>{label}</span>
      <div className={styles.numberWrap}>
        <input type="number" value={Number.isFinite(value) ? value : 0} min={min} max={max} step={step} onChange={(event) => onChange(Number(event.target.value))} />
        <em>{suffix}</em>
      </div>
    </label>
  );
}

function SliderField({
  label,
  suffix,
  value,
  min,
  max,
  step,
  onChange,
}: {
  label: string;
  suffix: string;
  value: number;
  min: number;
  max: number;
  step: number;
  onChange: (value: number) => void;
}) {
  return (
    <div className={styles.sliderField}>
      <div><span>{label}</span><strong>{value.toFixed(step < 1 ? 1 : 0)} {suffix}</strong></div>
      <input type="range" min={min} max={max} step={step} value={value} onChange={(event) => onChange(Number(event.target.value))} />
    </div>
  );
}

function ValidityBadge({ analysis }: { analysis: ConcreteDesignAnalysis }) {
  if (analysis.validity.valid) {
    return <span className={styles.valid}>Admissible full travel</span>;
  }
  return <span className={styles.invalid}>{analysis.validity.failure?.code ?? 'Inadmissible'}</span>;
}
