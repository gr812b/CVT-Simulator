"""C02: report sliding dissipation separately from signed sticking drift.

CINDER convention: contact-pair power = lambda * N * relative_speed.
Use the lambda/normal channels directly, matching the dedicated energy study;
there is no need to infer a traction sign from a torque-reporting convention.
"""
from __future__ import annotations

import numpy as np

SLIPPING = {
    'stick_stick': (),
    'primary_slip_secondary_stick': ('primary',),
    'primary_stick_secondary_slip': ('secondary',),
    'both_slip': ('primary', 'secondary'),
}
INJECTION_TOLERANCE_W = 1e-5  # Same guard used by the existing energy study.
DEFINITION = 'sliding_only_negative_lambda_N_vrel_v1'


def cumulative_segmentwise(time, values, ids):
    time, values, ids = np.asarray(time), np.asarray(values), np.asarray(ids)
    if not (time.ndim == values.ndim == ids.ndim == 1 and
            time.size == values.size == ids.size and time.size):
        raise ValueError('Expected non-empty aligned one-dimensional segment arrays')
    if not np.isfinite(time).all() or not np.isfinite(values).all():
        raise ValueError('Nonfinite time/power in an energy integral')
    if np.any(np.diff(time) < 0):
        raise ValueError('Energy samples are not chronological')
    out = np.zeros(time.size, dtype=float)
    seen = set()
    previous = None
    total = 0.
    for i in range(time.size):
        seg = ids[i].item() if hasattr(ids[i], 'item') else ids[i]
        if seg != previous:
            if seg in seen:
                raise ValueError('A continuous segment occurs in disjoint sample blocks')
            seen.add(seg)
            previous = seg
        elif i:
            total += .5 * (time[i] - time[i - 1]) * (values[i] + values[i - 1])
        out[i] = total
    return out


def publication_slip_channels(reported, segment_modes,
                              tolerance_W=INJECTION_TOLERANCE_W):
    """Return new channels and an explicit old/new diagnostic comparison.

    No values in the original result object are changed. The old integrated
    observer remains under its original key. New publication.* keys are used
    by the corrected plotter, so a legacy file cannot silently be reinterpreted.
    """
    if not np.isfinite(tolerance_W) or tolerance_W < 0:
        raise ValueError('Power-injection tolerance must be finite and nonnegative')
    t = np.asarray(reported['time_s'], dtype=float)
    ids = np.asarray(reported['segment_id'], dtype=int)
    if set(np.unique(ids)) != set(segment_modes):
        raise ValueError('Segment modes do not enumerate every retained segment')
    out = {}
    summary = {'definition': DEFINITION, 'injection_tolerance_W': tolerance_W,
               'integration': 'segmentwise trapezoid; distinct incoming/outgoing samples',
               'contacts': {}}
    for side in ('primary', 'secondary'):
        pair = np.zeros(len(t))
        loss = np.zeros(len(t))
        drift = np.zeros(len(t))
        legacy = np.zeros(len(t))
        mask_sliding = np.zeros(len(t), dtype=bool)
        for seg, mode in segment_modes.items():
            ix = np.flatnonzero(ids == seg)
            text = str(mode)
            parts = text.split('/')
            if parts[0] == 'deadzone':
                continue
            if parts[0] != 'engaged' or parts[-1] not in SLIPPING:
                raise ValueError(f'Unsupported contact mode {text!r}; do not assume sticking')
            fields = [np.asarray(reported[f'contact.{side}_{key}'], dtype=float)[ix]
                      for key in ('lambda', 'normal_resultant', 'relative_speed')]
            if not all(np.isfinite(a).all() for a in fields):
                raise ValueError(f'{side}: missing/nonfinite engaged contact channels')
            lam, normal, relative = fields
            if np.any(normal < -1e-8):
                raise ValueError(f'{side}: negative normal force in slip accounting')
            pair[ix] = lam * normal * relative
            legacy[ix] = abs(pair[ix])
            if side in SLIPPING[parts[-1]]:
                mask_sliding[ix] = True
                if np.max(pair[ix]) > tolerance_W:
                    j = ix[int(np.argmax(pair[ix]))]
                    raise ValueError(f'{side}: energy-adding sliding pair power '
                                     f'{pair[j]:.9g} W at t={t[j]:.12g}, segment={seg}')
                # Clip only the declared tiny positive-power roundoff; record it below.
                loss[ix] = np.maximum(0., -pair[ix])
            else:
                drift[ix] = pair[ix]
        loss_E = cumulative_segmentwise(t, loss, ids)
        drift_E = cumulative_segmentwise(t, drift, ids)
        legacy_E = cumulative_segmentwise(t, legacy, ids)
        clipped_E = cumulative_segmentwise(t, np.where(mask_sliding, np.maximum(pair, 0.), 0.), ids)
        out[f'publication.{side}_sliding'] = mask_sliding
        out[f'publication.{side}_pair_power_W'] = pair
        out[f'publication.{side}_slip_power_W'] = loss
        out[f'publication.{side}_slip_dissipation_J'] = loss_E
        out[f'publication.{side}_sticking_drift_power_W'] = drift
        out[f'publication.{side}_sticking_drift_work_J'] = drift_E
        old_key=f'observer.{side}_slip_dissipation'
        observer=(float(reported[old_key][-1]) if old_key in reported else None)
        if observer is not None and not np.isfinite(observer):
            raise ValueError('Nonfinite legacy observer total')
        summary['contacts'][side] = {
            'legacy_observer_total_J': observer,
            'legacy_observer_minus_sliding_J': None if observer is None else float(observer-loss_E[-1]),
            'sliding_loss_J': float(loss_E[-1]),
            'signed_sticking_drift_work_J': float(drift_E[-1]),
            'legacy_absolute_pair_work_J': float(legacy_E[-1]),
            'legacy_minus_sliding_J': float(legacy_E[-1] - loss_E[-1]),
            'max_sliding_pair_power_W': float(np.max(pair[mask_sliding])) if mask_sliding.any() else None,
            'tolerated_positive_sliding_work_J': float(clipped_E[-1]),
        }
    return out, summary
