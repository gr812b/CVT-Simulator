import { useMemo, useState } from 'react';
import type { SimulationCaseDocument } from '@api/client';
import type { MeasurementMetadata } from '@pages/validation/types';
import styles from './SetupEditorModal.module.scss';

type Section = 'primary' | 'cvt' | 'secondary';

type Props = {
  section: Section;
  document: SimulationCaseDocument;
  metrology: Record<string, MeasurementMetadata>;
  onChange: (document: SimulationCaseDocument, metrology: Record<string, MeasurementMetadata>) => void;
  onClose: () => void;
};

type JsonObject = Record<string, unknown>;

function clone<T>(value: T): T {
  return JSON.parse(JSON.stringify(value)) as T;
}

function pathParts(pointer: string): string[] {
  return pointer.split('/').filter(Boolean);
}

function getAt(root: unknown, pointer: string): unknown {
  let current: unknown = root;
  for (const part of pathParts(pointer)) {
    if (typeof current !== 'object' || current === null) return undefined;
    current = (current as JsonObject)[part];
  }
  return current;
}

function setAt<T>(root: T, pointer: string, value: unknown): T {
  const next = clone(root) as unknown as JsonObject;
  const parts = pathParts(pointer);
  let current = next;
  parts.forEach((part, index) => {
    if (index === parts.length - 1) {
      current[part] = value;
      return;
    }
    const child = current[part];
    if (typeof child !== 'object' || child === null || Array.isArray(child)) current[part] = {};
    current = current[part] as JsonObject;
  });
  return next as T;
}

function NumericMeasuredField({
  label,
  unit,
  pointer,
  document,
  metrology,
  onChange,
}: {
  label: string;
  unit: string;
  pointer: string;
  document: SimulationCaseDocument;
  metrology: Record<string, MeasurementMetadata>;
  onChange: Props['onChange'];
}) {
  const raw = getAt(document, pointer);
  const value = typeof raw === 'number' ? raw : 0;
  const meta = metrology[pointer] ?? { uncertainty: { status: 'pending' as const } };
  const updateMeta = (patch: Partial<MeasurementMetadata>) => {
    onChange(document, { ...metrology, [pointer]: { ...meta, ...patch } });
  };
  return (
    <div className={styles.fieldRow}>
      <label>
        <span>{label}</span>
        <div className={styles.valueWithUnit}>
          <input
            type="number"
            value={value}
            step="any"
            onChange={(event) => onChange(setAt(document, pointer, Number(event.target.value)), metrology)}
          />
          <small>{unit}</small>
        </div>
      </label>
      <label>
        <span>Uncertainty</span>
        <div className={styles.uncertaintyRow}>
          <select
            value={meta.uncertainty.status}
            onChange={(event) => updateMeta({
              uncertainty: {
                ...meta.uncertainty,
                status: event.target.value as MeasurementMetadata['uncertainty']['status'],
              },
            })}
          >
            <option value="pending">Pending</option>
            <option value="known">Known</option>
            <option value="not_applicable">N/A</option>
          </select>
          {meta.uncertainty.status === 'known' && (
            <input
              aria-label={`${label} absolute uncertainty`}
              type="number"
              step="any"
              value={meta.uncertainty.absolute ?? 0}
              onChange={(event) => updateMeta({
                uncertainty: {
                  ...meta.uncertainty,
                  absolute: Number(event.target.value),
                  unit,
                },
              })}
            />
          )}
        </div>
      </label>
      <label className={styles.sourceField}>
        <span>Measurement / source</span>
        <input
          value={meta.method ?? ''}
          placeholder="e.g. calipers, torsional pendulum, manufacturer curve"
          onChange={(event) => updateMeta({ method: event.target.value })}
        />
      </label>
    </div>
  );
}

const CVT_FIELDS = [
  ['/assembly/geometry/belt/height_m', 'Belt height', 'm'],
  ['/assembly/geometry/belt/outer_width_m', 'Belt outer width', 'm'],
  ['/assembly/geometry/belt/inner_width_m', 'Belt inner width', 'm'],
  ['/assembly/geometry/belt/cord_depth_from_outer_m', 'Cord depth from outer surface', 'm'],
  ['/assembly/geometry/belt_outer_length_m', 'Belt outer length', 'm'],
  ['/assembly/geometry/primary_outer_radius_at_zero_shift_m', 'Primary outer radius at zero shift', 'm'],
  ['/assembly/geometry/secondary_outer_radius_at_zero_shift_m', 'Secondary outer radius at zero shift', 'm'],
  ['/assembly/geometry/sheave_half_angle_rad', 'Sheave half angle', 'rad'],
  ['/assembly/geometry/deadzone_shift_m', 'Deadzone shift', 'm'],
  ['/assembly/geometry/max_shift_m', 'Maximum shift', 'm'],
  ['/assembly/contact/static_friction_coefficient', 'Static friction coefficient', '1'],
  ['/assembly/contact/kinetic_friction_coefficient', 'Kinetic friction coefficient', '1'],
  ['/assembly/inertias/primary/fixed_rotating_hardware_inertia_kg_m2', 'Primary fixed rotating inertia', 'kg·m²'],
  ['/assembly/inertias/primary/movable_sheave_rotational_inertia_kg_m2', 'Primary movable sheave rotational inertia', 'kg·m²'],
  ['/assembly/inertias/primary/moving_sheave_mass_kg', 'Primary moving sheave mass', 'kg'],
  ['/assembly/inertias/secondary/fixed_rotating_hardware_inertia_kg_m2', 'Secondary fixed rotating inertia', 'kg·m²'],
  ['/assembly/inertias/secondary/movable_sheave_rotational_inertia_kg_m2', 'Secondary movable sheave rotational inertia', 'kg·m²'],
  ['/assembly/inertias/secondary/moving_sheave_mass_kg', 'Secondary moving sheave mass', 'kg'],
  ['/assembly/inertias/belt_density_kg_per_m3', 'Belt density', 'kg/m³'],
] as const;

function PrimaryEditor(props: Omit<Props, 'section' | 'onClose'>) {
  const boundary = getAt(props.document, '/shaft_boundaries/primary') as JsonObject | undefined;
  const kind = typeof boundary?.kind === 'string' ? boundary.kind : 'full_throttle_engine';
  const fields = kind === 'fixed_shaft'
    ? [
        ['/shaft_boundaries/primary/external_torque_Nm', 'External torque', 'N·m'],
        ['/shaft_boundaries/primary/equivalent_inertia_kg_m2', 'Equivalent inertia', 'kg·m²'],
      ] as const
    : [
        ['/shaft_boundaries/primary/equivalent_rotational_inertia_kg_m2', 'Engine / primary equivalent inertia', 'kg·m²'],
        ['/shaft_boundaries/primary/low_speed_braking_torque_Nm', 'Low-speed braking torque', 'N·m'],
        ['/shaft_boundaries/primary/high_speed_braking_torque_Nm', 'High-speed braking torque', 'N·m'],
      ] as const;

  const switchKind = (nextKind: string) => {
    if (nextKind === kind) return;
    const next = clone(props.document) as unknown as JsonObject;
    const boundaries = next.shaft_boundaries as JsonObject;
    boundaries.primary = nextKind === 'fixed_shaft'
      ? { kind: 'fixed_shaft', external_torque_Nm: 0, equivalent_inertia_kg_m2: 0 }
      : {
          kind: 'full_throttle_engine',
          points: [
            { angular_speed_rad_per_s: 100, torque_Nm: 0 },
            { angular_speed_rad_per_s: 400, torque_Nm: 0 },
          ],
          low_speed_braking_torque_Nm: 0,
          low_speed_braking_peak_speed_rad_per_s: 50,
          high_speed_braking_torque_Nm: 0,
          high_speed_braking_transition_width_rad_per_s: 100,
          equivalent_rotational_inertia_kg_m2: 0,
        };
    props.onChange(next as unknown as SimulationCaseDocument, props.metrology);
  };

  const points = Array.isArray(boundary?.points) ? boundary.points as JsonObject[] : [];
  return (
    <>
      <label className={styles.kindSelect}>
        <span>Physical primary boundary</span>
        <select value={kind} onChange={(event) => switchKind(event.target.value)}>
          <option value="full_throttle_engine">Full-throttle engine</option>
          <option value="fixed_shaft">Fixed torque / inertia</option>
        </select>
      </label>
      {fields.map(([pointer, label, unit]) => (
        <NumericMeasuredField key={pointer} {...props} pointer={pointer} label={label} unit={unit} />
      ))}
      {kind === 'full_throttle_engine' && (
        <section className={styles.curveEditor}>
          <h3>Torque curve</h3>
          <p>Normally established once. Values are angular speed [rad/s] and crankshaft torque [N·m].</p>
          {points.map((point, index) => (
            <div className={styles.curveRow} key={index}>
              <input
                type="number"
                step="any"
                value={Number(point.angular_speed_rad_per_s ?? 0)}
                onChange={(event) => props.onChange(
                  setAt(props.document, `/shaft_boundaries/primary/points/${index}/angular_speed_rad_per_s`, Number(event.target.value)),
                  props.metrology,
                )}
              />
              <input
                type="number"
                step="any"
                value={Number(point.torque_Nm ?? 0)}
                onChange={(event) => props.onChange(
                  setAt(props.document, `/shaft_boundaries/primary/points/${index}/torque_Nm`, Number(event.target.value)),
                  props.metrology,
                )}
              />
            </div>
          ))}
        </section>
      )}
    </>
  );
}

function SecondaryEditor(props: Omit<Props, 'section' | 'onClose'>) {
  const boundary = getAt(props.document, '/shaft_boundaries/secondary') as JsonObject | undefined;
  const kind = typeof boundary?.kind === 'string' ? boundary.kind : 'fixed_shaft';
  return (
    <>
      <label className={styles.kindSelect}>
        <span>Physical secondary boundary</span>
        <select
          value={kind}
          onChange={(event) => {
            const next = clone(props.document) as unknown as JsonObject;
            const boundaries = next.shaft_boundaries as JsonObject;
            if (event.target.value === 'fixed_shaft') {
              boundaries.secondary = { kind: 'fixed_shaft', external_torque_Nm: 0, equivalent_inertia_kg_m2: 0 };
            }
            props.onChange(next as unknown as SimulationCaseDocument, props.metrology);
          }}
        >
          <option value="fixed_shaft">Fixed torque / inertia (dyno)</option>
          {kind === 'locked_final_drive' && <option value="locked_final_drive">Locked final-drive vehicle</option>}
        </select>
      </label>
      {kind === 'fixed_shaft' ? (
        <>
          <NumericMeasuredField {...props} pointer="/shaft_boundaries/secondary/external_torque_Nm" label="External torque" unit="N·m" />
          <NumericMeasuredField {...props} pointer="/shaft_boundaries/secondary/equivalent_inertia_kg_m2" label="Equivalent inertia" unit="kg·m²" />
        </>
      ) : (
        <>
          <NumericMeasuredField {...props} pointer="/shaft_boundaries/secondary/vehicle/mass_kg" label="Vehicle mass" unit="kg" />
          <NumericMeasuredField {...props} pointer="/shaft_boundaries/secondary/final_drive/reduction_ratio" label="Final drive reduction" unit="1" />
          <NumericMeasuredField {...props} pointer="/shaft_boundaries/secondary/final_drive/wheel_radius_m" label="Wheel radius" unit="m" />
          <NumericMeasuredField {...props} pointer="/shaft_boundaries/secondary/direct_secondary_shaft_inertia_kg_m2" label="Direct secondary inertia" unit="kg·m²" />
        </>
      )}
    </>
  );
}

export function SetupEditorModal({ section, document, metrology, onChange, onClose }: Props) {
  const [advancedJson, setAdvancedJson] = useState(() => JSON.stringify(
    section === 'cvt' ? (document as unknown as JsonObject).assembly : (document as unknown as JsonObject).shaft_boundaries,
    null,
    2,
  ));
  const title = section === 'primary' ? 'Primary boundary' : section === 'secondary' ? 'Secondary boundary' : 'CVT setup';
  const body = useMemo(() => {
    const shared = { document, metrology, onChange };
    if (section === 'primary') return <PrimaryEditor {...shared} />;
    if (section === 'secondary') return <SecondaryEditor {...shared} />;
    return <>{CVT_FIELDS.map(([pointer, label, unit]) => (
      <NumericMeasuredField key={pointer} {...shared} pointer={pointer} label={label} unit={unit} />
    ))}</>;
  }, [document, metrology, onChange, section]);

  return (
    <div className={styles.backdrop} role="presentation" onMouseDown={onClose}>
      <div className={styles.modal} role="dialog" aria-modal="true" onMouseDown={(event) => event.stopPropagation()}>
        <header><h2>{title}</h2><button type="button" onClick={onClose}>Close</button></header>
        <div className={styles.body}>{body}</div>
        <details className={styles.advanced}>
          <summary>Advanced JSON</summary>
          <p>This is the same canonical setup, not a second copy. Use only for fields not yet surfaced above.</p>
          <textarea value={advancedJson} onChange={(event) => setAdvancedJson(event.target.value)} />
          <button
            type="button"
            onClick={() => {
              const parsed = JSON.parse(advancedJson) as JsonObject;
              const next = clone(document) as unknown as JsonObject;
              if (section === 'cvt') next.assembly = parsed;
              else {
                const boundaries = next.shaft_boundaries as JsonObject;
                const parsedBoundaries = parsed;
                boundaries[section] = parsedBoundaries[section];
              }
              onChange(next as unknown as SimulationCaseDocument, metrology);
            }}
          >Apply advanced JSON</button>
        </details>
      </div>
    </div>
  );
}
