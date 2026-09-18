import { useMemo, useState } from 'react';
import type { ChannelConfig, MeasurementUncertainty } from '@pages/validation/types';
import {
  measurementUncertaintySeries,
  summarizeUncertainty,
} from '@pages/validation/data';
import styles from './MeasurementUncertaintyModal.module.scss';

type Props = {
  channel: ChannelConfig;
  values: number[];
  onSave: (uncertainty: MeasurementUncertainty) => void;
  onClose: () => void;
};

function finitePositive(value: number | undefined): boolean {
  return value !== undefined && Number.isFinite(value) && value > 0;
}

function format(value: number): string {
  if (value >= 100) return value.toFixed(1);
  if (value >= 10) return value.toFixed(2);
  return value.toFixed(3);
}

export function MeasurementUncertaintyModal({ channel, values, onSave, onClose }: Props) {
  const isRpm = channel.mapping === 'primary_speed' || channel.mapping === 'secondary_speed' || channel.unit.toLowerCase() === 'rpm';
  const [draft, setDraft] = useState<MeasurementUncertainty>(() => ({
    ...channel.uncertainty,
    model: channel.uncertainty.model ?? (isRpm ? 'rpm_tooth_timing' : 'absolute'),
    replaySampleIntervalS: channel.uncertainty.replaySampleIntervalS ?? (isRpm ? 0.01 : undefined),
  }));

  const derived = useMemo(
    () => summarizeUncertainty(measurementUncertaintySeries(values, draft)),
    [draft, values],
  );

  const timingComplete = finitePositive(draft.teethPerRevolution)
    && draft.timestampUncertaintyS !== undefined
    && Number.isFinite(draft.timestampUncertaintyS)
    && draft.timestampUncertaintyS >= 0;

  const save = () => {
    const next = { ...draft };
    if (next.status !== 'not_applicable') {
      if (isRpm && next.model === 'rpm_tooth_timing') {
        next.status = timingComplete ? 'known' : 'pending';
      } else if (!isRpm && next.model === 'absolute') {
        next.status = next.absolute !== undefined && Number.isFinite(next.absolute) && next.absolute >= 0
          ? 'known'
          : 'pending';
      }
    }
    onSave(next);
    onClose();
  };

  return (
    <div className={styles.backdrop} role="presentation" onMouseDown={onClose}>
      <div className={styles.modal} role="dialog" aria-modal="true" onMouseDown={(event) => event.stopPropagation()}>
        <header className={styles.header}>
          <div>
            <span className={styles.eyebrow}>Measurement model</span>
            <h2>{channel.label} uncertainty</h2>
          </div>
          <button className={styles.ghostButton} type="button" onClick={onClose}>Close</button>
        </header>

        {isRpm ? (
          <>
            <section className={styles.callout}>
              <strong>Tooth-timing RPM</strong>
              <p>
                Each RPM sample is treated as one tooth-period estimate. If each tooth-hit timestamp is known within ±δt,
                the interval gets a conservative ±2δt bound and the RPM uncertainty is computed separately at every point.
              </p>
              <code>RPM = 60 / (teeth × tooth interval)</code>
            </section>

            <div className={styles.fieldGrid}>
              <label>
                <span>Teeth per revolution</span>
                <input
                  type="number"
                  min="1"
                  step="1"
                  value={draft.teethPerRevolution ?? ''}
                  placeholder="e.g. 18"
                  onChange={(event) => setDraft((current) => ({
                    ...current,
                    model: 'rpm_tooth_timing',
                    teethPerRevolution: event.target.value === '' ? undefined : Number(event.target.value),
                  }))}
                />
              </label>
              <label>
                <span>Timestamp uncertainty ± [µs]</span>
                <input
                  type="number"
                  min="0"
                  step="any"
                  value={draft.timestampUncertaintyS === undefined ? '' : draft.timestampUncertaintyS * 1e6}
                  placeholder="DAQ timing bound"
                  onChange={(event) => setDraft((current) => ({
                    ...current,
                    model: 'rpm_tooth_timing',
                    timestampUncertaintyS: event.target.value === '' ? undefined : Number(event.target.value) / 1e6,
                  }))}
                />
              </label>
              <label>
                <span>Replay grid spacing [ms]</span>
                <input
                  type="number"
                  min="0.1"
                  step="0.1"
                  value={(draft.replaySampleIntervalS ?? 0.01) * 1000}
                  onChange={(event) => setDraft((current) => ({
                    ...current,
                    replaySampleIntervalS: Number(event.target.value) / 1000,
                  }))}
                />
                <small>Used to resample the replay reference uniformly. This is interpolation only; no smoothing filter is implied.</small>
              </label>
            </div>

            <section className={styles.derivedCard}>
              <span>Pointwise RPM uncertainty</span>
              {derived === null ? (
                <strong>Enter teeth/rev and timestamp uncertainty</strong>
              ) : (
                <strong>
                  median ±{format(derived.median)} rpm · range ±{format(derived.minimum)}–{format(derived.maximum)} rpm
                </strong>
              )}
            </section>
          </>
        ) : (
          <div className={styles.fieldGrid}>
            <label>
              <span>Absolute uncertainty ± [{channel.unit || 'units'}]</span>
              <input
                type="number"
                min="0"
                step="any"
                value={draft.absolute ?? ''}
                onChange={(event) => setDraft((current) => ({
                  ...current,
                  model: 'absolute',
                  absolute: event.target.value === '' ? undefined : Number(event.target.value),
                  unit: channel.unit,
                }))}
              />
            </label>
          </div>
        )}

        <div className={styles.notesGrid}>
          <label>
            <span>Source / method</span>
            <input
              value={draft.source ?? ''}
              placeholder={isRpm ? 'e.g. Teensy hardware timestamp' : 'Instrument or calibration source'}
              onChange={(event) => setDraft((current) => ({ ...current, source: event.target.value }))}
            />
          </label>
          <label>
            <span>Notes</span>
            <textarea
              value={draft.notes ?? ''}
              placeholder="Optional uncertainty assumptions or calibration notes"
              onChange={(event) => setDraft((current) => ({ ...current, notes: event.target.value }))}
            />
          </label>
        </div>

        <footer className={styles.footer}>
          <button type="button" className={styles.secondaryButton} onClick={() => {
            onSave({ ...draft, status: 'not_applicable' });
            onClose();
          }}>Mark N/A</button>
          <button type="button" className={styles.primaryButton} onClick={save}>Save uncertainty</button>
        </footer>
      </div>
    </div>
  );
}
