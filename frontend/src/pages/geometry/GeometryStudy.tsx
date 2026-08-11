import { useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { QuantityInput } from '@components/quantityInput/QuantityInput';
import {
  ApiClientError,
  runEndpointRadiiGeometryStudy,
  validateSimulationCase,
  type GeometryStudyResult,
  type ProjectedField,
  type ProjectedScalar,
} from '@api/client';
import { simulationCaseGeometry } from '@api/simulationCaseGeometry';
import { useSimulationCase } from '@contexts/SimulationCaseContext';
import { formatProjectedQuantity, formatQuantity, type QuantityDimension } from '@utils/units';
import styles from './GeometryStudy.module.scss';

type EditableGeometryField = {
  path: string;
  label: string;
  dimension: QuantityDimension;
  canonicalUnit: string;
  description: string;
  minSi?: number;
};

// This only lays out real CINDER document paths on this proof page. It does not
// rename, convert, validate, or map parameters into a separate frontend model.
const FIELDS: readonly EditableGeometryField[] = [
  { path: '/assembly/geometry/belt/height_m', label: 'Belt height', dimension: 'length', canonicalUnit: 'm', description: 'Outer-to-inner belt section height.', minSi: Number.MIN_VALUE },
  { path: '/assembly/geometry/belt/outer_width_m', label: 'Belt outer width', dimension: 'length', canonicalUnit: 'm', description: 'Width at the outer face.', minSi: Number.MIN_VALUE },
  { path: '/assembly/geometry/belt/inner_width_m', label: 'Belt inner width', dimension: 'length', canonicalUnit: 'm', description: 'Width at the inner face.', minSi: Number.MIN_VALUE },
  { path: '/assembly/geometry/belt/cord_depth_from_outer_m', label: 'Cord depth from outer face', dimension: 'length', canonicalUnit: 'm', description: 'Neutral-cord location measured from the outer face.', minSi: 0 },
  { path: '/assembly/geometry/belt_outer_length_m', label: 'Belt outer length', dimension: 'length', canonicalUnit: 'm', description: 'Closed belt outer circumference.', minSi: Number.MIN_VALUE },
  { path: '/assembly/geometry/primary_outer_radius_at_zero_shift_m', label: 'Primary radius at zero shift', dimension: 'length', canonicalUnit: 'm', description: 'Primary outer belt radius at zero global shift.', minSi: Number.MIN_VALUE },
  { path: '/assembly/geometry/secondary_outer_radius_at_zero_shift_m', label: 'Secondary radius at zero shift', dimension: 'length', canonicalUnit: 'm', description: 'Secondary outer belt radius at zero global shift.', minSi: Number.MIN_VALUE },
  { path: '/assembly/geometry/sheave_half_angle_rad', label: 'Sheave half angle', dimension: 'angle', canonicalUnit: 'rad', description: 'Half groove angle used by the belt-radius geometry.', minSi: Number.MIN_VALUE },
  { path: '/assembly/geometry/deadzone_shift_m', label: 'Primary deadzone shift', dimension: 'length', canonicalUnit: 'm', description: 'Shift travel before primary active radial motion.', minSi: 0 },
  { path: '/assembly/geometry/max_shift_m', label: 'Maximum shift', dimension: 'length', canonicalUnit: 'm', description: 'Maximum permitted global CVT shift coordinate.', minSi: 0 },
];

function errorMessage(error: unknown): string {
  if (error instanceof ApiClientError || error instanceof Error) return error.message;
  return String(error);
}

function values(column: ProjectedField): Array<number | null> {
  return Array.isArray(column.values)
    ? column.values.map((value) => typeof value === 'number' ? value : null)
    : [];
}

function indices(count: number): number[] {
  if (count <= 12) return Array.from({ length: count }, (_, index) => index);
  return [...new Set([0, 1, 2, 3, 4, Math.floor(count / 2), count - 5, count - 4, count - 3, count - 2, count - 1])]
    .sort((a, b) => a - b);
}

function Summary({ scalars }: { scalars: ProjectedScalar[] }) {
  return (
    <div className={styles.summary}>
      {scalars.map((item) => (
        <div className={styles.summaryItem} key={item.key}>
          <span>{item.label}</span>
          <strong>{item.value === null ? '—' : formatProjectedQuantity(item.value, item.dimension, item.canonicalUnit, 5)}</strong>
        </div>
      ))}
    </div>
  );
}

function PathTable({ study }: { study: GeometryStudyResult }) {
  const rowCount = study.path.shape[0] ?? 0;
  const sampleRows = indices(rowCount);
  const columns = study.path.columns;
  const byKey = new Map(columns.map((column) => [column.key, values(column)]));
  return (
    <div className={styles.tableScroll}>
      <table className={styles.table}>
        <thead>
          <tr>
            <th>Sample</th>
            {columns.map((column) => <th key={column.key}>{column.label}<small>{column.canonicalUnit}</small></th>)}
          </tr>
        </thead>
        <tbody>
          {sampleRows.map((row, index) => (
            <tr key={row}>
              <td>{index > 0 && row - sampleRows[index - 1] > 1 ? `… ${row}` : row}</td>
              {columns.map((column) => {
                const value = byKey.get(column.key)?.[row] ?? null;
                return <td key={column.key}>{value === null ? '—' : value.toPrecision(7)}</td>;
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/** A deliberately small proof that the new frontend transport path works. */
export const GeometryStudy = () => {
  const navigate = useNavigate();
  const { document, source, validation, loadPreset, setValueAtPath, setValidation, ensureReady } = useSimulationCase();
  const [study, setStudy] = useState<GeometryStudyResult | null>(null);
  useEffect(() => { void ensureReady(); }, [ensureReady]);
  const [busy, setBusy] = useState<'preset' | 'validation' | 'study' | null>(null);
  const [requestError, setRequestError] = useState<string | null>(null);

  const geometry = document === null ? null : simulationCaseGeometry(document);
  const fieldValues = useMemo(() => {
    if (geometry === null) return new Map<string, number>();
    return new Map<string, number>([
      ['/assembly/geometry/belt/height_m', geometry.belt.height_m],
      ['/assembly/geometry/belt/outer_width_m', geometry.belt.outer_width_m],
      ['/assembly/geometry/belt/inner_width_m', geometry.belt.inner_width_m],
      ['/assembly/geometry/belt/cord_depth_from_outer_m', geometry.belt.cord_depth_from_outer_m],
      ['/assembly/geometry/belt_outer_length_m', geometry.belt_outer_length_m],
      ['/assembly/geometry/primary_outer_radius_at_zero_shift_m', geometry.primary_outer_radius_at_zero_shift_m],
      ['/assembly/geometry/secondary_outer_radius_at_zero_shift_m', geometry.secondary_outer_radius_at_zero_shift_m],
      ['/assembly/geometry/sheave_half_angle_rad', geometry.sheave_half_angle_rad],
      ['/assembly/geometry/deadzone_shift_m', geometry.deadzone_shift_m],
      ['/assembly/geometry/max_shift_m', geometry.max_shift_m],
    ]);
  }, [geometry]);

  const invoke = async (kind: 'preset' | 'validation' | 'study', action: () => Promise<void>) => {
    setBusy(kind);
    setRequestError(null);
    try { await action(); }
    catch (error) { setRequestError(errorMessage(error)); }
    finally { setBusy(null); }
  };

  return (
    <main className={styles.page}>
      <header className={styles.header}>
        <div>
          <p className={styles.eyebrow}>Phase 3 transport smoke test</p>
          <h1>Geometry study</h1>
          <p>This route proves preset loading, canonical SI edits, CINDER validation, and one static study. It does not replace the current simulator workflow.</p>
        </div>
        <div className={styles.actions}>
          <button onClick={() => navigate('/')}>Home</button>
          <button onClick={() => navigate('/input')}>Back to simulator</button>
        </div>
      </header>

      <section className={styles.card}>
        <div className={styles.cardHeader}>
          <div>
            <h2>Canonical CINDER document</h2>
            <p>{source ? `${source.name} — ${source.description}` : 'No document is loaded yet.'}</p>
          </div>
          <button disabled={busy !== null} onClick={() => void invoke('preset', async () => {
            await loadPreset('baja-launch-baseline');
            setStudy(null);
          })}>{busy === 'preset' ? 'Loading…' : 'Load Baja baseline'}</button>
        </div>
      </section>

      {document !== null && geometry !== null && <>
        <section className={styles.card}>
          <div className={styles.cardHeader}>
            <div>
              <h2>Geometry inputs</h2>
              <p>Each edit writes directly to the generated CINDER document in canonical SI. The visible units are only a generic presentation layer.</p>
            </div>
            <div className={styles.actions}>
              <button disabled={busy !== null} onClick={() => void invoke('validation', async () => setValidation(await validateSimulationCase(document)))}>{busy === 'validation' ? 'Validating…' : 'Validate document'}</button>
              <button disabled={busy !== null} onClick={() => void invoke('study', async () => {
                setStudy(await runEndpointRadiiGeometryStudy({
                  context: {
                    belt: geometry.belt,
                    belt_outer_length_m: geometry.belt_outer_length_m,
                    sheave_half_angle_rad: geometry.sheave_half_angle_rad,
                    deadzone_shift_m: geometry.deadzone_shift_m,
                    max_shift_m: geometry.max_shift_m,
                  },
                  primary_outer_radius_at_zero_shift_m: geometry.primary_outer_radius_at_zero_shift_m,
                  secondary_outer_radius_at_zero_shift_m: geometry.secondary_outer_radius_at_zero_shift_m,
                  sample_count: 101,
                }));
              })}>{busy === 'study' ? 'Running…' : 'Run geometry study'}</button>
            </div>
          </div>
          <div className={styles.fieldGrid}>
            {FIELDS.map((field) => <QuantityInput key={field.path} {...field} valueSi={fieldValues.get(field.path) ?? 0} onChangeSi={(value) => setValueAtPath(field.path, value)} />)}
          </div>
        </section>

        {validation !== null && <section className={styles.card}>
          <h2>Document validation</h2>
          <p className={validation.isValid ? styles.good : styles.bad}>{validation.isValid ? 'CINDER accepted this document.' : 'CINDER reported validation errors.'}</p>
          {validation.findings.length === 0 ? <p className={styles.muted}>No engineering findings.</p> : <ul className={styles.findings}>
            {validation.findings.map((finding) => <li key={`${finding.code}-${finding.location}`} className={finding.severity === 'error' ? styles.errorFinding : styles.warningFinding}>
              <strong>{finding.severity}</strong> <code>{finding.code}</code> — {finding.message}
              {finding.documentPath && <small>{finding.documentPath}</small>}
            </li>)}
          </ul>}
        </section>}

        {study !== null && <>
          <section className={styles.card}><h2>Geometry summary</h2><Summary scalars={study.summary.scalars} /></section>
          <section className={styles.card}>
            <h2>Feasibility</h2>
            <p className={study.feasibility.isFeasible ? styles.good : styles.bad}>{study.feasibility.isFeasible ? 'The sampled geometry is feasible.' : 'The sampled geometry has feasibility errors.'}</p>
            {study.feasibility.findings.length === 0 ? <p className={styles.muted}>No feasibility findings.</p> : <ul className={styles.findings}>
              {study.feasibility.findings.map((finding) => <li key={`${finding.code}-${finding.shiftM ?? 'global'}`} className={finding.severity === 'error' ? styles.errorFinding : styles.warningFinding}>
                <strong>{finding.severity}</strong> <code>{finding.code}</code> — {finding.message}
                {finding.shiftM !== null && <small>Shift: {formatQuantity(finding.shiftM, 'length')}</small>}
              </li>)}
            </ul>}
          </section>
          <section className={styles.card}>
            <h2>Sampled geometry path</h2>
            <p>{study.path.shape[0] ?? 0} CINDER-generated samples; the table shows a representative subset rather than creating a graph framework.</p>
            <PathTable study={study} />
          </section>
        </>}
      </>}

      {requestError !== null && <section className={`${styles.card} ${styles.errorCard}`}><h2>Request failed</h2><p>{requestError}</p></section>}
    </main>
  );
};
