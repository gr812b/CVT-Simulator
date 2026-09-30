"""Retain numerical evidence before evaluating derived sliding-loss health."""

from collections import Counter
import hashlib
import json
from pathlib import Path
import shutil
import sys

import cinder
import numpy as np
from cinder.model.cvt.contact.tolerances import ContactKinematicTolerances

from .simulation import compact_mode
from results_health.common import simulation_fingerprint
from results_health.slip import (DEFINITION, HEALTH_POLICY,
                                 RELATIVE_SPEED_TOLERANCE_M_PER_S,
                                 publication_slip_channels)


def _write_json(path, value):
    path.write_text(json.dumps(value, indent=2, allow_nan=False) + '\n', encoding='utf-8')


def retain_result(setup, result, output: Path) -> None:
    """Save an integration even when its publication diagnostic needs review.

    All native/report event sides and the original dense comparison grid are
    retained exactly as before. The model and numerical settings are unchanged.
    A derived-accounting failure is recorded, and remains a publication failure;
    it no longer destroys an otherwise completed numerical execution record.
    """
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    raw = result.trace
    time = np.concatenate([s.time for s in raw.segments])
    state = np.concatenate([s.state for s in raw.segments], axis=1)
    ids = np.concatenate([np.full(s.time.size, i, dtype=int)
                          for i, s in enumerate(raw.segments)])
    np.savez_compressed(output / 'native_trace.npz', time_s=time,
                        full_state=state, segment_id=ids)

    if len(result.segments) != len(raw.segments):
        raise ValueError('Raw and reported segment counts disagree')
    channels = tuple(result.segments[0].signals)
    reported = {k: np.concatenate([s.signals[k].values for s in result.segments])
                for k in channels}
    reported['time_s'] = np.concatenate([s.time for s in result.segments])
    reported['segment_id'] = np.concatenate([
        np.full(s.time.size, i, dtype=int) for i, s in enumerate(result.segments)])
    # Persist raw contact channels BEFORE any derived-accounting gate.
    np.savez_compressed(output / 'segmented_report.npz', **reported)

    events = []
    for event in raw.transitions:
        events.append({'time_s': event.time,
                       'reason': event.transition.reason,
                       'fired_events': event.fired_event_names,
                       'previous_mode': compact_mode(event.previous_mode),
                       'next_mode': compact_mode(event.transition.next_mode),
                       'post_state': event.post_transition_state.tolist()})
    durations = Counter()
    for segment in raw.segments:
        durations[compact_mode(segment.mode)] += segment.end_time - segment.start_time
    steps = np.concatenate([np.diff(s.time) for s in raw.segments])
    record = {'segments': [{'id': i, 'start_s': s.start_time,
                            'end_s': s.end_time, 'mode': compact_mode(s.mode),
                            'native_samples': s.time.size}
                           for i, s in enumerate(raw.segments)],
              'events': events, 'mode_duration_s': dict(durations),
              'transition_reasons': dict(Counter(e['reason'] for e in events)),
              'accepted_steps': int(steps.size),
              'native_step_quantiles_s': np.quantile(steps, [0, .5, .95, 1]).tolist(),
              'comparison_grid_step_s': 0.0002, 'event_sides_preserved': True}
    _write_json(output / 'trace_manifest.json', record)
    belt = setup.assembly.inertias.belt
    _write_json(output / 'resolved_belt_mass.json', {
        'mass_kg': belt.mass, 'linear_density_kg_per_m': belt.linear_density,
        'density_kg_per_m3': belt.density,
        'center_of_mass_path_length_m': belt.center_of_mass_path_length,
        'outer_path_length_m': belt.outer_length})

    grid = np.arange(0.0, raw.final_time + 1e-12, 0.0002)
    values = np.full((state.shape[0], grid.size), np.nan)
    for segment in raw.segments:
        selected = np.flatnonzero((grid >= segment.start_time) &
                                  (grid <= segment.end_time))
        if selected.size:
            values[:, selected] = segment.dense_state_at(grid[selected])
    if not np.all(np.isfinite(values)):
        raise RuntimeError('Uncovered common-grid state in retained Ballew trace')
    cvt = setup.system.layout.view_matrix(values, 'cvt')
    np.savez_compressed(output / 'comparison_grid.npz', time_s=grid,
                        full_state=values, cvt_state=cvt)

    modes = {i: compact_mode(s.mode) for i, s in enumerate(raw.segments)}
    try:
        # This benchmark uses the default CINDER contact kinematic tolerance.
        # Verify the expected installed-release value rather than silently
        # using a different numerical contact policy for its reporting audit.
        contact_speed_tolerance = ContactKinematicTolerances().relative_speed_tolerance
        if contact_speed_tolerance != RELATIVE_SPEED_TOLERANCE_M_PER_S:
            raise ValueError('Installed contact speed tolerance differs from the pinned reporting policy')
        corrected, accounting = publication_slip_channels(
            reported, modes, relative_speed_tolerance=contact_speed_tolerance,
            enforce_health=False)
        reported.update(corrected)
        np.savez_compressed(output / 'segmented_report.npz', **reported)
    except ValueError as exc:
        # This is diagnostic retention, not acceptance. trace_check and
        # ballew-health explicitly reject missing/failed accounting.
        accounting = {'definition': DEFINITION, 'health_policy': HEALTH_POLICY,
                      'health': {'passed': False, 'findings': [str(exc)]},
                      'structural_accounting_error': str(exc)}
    _write_json(output / 'slip_accounting.json', accounting)
    if not accounting['health']['passed']:
        print('Ballew numerical trace retained; sliding-accounting health FAILED. '
              'See ' + str(output / 'slip_accounting.json'), file=sys.stderr)


def record_execution(study: Path, output: Path, solver: dict) -> None:
    """Freeze study AND shared accounting sources with the retained outputs."""
    sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
    paths = [p for p in study.rglob('*.py')
             if not {'artifacts', 'work', '__pycache__'}.intersection(p.parts)]
    paths += [study / 'study.json', study / 'reference/manifest.json']
    paths += list((study / 'reference').glob('*.csv'))
    snapshots = output / 'execution_inputs'
    inputs = {}
    for path in sorted(set(paths)):
        name = path.relative_to(study)
        target = snapshots / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, target)
        inputs[name.as_posix()] = sha(path)
    # The shared C02 implementation is outside study/. Without this snapshot
    # the archive would not identify the actual accounting code that ran.
    shared = study.parents[1] / 'results_health'
    for name in ('__init__.py', 'common.py', 'slip.py'):
        source = shared / name
        relative = Path('_results_health') / name
        target = snapshots / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        inputs[relative.as_posix()] = sha(source)
    outputs = {p.name: sha(p) for p in sorted(output.iterdir())
               if p.is_file() and p.name != 'execution_provenance.json'}
    record = {'simulation_fingerprint': simulation_fingerprint(study),
              'cinder_version': cinder.__version__,
              'cinder_tag_commit': '7637a38b4fb9ec21dfb953c1c80a27ec5f389654',
              'cinder_module_path': str(Path(cinder.__file__).resolve()),
              'python_version': sys.version, 'solver': solver,
              'input_sha256': inputs, 'output_sha256': outputs}
    _write_json(output / 'execution_provenance.json', record)
