"""Audit the retained belt discovery outputs, without integrating a model.

This reproduces the historical R1 metric exactly (including its limitations),
checks dimensional term identities, and reconstructs local wrap loading from
saved fields. It does not certify convergence, recover missing event ledgers,
or perform the proposed R2 omission experiment.
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
from pathlib import Path
import zipfile

import numpy as np

ARCHIVE_SHA256 = "9bacf2c5e8df301aa1e1a8bc080de1798222d749e7d338bf5331447da16a98cb"
TERMS = ("radial_shift_acceleration", "radial_geometry_curvature",
         "tangential_belt_acceleration", "tangential_shifting_radius", "normal_contact")
STATES = ("primary_angular_speed_rad_per_s", "secondary_angular_speed_rad_per_s",
          "belt_speed_m_per_s", "shift_position_m", "shift_speed_m_per_s")


def arrays(rows):
    out = {}
    for key in rows[0]:
        try:
            out[key] = np.array([float(r[key]) if r[key] else np.nan for r in rows])
        except ValueError:
            out[key] = np.array([r[key] for r in rows])
    return out


def read_archive(path):
    if hashlib.sha256(path.read_bytes()).hexdigest() != ARCHIVE_SHA256:
        raise ValueError("Expected the retained 20260916-222846 belt archive")
    cases, hashes = {}, {}
    with zipfile.ZipFile(path) as z:
        def read(name):
            data = z.read(name)
            hashes[name] = hashlib.sha256(data).hexdigest()
            return data
        for name in sorted(z.namelist()):
            if not name.endswith('/belt_terms.csv'):
                continue
            root = name.rsplit('/', 1)[0]
            rows = list(csv.DictReader(io.StringIO(read(name).decode())))
            cases[root.split('/')[-1]] = {
                'data': arrays(rows),
                **{key: json.loads(read(root + '/' + file)) for key, file in
                   [('document', 'simulation_case.json'), ('protocol', 'protocol.json'),
                    ('run', 'run_summary.json')]}}
        summaries = {fn: list(csv.DictReader(io.StringIO(read('artifacts/' + fn).decode())))
                     for fn in ('inertia_continuation_comparison.csv', 'closure_failures.csv',
                                'controlled_load_summary.csv', 'baja_envelope_observed_coverage.csv',
                                'contact_stick_targets.csv', 'overrun_summary.csv')}
    return cases, summaries, hashes


def local_loading(d, assembly):
    """Monotone analytical wrap solution: extrema are at its two ends.

    Recover phi=(2 sin(beta)-lambda H)/G from the saved regular factors.
    Then use the frozen 1.1.2 endpoint map (results/fields/belt.py).
    Normal loading is (T-C)/sin(beta), C=q(v_b^2-r*r_ddot).
    """
    g = assembly['geometry']
    b = g['belt']
    sb = np.sin(g['sheave_half_angle_rad'])
    q = assembly['inertias']['belt_density_kg_per_m3'] * b['height_m'] * (b['outer_width_m'] + b['inner_width_m']) / 2
    sd, sdd = (d['state.' + k] for k in ('shift_speed_m_per_s', 'shift_acceleration_m_per_s2'))
    vb, vd = (d['state.' + k] for k in ('belt_speed_m_per_s', 'belt_acceleration_m_per_s2'))
    out = {}
    for side in ('primary', 'secondary'):
        lam = d['contact.' + side + '_lambda']
        H, G = (d['coefficient.' + side + '_' + k] for k in ('H', 'G'))
        wrap = (2 * sb - lam * H) / G
        if np.any((wrap <= 0) | (wrap >= 2 * np.pi)):
            raise ValueError('Invalid reconstructed wrap angle')
        z = lam * wrap / sb
        small = abs(z) < 1e-4
        phi, psi = np.empty_like(z), np.empty_like(z)
        a = z[small]
        phi[small] = 1-a/2+a**2/6-a**3/24+a**4/120
        psi[small] = .5-a/6+a**2/24-a**3/120+a**4/720
        a = z[~small]
        phi[~small] = -np.expm1(-a)/a
        psi[~small] = (a+np.expm1(-a))/a**2
        radius, rp, rpp = (d['geometry.' + side + k] for k in
                          ('_radius_cm_m', '_d_radius_ds', '_d2_radius_ds2_per_m'))
        A = q * (radius * vd + rp * sd * vb)
        C = q * (vb**2 - radius * (rp * sdd + rpp * sd**2))
        incoming = d['contact.' + side + '_normal_N'] * sb / (wrap * phi) - A * wrap * psi / phi
        outgoing = np.exp(-z) * incoming + A * wrap * phi
        out[side + '_min_local_N_per_rad'] = np.minimum(incoming, outgoing) / sb
        out[side + '_min_tension_N'] = C + np.minimum(incoming, outgoing)
        out[side + '_wrap_rad'] = wrap
        out[side + '_endpoint_sum_N'] = 2*C + incoming + outgoing
    out['endpoint_sum_difference_N'] = out['primary_endpoint_sum_N'] - out['secondary_endpoint_sum_N']
    return out


def point(d, i):
    keys = ['time_s', 'segment_index', 'native_index', 'regime.contact_mode',
            'regime.shift_constraint', 'state.shift_position_m', 'state.shift_speed_m_per_s',
            'state.belt_speed_m_per_s', 'loop.activity_scale_N', 'loop.contact_scale_N',
            'boundary.primary_power_W', 'boundary.secondary_power_W']
    keys += ['loop.' + t + '_N' for t in TERMS]
    keys += ['loop.share.' + t for t in TERMS]
    return {k: d[k][i].item() for k in keys}


def historical_metric(reference, variant):
    # Deliberately reproduce the original algorithm, NOT a new hybrid metric.
    def series(d, key):
        pairs = sorted(zip(d['time_s'], d['state.' + key]), key=lambda p: p[0])
        t, y = [], []
        for ti, yi in pairs:
            if not (np.isfinite(ti) and np.isfinite(yi)):
                continue
            if t and abs(ti-t[-1]) <= 1e-12:
                y[-1] = yi  # historical last-side rule at duplicate event time
            else:
                t.append(ti); y.append(yi)
        return np.array(t), np.array(y)
    tr, _ = series(reference, STATES[0]); tv, _ = series(variant, STATES[0])
    grid = np.linspace(max(tr[0], tv[0]), min(tr[-1], tv[-1]), 1000)
    result = {}
    for key in STATES:
        a = np.interp(grid, *series(reference, key))
        b = np.interp(grid, *series(variant, key))
        scale = max(float(np.ptp(a)), float(np.max(abs(a))), 1e-12)
        rmse = float(np.sqrt(np.mean((b-a)**2)))
        result[key] = {'rmse': rmse, 'normalizer': scale, 'fraction': rmse/scale,
                       'percent': 100*rmse/scale, 'max_abs_error': float(np.max(abs(b-a)))}
    return {'window_s': [float(grid[0]), float(grid[-1])], 'states': result}


def saved_segment_modes(d):
    """Available engaged-mode sequence, explicitly not a full event signature."""
    _, indices = np.unique(d['segment_index'], return_index=True)
    keys = ('regime.contact_mode', 'regime.shift_constraint',
            'regime.primary_slip_direction', 'regime.secondary_slip_direction')
    return [[d[k][i].item() for k in keys] for i in sorted(indices)]


def audit(path, output):
    cases, summaries, hashes = read_archive(path)
    result = {'archive': path.name, 'archive_sha256': ARCHIVE_SHA256,
              'scope': 'Retained-output audit only; zero new integrations. Discovery outputs are not final convergence evidence.',
              'case_count': len(cases), 'cases': {}, 'R1': [], 'source_sha256': hashes,
              'R2': 'Unrun; no omission outcome inferred from observed term sizes.',
              'limitations': [
                  'Original runs use rtol=0.01, atol=1e-5, max_step=0.05 s; selected publication cases need refinement.',
                  'belt_terms.csv retains engaged native samples, not full event/reset ledgers or disengaged trajectories.',
                  'R1 reproduces 1000-point linear interpolation after retaining the last duplicate-time row; it can interpolate across jumps.',
                  'Unchanged transition counts do not establish equal ordered events, reset maps, or event timing.',
                  'Local-loading checks cover saved engaged states, not an unsampled continuous domain.',
                  'Archive does not include a complete executed-runtime manifest; release attribution comes from frozen study ownership and source, not a binary attestation.']}
    for name, case in cases.items():
        d, doc = case['data'], case['document']
        loading = local_loading(d, doc['assembly'])
        local_min = {k: float(np.min(v)) for k, v in loading.items() if '_min_' in k}
        loop_error = float(np.max(abs(sum(d['loop.' + t + '_N'] for t in TERMS))))
        identity_error = float(np.max(abs(loading['endpoint_sum_difference_N'] - d['loop.residual_N'])))
        assert loop_error < 1e-7 and identity_error < 1e-7
        assert np.max(abs(loading['primary_wrap_rad'] + loading['secondary_wrap_rad'] - 2*np.pi)) < 1e-9
        record = {'family': case['protocol']['family'], 'protocol': case['protocol'],
                  'run': case['run'], 'settings': doc['execution']['integrator'],
                  'saved_engaged_rows': len(d['time_s']), 'minimum_loading': local_min,
                  'saved_segment_modes': saved_segment_modes(d),
                  'max_loop_residual_N': loop_error, 'max_endpoint_identity_error_N': identity_error,
                  'max_transport_residual_N': float(np.max(abs(d['transport.residual_N']))),
                  'peaks': {}}
        for label, mask in [('all_engaged', np.ones(len(d['time_s']), dtype=bool)),
                            ('after_0p1s', d['time_s'] >= .1)]:
            record['peaks'][label] = {}
            for term in TERMS[:-1]:
                for kind, key in [('force', 'loop.' + term + '_N'), ('share', 'loop.share.' + term)]:
                    i = int(np.argmax(np.where(mask, abs(d[key]), -np.inf)))
                    record['peaks'][label][term + '_' + kind] = point(d, i)
        g = doc['assembly']['geometry']
        record['travel_definition'] = {'archived': 's/max_shift', 'active': '(s-deadzone)/(max_shift-deadzone)',
                                       'deadzone_m': g['deadzone_shift_m'], 'max_shift_m': g['max_shift_m']}
        result['cases'][name] = record
    for row in summaries['inertia_continuation_comparison.csv']:
        name = row['case']
        ref = cases['inertia_' + row['scenario'] + '_reference']['data']
        comparison = historical_metric(ref, cases[name]['data'])
        for key, metric in comparison['states'].items():
            assert abs(metric['fraction'] - float(row[key + '_normalized_rmse'])) < 1e-13
        worst = max(comparison['states'], key=lambda k: comparison['states'][k]['fraction'])
        result['R1'].append({'case': name, 'kind': row['kind'], 'scale': float(row['scale']),
                             'worst_state': worst, 'worst_percent': comparison['states'][worst]['percent'],
                             'saved_engaged_mode_sequence_equal': saved_segment_modes(ref) == saved_segment_modes(cases[name]['data']),
                             'transition_count_delta': int(row['transition_count_delta']), **comparison})
    result['archived_summaries'] = summaries
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, allow_nan=False) + '\n')
    print(f'Audited {len(cases)} retained cases; wrote {output}')
    return cases, result
