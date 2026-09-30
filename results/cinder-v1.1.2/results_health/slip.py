"""Sliding-loss accounting and its reporting checks, separate from retention.

Pair power is lambda*N*v_rel on either contact. A numerical contact mode can
remain kinetic when |v_rel| is inside CINDER's near-zero speed band. A fixed
power cutoff is not invariant to contact force, so small positive power there
is recorded as signed numerical work, not silently converted into heat.

This module changes reporting only. It does not modify the mechanics package,
friction coefficients, event tolerances, solver settings, or state histories.
"""
from __future__ import annotations

import numpy as np

SLIPPING = {
    'stick_stick': (),
    'primary_slip_secondary_stick': ('primary',),
    'primary_stick_secondary_slip': ('secondary',),
    'both_slip': ('primary', 'secondary'),
}
INJECTION_TOLERANCE_W = 1e-5  # Original reporting floor, now integrated in time.
RELATIVE_SPEED_TOLERANCE_M_PER_S = 1e-7
# Pinned source: cinder.model.cvt.contact.tolerances.ContactKinematicTolerances
# at CINDER 1.1.2 / 7637a38b4fb9ec21dfb953c1c80a27ec5f389654.
# This is NOT an instruction to change that model tolerance.
POSITIVE_WORK_RELATIVE_ALLOWANCE = 1e-6  # Declared reporting precision criterion.
DEFINITION = 'sliding_only_negative_lambda_N_vrel_v2'
HEALTH_POLICY = 'near_zero_speed_and_accumulated_positive_work_v1'


def cumulative_segmentwise(time, values, ids):
    """Integrate within segments; never bridge distinct event-side samples.

    This general helper permits disconnected retained intervals. Full-run
    coverage is checked separately by publication_slip_channels/trace_check.
    """
    time, values, ids = np.asarray(time), np.asarray(values), np.asarray(ids)
    if not (time.ndim == values.ndim == ids.ndim == 1 and
            time.size == values.size == ids.size and time.size):
        raise ValueError('Expected non-empty aligned one-dimensional segment arrays')
    if not np.isfinite(time).all() or not np.isfinite(values).all():
        raise ValueError('Nonfinite time/power in an energy integral')
    if np.any(np.diff(time) < 0):
        raise ValueError('Energy samples are not chronological')
    out = np.zeros(time.size, dtype=float)
    seen, previous, total = set(), None, 0.
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


def _positive_number(name, value, *, allow_zero=False):
    if not np.isfinite(value) or value < 0 or (value == 0 and not allow_zero):
        raise ValueError(f'{name} must be finite and ' + ('nonnegative' if allow_zero else 'positive'))


def require_slip_health(summary):
    """Publication gate. Failed accounting remains available for diagnosis."""
    if summary.get('definition') != DEFINITION or summary.get('health_policy') != HEALTH_POLICY:
        raise ValueError('Slip-accounting record has an old or unknown definition/policy')
    if summary.get('health', {}).get('passed') is not True:
        reasons = summary.get('health', {}).get('findings', ['missing health result'])
        raise ValueError('energy-adding sliding or unresolved accounting: ' + '; '.join(map(str, reasons)))


def publication_slip_channels(reported, segment_modes,
                              tolerance_W=INJECTION_TOLERANCE_W, *,
                              relative_speed_tolerance=RELATIVE_SPEED_TOLERANCE_M_PER_S,
                              positive_work_rtol=POSITIVE_WORK_RELATIVE_ALLOWANCE,
                              enforce_health=True):
    """Return derived arrays and old/new totals; do not mutate input channels.

    Acceptance requires BOTH:
      1. Positive sliding pair power occurs only inside the declared numerical
         near-zero relative-speed band, up to arithmetic roundoff.
      2. Its integrated work is <= tolerance_W*T + positive_work_rtol*E_loss.
         T is the total retained continuous duration, E_loss is the nonnegative
         dissipative part of sliding work. The latter is a reporting precision
         criterion, NOT an added physical force, calibration, or ODE tolerance.

    Retention calls enforce_health=False so it can save a complete failed
    diagnostic. Publication and direct callers use True. No positive work is
    concealed: gross dissipation, positive work, and net removed work are all
    returned. Sticking drift stays separate.
    """
    _positive_number('Power floor', tolerance_W, allow_zero=True)
    _positive_number('Relative-speed tolerance', relative_speed_tolerance)
    _positive_number('Positive-work relative allowance', positive_work_rtol, allow_zero=True)
    t = np.asarray(reported['time_s'], dtype=float)
    raw_ids = np.asarray(reported['segment_id'])
    if t.ndim != 1 or raw_ids.shape != t.shape or not t.size:
        raise ValueError('Report time/segment columns are not nonempty aligned vectors')
    if not np.isfinite(raw_ids).all() or not np.equal(raw_ids, np.floor(raw_ids)).all():
        raise ValueError('Invalid segment identifiers')
    ids = raw_ids.astype(np.int64)
    if set(np.unique(ids)) != set(segment_modes):
        raise ValueError('Segment modes do not enumerate every retained segment')
    # Validate chronological contiguous blocks. A full-run report cannot omit
    # an interval between one segment's end and the next segment's start.
    duration = float(cumulative_segmentwise(t, np.ones(len(t)), ids)[-1])
    jumps = ids[1:] != ids[:-1]
    scale = max(1., float(np.max(np.abs(t))))
    if np.any(np.abs(np.diff(t)[jumps]) > 128 * np.finfo(float).eps * scale):
        raise ValueError('Missing continuous interval between retained segment sides')

    out = {}
    summary = {
        'definition': DEFINITION, 'health_policy': HEALTH_POLICY,
        'injection_tolerance_W': float(tolerance_W),
        'relative_speed_tolerance_m_per_s': float(relative_speed_tolerance),
        'positive_work_relative_allowance': float(positive_work_rtol),
        'retained_continuous_duration_s': duration,
        'integration': 'segmentwise trapezoid; distinct incoming/outgoing samples',
        'contacts': {}, 'health': {'passed': True, 'findings': []},
    }
    endpoint = np.zeros(len(t), bool)
    for seg in segment_modes:
        ix = np.flatnonzero(ids == seg)
        endpoint[ix[[0, -1]]] = True

    for side in ('primary', 'secondary'):
        pair = np.zeros(len(t)); loss = np.zeros(len(t)); drift = np.zeros(len(t))
        relative_all = np.zeros(len(t)); force_all = np.zeros(len(t))
        mask_sliding = np.zeros(len(t), dtype=bool)
        for seg, mode in segment_modes.items():
            ix = np.flatnonzero(ids == seg)
            parts = str(mode).split('/')
            if parts[0] == 'deadzone':
                continue
            if parts[0] != 'engaged' or parts[-1] not in SLIPPING:
                raise ValueError(f'Unsupported contact mode {mode!r}; do not assume sticking')
            fields = []
            for key in ('lambda', 'normal_resultant', 'relative_speed'):
                values = np.asarray(reported[f'contact.{side}_{key}'], dtype=float)
                if values.shape != t.shape:
                    raise ValueError(f'{side}: unaligned {key} channel')
                fields.append(values[ix])
            if not all(np.isfinite(a).all() for a in fields):
                raise ValueError(f'{side}: missing/nonfinite engaged contact channels')
            lam, normal, relative = fields
            if np.any(normal < -1e-8):
                raise ValueError(f'{side}: negative normal force in slip accounting')
            force_all[ix] = lam * normal
            relative_all[ix] = relative
            pair[ix] = force_all[ix] * relative
            if not np.isfinite(pair[ix]).all():
                raise ValueError(f'{side}: overflow/nonfinite pair power')
            if side in SLIPPING[parts[-1]]:
                mask_sliding[ix] = True
                loss[ix] = np.maximum(0., -pair[ix])
            else:
                drift[ix] = pair[ix]

        positive = np.where(mask_sliding, np.maximum(pair, 0.), 0.)
        loss_E = cumulative_segmentwise(t, loss, ids)
        positive_E = cumulative_segmentwise(t, positive, ids)
        drift_E = cumulative_segmentwise(t, drift, ids)
        legacy_E = cumulative_segmentwise(t, abs(pair), ids)
        # The slack below covers floating-point comparisons, not an enlarged
        # physical near-zero band. Both incoming and outgoing rows are tested.
        speed_slack = 64 * np.finfo(float).eps * np.maximum(1., abs(relative_all))
        near_zero = abs(relative_all) <= relative_speed_tolerance + speed_slack
        power_roundoff = 64 * np.finfo(float).eps * np.maximum(1., abs(force_all)) * np.maximum(1., abs(relative_all))
        bad = mask_sliding & ~near_zero & (pair > power_roundoff)
        allowance = tolerance_W * duration + positive_work_rtol * float(loss_E[-1])
        budget_ok = float(positive_E[-1]) <= allowance + 64 * np.finfo(float).eps * max(1., allowance)
        nonzero_positive = mask_sliding & (pair > 0)
        worst = int(np.argmax(positive)) if np.any(positive > 0) else None
        examples = [
            {'time_s': float(t[i]), 'segment_id': int(ids[i]),
             'pair_power_W': float(pair[i]), 'relative_speed_m_per_s': float(relative_all[i]),
             'retained_endpoint': bool(endpoint[i])}
            for i in np.flatnonzero(bad)[:12]
        ]
        if bad.any():
            summary['health']['findings'].append(
                f'{side}: {int(bad.sum())} positive-power samples outside the numerical zero-speed band; '
                f'first t={examples[0]["time_s"]:.12g}, v_rel={examples[0]["relative_speed_m_per_s"]:.9g} m/s')
        if not budget_ok:
            summary['health']['findings'].append(
                f'{side}: positive sliding work {positive_E[-1]:.9g} J exceeds reporting allowance {allowance:.9g} J')

        out[f'publication.{side}_sliding'] = mask_sliding
        out[f'publication.{side}_pair_power_W'] = pair
        out[f'publication.{side}_slip_power_W'] = loss
        out[f'publication.{side}_slip_dissipation_J'] = loss_E
        out[f'publication.{side}_sticking_drift_power_W'] = drift
        out[f'publication.{side}_sticking_drift_work_J'] = drift_E
        out[f'publication.{side}_positive_sliding_power_W'] = positive
        out[f'publication.{side}_positive_sliding_work_J'] = positive_E
        out[f'publication.{side}_net_sliding_work_removed_J'] = loss_E - positive_E
        out[f'publication.{side}_legacy_absolute_pair_work_J'] = legacy_E
        old_key = f'observer.{side}_slip_dissipation'
        observer = float(reported[old_key][-1]) if old_key in reported else None
        if observer is not None and not np.isfinite(observer):
            raise ValueError('Nonfinite legacy observer total')
        summary['contacts'][side] = {
            'legacy_observer_total_J': observer,
            'legacy_observer_minus_sliding_J': None if observer is None else float(observer - loss_E[-1]),
            'sliding_loss_J': float(loss_E[-1]),
            'net_sliding_work_removed_J': float(loss_E[-1] - positive_E[-1]),
            'signed_sticking_drift_work_J': float(drift_E[-1]),
            'legacy_absolute_pair_work_J': float(legacy_E[-1]),
            'legacy_minus_sliding_J': float(legacy_E[-1] - loss_E[-1]),
            'max_sliding_pair_power_W': float(np.max(pair[mask_sliding])) if mask_sliding.any() else None,
            'positive_sliding_work_J': float(positive_E[-1]),
            'tolerated_positive_sliding_work_J': float(positive_E[-1]) if not bad.any() and budget_ok else None,
            'positive_work_allowance_J': float(allowance),
            'positive_work_fraction_of_dissipation': float(positive_E[-1] / loss_E[-1]) if loss_E[-1] > 0 else None,
            'positive_sample_count': int(nonzero_positive.sum()),
            'positive_endpoint_sample_count': int((nonzero_positive & endpoint).sum()),
            'positive_interior_sample_count': int((nonzero_positive & ~endpoint).sum()),
            'outside_speed_band_count': int(bad.sum()), 'outside_speed_band_examples': examples,
            'max_positive_power_sample': None if worst is None else {
                'time_s': float(t[worst]), 'segment_id': int(ids[worst]),
                'power_W': float(positive[worst]), 'relative_speed_m_per_s': float(relative_all[worst]),
                'near_zero_speed': bool(near_zero[worst]), 'retained_endpoint': bool(endpoint[worst])},
            'sign_check_passed': not bool(bad.any()), 'work_budget_passed': bool(budget_ok),
        }
    summary['health']['passed'] = not summary['health']['findings']
    if enforce_health:
        require_slip_health(summary)
    return out, summary


def verify_publication_slip_channels(reported, segment_modes):
    """Rebuild from lambda/N/v_rel, check recorded arrays, then enforce health."""
    expected, summary = publication_slip_channels(reported, segment_modes, enforce_health=False)
    for key, values in expected.items():
        if key not in reported:
            raise ValueError(f'Missing corrected accounting channel: {key}')
        observed = np.asarray(reported[key])
        if observed.shape != values.shape or not np.isfinite(observed).all():
            raise ValueError(f'Nonfinite or unaligned recorded accounting channel: {key}')
        if values.dtype == bool:
            matches = np.array_equal(observed, values)
        else:
            matches = np.allclose(observed, values, rtol=1e-12, atol=1e-10)
        if not matches:
            raise ValueError(f'Recorded slip accounting does not match contact reconstruction: {key}')
    require_slip_health(summary)
    return summary
