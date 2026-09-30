"""Preparation-only repairs: portable manifests, LFS data, and exported margins.

No solver calls or mechanical-law substitutions. Historical raw files are read,
never rewritten. Missing evidence and nonfinite physical quantities still fail.
"""
from __future__ import annotations
import csv
import hashlib
import math
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess

from .common import MissingEvidence, digest, read_json, write_json

PRIMARY_SCREEN_SHA256 = '4499dfb01068c0f21bf528d0d4ef1861c3c6a3b043d165b787395ca8de4b9dbb'
PRIMARY_SCREEN_BYTES = 10366
PRIMARY_FORCE_COMPONENTS = (
    'primary.fixed_pivot_flyweight_centrifugal_N',
    'primary.fixed_pivot_flyweight_axial_inertia_N',
    'primary.fixed_pivot_flyweight_motion_ratio_curvature_N',
)


def portable_key(value):
    """Canonical relative manifest key; separators are not part of identity."""
    text = str(value).replace('\\', '/')
    p = PurePosixPath(text)
    if not text or p.as_posix() == '.' or p.is_absolute() or '..' in p.parts or ':' in text or '\x00' in text:
        raise ValueError('Unsafe relative evidence path: ' + repr(value))
    return p.as_posix()


def portable_hashes(mapping):
    out = {}
    for key, value in mapping.items():
        key = portable_key(key)
        if key in out and out[key] != value:
            raise ValueError('Conflicting hashes for the same portable path: ' + key)
        out[key] = value
    return out


def path_below(root, relative):
    root = Path(root).resolve()
    path = (root / portable_key(relative)).resolve()
    if not path.is_relative_to(root):
        raise ValueError('Evidence path escapes its root: ' + str(relative))
    return path


def lfs_pointer(path):
    """Return pointer metadata, or None for actual data. Never parse as CSV."""
    path = Path(path)
    if not path.is_file():
        raise MissingEvidence('Missing required data file: ' + str(path))
    if path.stat().st_size > 2048:
        return None
    text = path.read_bytes().decode('utf-8-sig', errors='replace').replace('\r\n', '\n')
    if not text.startswith('version https://git-lfs.github.com/spec/v1\n'):
        return None
    oid = re.search(r'^oid sha256:([0-9a-f]{64})$', text, re.M)
    size = re.search(r'^size ([0-9]+)$', text, re.M)
    if not oid or not size:
        raise ValueError('Malformed Git LFS pointer: ' + str(path))
    return {'sha256': oid[1], 'bytes': int(size[1])}


def require_data(path):
    metadata = lfs_pointer(path)
    if metadata:
        raise MissingEvidence(f'{path} is a Git LFS pointer, not its data '
                              f'({metadata["bytes"]} bytes, SHA256 {metadata["sha256"]}). '
                              'Use the localized prep runner with --fetch-lfs, '
                              'or hydrate this exact file with Git LFS.')
    return Path(path)


def git(repo, arguments):
    try:
        return subprocess.check_output(['git', '-C', str(repo), *arguments], text=True,
                                       stderr=subprocess.STDOUT).strip()
    except (OSError, subprocess.CalledProcessError) as exc:
        message = getattr(exc, 'output', '') or str(exc)
        raise MissingEvidence('Git data recovery failed: ' + message) from exc


def materialize_asset(source, target, repo, *, fetch=False):
    """Copy verified content into the new preparation, leaving tracked files alone.

    --fetch-lfs permits a targeted `git lfs fetch`; it does not checkout/smudge
    files or alter the working tree. Otherwise only the existing local LFS store
    is used. The copied bytes must match the pointer's SHA256 AND byte count.
    """
    source, target, repo = Path(source).resolve(), Path(target).resolve(), Path(repo).resolve()
    info = lfs_pointer(source)
    location = source
    if info:
        local = git(repo, ['rev-parse', '--git-path', 'lfs/objects'])
        store = Path(local)
        if not store.is_absolute():
            store = repo / store
        oid = info['sha256']
        location = store / oid[:2] / oid[2:4] / oid
        if not location.is_file() and fetch:
            if not source.is_relative_to(repo):
                raise MissingEvidence('Cannot fetch an untracked external LFS pointer: ' + str(source))
            ref = git(repo, ['rev-parse', 'HEAD'])
            include = source.relative_to(repo).as_posix()
            # The remote is explicitly the repository's origin; no arbitrary URL
            # from an untrusted pointer or evidence file is executed.
            git(repo, ['lfs', 'fetch', '--include=' + include, '--exclude=', 'origin', ref])
        if not location.is_file():
            raise MissingEvidence('Git LFS object is unavailable locally: ' + str(source)
                                  + '. Rerun with --fetch-lfs or restore the exact object.')
        if location.stat().st_size != info['bytes'] or digest(location) != info['sha256']:
            raise ValueError('Git LFS object failed SHA256/size verification: ' + str(source))
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.is_file() and digest(target) != digest(location):
        raise FileExistsError('Refusing to overwrite a different prepared input: ' + str(target))
    if location != target:
        shutil.copy2(location, target)
    return {'source': str(source), 'copied_from': str(location), 'sha256': digest(target),
            'bytes': target.stat().st_size, 'was_lfs_pointer': bool(info),
            'working_tree_modified': False, 'target': str(target)}


def validate_primary_screen(path, *, expected_sha=PRIMARY_SCREEN_SHA256):
    """Preserve the existing 72-row screen used by panel 4.9(a); do not omit it."""
    path = require_data(path)
    if expected_sha is not None and digest(path) != expected_sha:
        raise ValueError('Primary screen does not match the retained publication screen SHA256')
    with path.open(encoding='utf-8-sig', newline='') as stream:
        rows = list(csv.DictReader(stream))
    needed = {'status', 'response_class', 'peak_dynamic_number',
              'restart_target_shift_percent', 'ramp_s'}
    if len(rows) != 72 or not rows or not needed.issubset(rows[0]):
        raise ValueError(f'Expected the 72-row primary screening CSV; found {len(rows)} rows/columns {list(rows[0]) if rows else []}')
    bins = {}
    for row in rows:
        if row['status'] != 'completed' or row['response_class'] != 'clean_continuous':
            raise ValueError('Primary screen includes an incomplete/noncontinuous case')
        point = tuple(float(row[k]) for k in ('restart_target_shift_percent', 'ramp_s'))
        metric = float(row['peak_dynamic_number'])
        if not all(math.isfinite(x) for x in (*point, metric)) or metric < 0:
            raise ValueError('Nonfinite/negative primary screening metric')
        bins[point] = bins.get(point, 0) + 1
    expected = {(s, t) for s in (20., 50., 80.) for t in (.005, .02, .1, .25)}
    if not expected.issubset(bins):
        raise ValueError('Primary screen omits a travel/ramp combination used by the existing plot')
    return rows


def recover_course_mechanism_margins(row):
    """Recover ONLY omitted deadzone flyweight margins from saved force terms.

    The exporter wrote mechanism_contact_margins only inside `ins.contact is not
    None`. CSV union headers therefore leave blank flyweight-margin cells during
    deadzone segments, although the three full-law force contributions were
    saved earlier for those same states. Their signed sum is exactly the margin
    returned by FixedPivotFlyweightForce.compressive_contact_margin in 1.1.2.

    Literal NaN/Inf, missing components, and every engaged missing margin remain
    failures. This does not mark the flyweight inactive or exempt it from its
    unilateral check. The raw row is never modified.
    """
    recovered = dict(row)
    notes = []
    if row.get('engagement') != 'deadzone' or row.get('inspection_error'):
        return recovered, notes
    for key, value in row.items():
        if not (key.startswith('mechanism_margin.primary/') and
                key.endswith(':FixedPivotFlyweightForce') and value in ('', None)):
            continue
        try:
            parts = [float(row[k]) for k in PRIMARY_FORCE_COMPONENTS]
        except (KeyError, TypeError, ValueError):
            continue
        if not all(math.isfinite(v) for v in parts):
            continue
        recovered[key] = math.fsum(parts)
        notes.append({'key': key, 'value_N': recovered[key],
                      'method': 'signed_sum_of_retained_full_flyweight_force_components',
                      'component_keys': list(PRIMARY_FORCE_COMPONENTS)})
    return recovered, notes


def recovery_summary(rows):
    count = 0
    examples = []
    minimum = None
    for row in rows:
        _, recovered = recover_course_mechanism_margins(row)
        count += len(recovered)
        for entry in recovered:
            minimum = entry['value_N'] if minimum is None else min(minimum, entry['value_N'])
            if len(examples) < 20:
                examples.append({'time_s': float(row['time_s']), 'segment_id': row.get('segment_id'),
                                 'sample_location': row.get('sample_location'), **entry})
    return {'reconstructed_margin_count': count, 'minimum_reconstructed_margin_N': minimum,
            'examples': examples, 'missing_values_ignored': False,
            'raw_diagnostics_rewritten': False}


def moving_source_hashes(audit):
    return portable_hashes(audit['raw_sha256'])


def verify_saved_subtree(run_root, relative, *, required_prefix=None):
    """Verify original PASS/reused execution bytes without relabelling their source.

    Absolute Windows paths in the original report are mapped to this explicitly
    provided run root, so moving an evidence directory does not change identity.
    This is output integrity plus recorded execution status, not a new physics
    audit. Study-specific checks follow in independent steps.
    """
    run_root = Path(run_root).resolve()
    report_file = run_root / 'health_report.json'
    report = read_json(report_file)
    original = str(report['output']).replace('\\', '/').rstrip('/')
    relative = portable_key(relative).rstrip('/')
    prefix = original + '/' + relative + '/'
    expected = {}
    producers = []
    for step in report['steps']:
        hits = {name: value for name, value in step.get('output_sha256', {}).items()
                if name.replace('\\', '/').startswith(prefix)}
        if not hits:
            continue
        if step['status'] not in ('PASS', 'REUSED'):
            raise ValueError('Evidence producer did not pass: ' + step['id'])
        producers.append(step['id'])
        for name, value in hits.items():
            key = portable_key(name.replace('\\', '/')[len(original) + 1:])
            if key in expected and expected[key] != value:
                raise ValueError('Conflicting original output hash: ' + key)
            expected[key] = value
    if not expected:
        raise MissingEvidence('No accepted hash inventory for ' + relative + ' in ' + str(report_file))
    if required_prefix and not any(p.startswith(required_prefix) for p in producers):
        raise ValueError('Missing expected original producer for ' + relative)
    for key, value in expected.items():
        path = path_below(run_root, key)
        if not path.is_file():
            raise MissingEvidence('Missing original execution output: ' + str(path))
        if digest(path) != value:
            raise ValueError('Original execution output changed: ' + str(path))
    return {'verified_files': len(expected), 'producers': sorted(set(producers)),
            'relative_root': relative, 'source_run': str(run_root),
            'original_run_source_identity': report.get('source_identity'),
            'original_git_head': report.get('git_head'),
            'original_report_sha256': digest(report_file),
            'files': expected, 'scope': 'original byte identity/status; generating source not relabelled'}


def resolve_saved_suite(run_root):
    """Resolve the exact pointer, with a portable rebase of the saved run path."""
    run_root = Path(run_root).resolve()
    pointer = run_root / 'data/course/latest_final.txt'
    if not pointer.is_file():
        raise MissingEvidence('Missing original selected-course pointer: ' + str(pointer))
    text = pointer.read_text(encoding='utf-8-sig').strip().replace('\\', '/')
    report = read_json(run_root / 'health_report.json')
    old = report['output'].replace('\\', '/').rstrip('/')
    if text.startswith(old + '/'):
        target = path_below(run_root, text[len(old) + 1:])
    else:
        candidate = Path(text)
        target = candidate if candidate.is_absolute() else pointer.parent / candidate
        if not target.is_dir():
            # An archive copied from another platform may contain a literal
            # absolute path. Only reuse its exact selected folder name.
            target = pointer.parent / text.rstrip('/').rsplit('/', 1)[-1]
    if not (target / 'suite.json').is_file():
        raise MissingEvidence('Selected course suite is unavailable: ' + text)
    return target.resolve()


def prepare_course_bundle(suite, output, audit_file):
    """Compact, unresampled plotting inputs for the accepted 15-case course suite.

    This is input preparation, not a new course compositor. The original row
    order, duplicate event times, modes, negative speeds and rollout/rollback
    histories remain present. No 15-85% shift-curve eligibility filter is used.
    """
    import numpy as np
    suite, output, audit_file = Path(suite), Path(output), Path(audit_file)
    audit = read_json(audit_file)
    manifest = read_json(suite/'suite.json')
    if (audit.get('passed') is not True or set(audit['cases']) != set(manifest['expected_cases'])
            or audit.get('suite_sha256') != digest(suite/'suite.json')):
        raise ValueError('Course bundle requires the complete passing case/event-side audit')
    output.mkdir(parents=True, exist_ok=True)
    arrays, descriptions, sources = {}, {}, {}
    retain = ('resolved_case.json', 'model_identity.json', 'events.json', 'segments.csv',
              'mechanism_map.csv', 'ramp_profile.csv', 'shape_mechanism_map.csv', 'summary.json')
    for index, name in enumerate(manifest['expected_cases']):
        experiment, case_name = name.split('/')
        case = suite/experiment/'cases'/case_name
        path = case/'diagnostics.csv'
        audited = audit['cases'][name].get('input_sha256', {})
        for filename in ('diagnostics.csv', 'events.json', 'summary.json', 'resolved_case.json'):
            if digest(case/filename) != audited.get(filename):
                raise ValueError('Course source changed since health inspection: '+name+'/'+filename)
        with path.open(encoding='utf-8-sig', newline='') as stream:
            rows = list(csv.DictReader(stream))
        if not rows:
            raise ValueError('Empty accepted course diagnostics: '+name)
        prefix = f'case_{index:02d}'
        schema = {}
        for column in rows[0]:
            raw = [r[column] for r in rows]
            try:
                values = np.array([float(v) if v not in ('', None) else np.nan for v in raw], dtype=float)
                schema[column] = 'float64; empty CSV cells are NaN'
                blank = np.array([v in ('', None) for v in raw], dtype=bool)
                if blank.any():
                    arrays[prefix+'__missing__'+column] = blank
            except (ValueError, TypeError):
                values = np.asarray(raw, dtype=str)
                schema[column] = 'unicode'
            arrays[prefix+'__'+column] = values
        time = arrays[prefix+'__time_s']
        if not np.isfinite(time).all() or np.any(np.diff(time) < 0):
            raise ValueError('Course plotting rows are not chronological: '+name)
        source_key = path.relative_to(suite).as_posix()
        sources[source_key] = digest(path)
        copy_to = output/'cases'/experiment/case_name
        copy_to.mkdir(parents=True, exist_ok=True)
        copied = {}
        for filename in retain:
            source = case/filename
            if not source.is_file():
                raise MissingEvidence('Required course figure input missing: '+str(source))
            shutil.copy2(source, copy_to/filename)
            sources[source.relative_to(suite).as_posix()] = digest(source)
            copied[filename] = (copy_to/filename).relative_to(output).as_posix()
        descriptions[name] = {'array_prefix': prefix, 'rows': len(rows), 'columns': schema,
                              'case_files': copied, 'diagnostics_sha256': digest(path),
                              'duplicate_time_pairs': int(np.count_nonzero(np.diff(time)==0))}
    arrays['schema_json'] = np.array(__import__('json').dumps(descriptions, sort_keys=True))
    np.savez_compressed(output/'course_plot_inputs.npz', **arrays)
    shutil.copy2(suite/'suite.json', output/'suite.json')
    shutil.copy2(audit_file, output/'course_health_audit.json')
    files = {'course_plot_inputs.npz': digest(output/'course_plot_inputs.npz'),
             'suite.json': digest(output/'suite.json'),
             'course_health_audit.json': digest(output/'course_health_audit.json')}
    files.update({p.relative_to(output).as_posix(): digest(p) for p in sorted((output/'cases').rglob('*')) if p.is_file()})
    result = {'schema': 1, 'case_count': len(descriptions), 'cases': descriptions,
              'files': files, 'source_suite': str(suite.resolve()), 'source_sha256': sources,
              'health_audit_sha256': digest(audit_file),
              'row_order_and_event_sides_preserved': True, 'smoothing_or_resampling': False,
              'scope': 'Numeric input preparation. Exact paper figure compositing remains a separate export step.'}
    write_json(output/'course_bundle.json', result)
    return result
