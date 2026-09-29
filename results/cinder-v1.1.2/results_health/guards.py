"""C04/C05: explicit, finite, mode-aware checks; never discard event endpoints."""
from __future__ import annotations

from collections import Counter
from math import isfinite

from .common import finite, strict_bool

COURSE_LOAD_FIELDS = ('normal_primary_N', 'normal_secondary_N', 'min_tension_N',
                      'primary_min_dN_dtheta_N_per_rad', 'secondary_min_dN_dtheta_N_per_rad')
SUPPORT_REACTIONS = {'lower_stop': 'lower_stop_reaction_N',
                     'low_ratio_seat': 'low_ratio_seat_reaction_N',
                     'upper_stop': 'upper_stop_reaction_N'}


def course_row_failures(row, load_tolerance=1e-5):
    """Keep the existing load tolerance, extending coverage rather than relaxing it.

    Slip-direction acceleration tests at an old kinetic branch's terminal zero
    crossing are NOT added here. Normal loads, tension, support, and finite
    mechanical data remain applicable at both sides of the event.
    """
    if not finite(load_tolerance) or load_tolerance < 0:
        raise ValueError('Invalid course load tolerance')
    if row.get('inspection_error'):
        return ['inspection_error']
    failures = []
    engagement = row.get('engagement')
    if engagement not in ('engaged', 'deadzone'):
        return ['unknown_or_missing_engagement']
    if engagement == 'engaged':
        for key in COURSE_LOAD_FIELDS:
            if not finite(row.get(key)):
                failures.append('nonfinite_' + key)
            elif float(row[key]) < -load_tolerance:
                failures.append('negative_' + key)
        for side in ('primary', 'secondary'):
            try:
                sliding = strict_bool(row.get(side + '_sliding'))
            except ValueError:
                failures.append('missing_' + side + '_contact_classification')
                continue
            for key in (side + '_lambda', side + '_vrel_m_s'):
                if not finite(row.get(key)):
                    failures.append('nonfinite_' + key)
            if sliding:
                key = side + '_slip_loss_W'
                if not finite(row.get(key)):
                    failures.append('nonfinite_' + key)
                elif float(row[key]) < -1e-5:
                    failures.append('energy_adding_' + side + '_sliding')
            else:
                key = side + '_static_utilization'
                if not finite(row.get(key)):
                    failures.append('nonfinite_' + key)
                elif float(row[key]) > 1. + 1e-8:
                    failures.append(side + '_static_capacity')
    for key, value in row.items():
        if key.startswith('mechanism_margin.'):
            if not finite(value):
                failures.append('nonfinite_' + key)
            elif float(value) < -load_tolerance:
                failures.append('negative_' + key)
    reaction = SUPPORT_REACTIONS.get(row.get('shift_constraint'))
    if reaction:
        if not finite(row.get(reaction)):
            failures.append('nonfinite_' + reaction)
        elif float(row[reaction]) < -load_tolerance:
            failures.append('negative_' + reaction)
    return failures


def course_endpoint_audit(rows, tolerance=1e-5):
    issues = []
    for row in rows:
        failed = course_row_failures(row, tolerance)
        if failed:
            issues.append({'time_s': float(row['time_s']),
                           'segment_id': row.get('segment_id'),
                           'sample_location': row.get('sample_location'),
                           'failures': failed})
    return {'checked_rows': len(rows), 'failed_rows': len(issues),
            'failures_by_location': dict(Counter(x['sample_location'] for x in issues)),
            'first_findings': issues[:50],
            'load_tolerance': tolerance, 'event_endpoints_excluded': False}


def belt_run_findings(name, summary):
    """C05: preserve the prior strict nonnegative load criterion and residual caps.

    No new tolerance is invented to turn negative loads into passes. Exact zero
    is allowed. Missing/NaN required metrics are failures, never silent omissions.
    """
    a = summary.get('audit', {})
    issues = []
    if summary.get('completed') is not True:
        issues.append('not_completed')
    if a.get('inspection_errors') != 0:
        issues.append('inspection_errors_or_missing_count')
    if not finite(a.get('engaged_samples')) or float(a['engaged_samples']) <= 0:
        issues.append('no_engaged_samples')
    for side in ('primary', 'secondary'):
        for suffix in ('min_tension_N', 'min_local_normal_N_per_rad'):
            k = side + '.' + suffix
            if not finite(a.get(k)):
                issues.append('nonfinite_' + k)
            elif float(a[k]) < 0.:
                issues.append('negative_' + k)
    for key, limit in (('max_endpoint_vs_equation_residual_N', 1e-8),
                       ('closure.max_abs_residual', 1e-7)):
        if not finite(a.get(key)):
            issues.append('nonfinite_' + key)
        elif abs(float(a[key])) >= limit:
            issues.append('exceeds_limit_' + key)
    return [{'run': name, 'finding': issue} for issue in issues]
