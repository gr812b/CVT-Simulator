"""Small, explicit utilities shared by the Results checks (standard library only)."""
from __future__ import annotations

import hashlib
import json
import math
import os
from pathlib import Path
from typing import Any, Iterable


class MissingEvidence(RuntimeError):
    """Required evidence is absent; this is not a passing check."""


def digest(path: Path) -> str:
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def read_json(path: Path) -> Any:
    if not Path(path).is_file():
        raise MissingEvidence(f'Missing required file: {path}')
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def write_json(path: Path, value: Any) -> None:
    """Atomic report update. Nonfinite numbers must be handled explicitly upstream."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + '.tmp')
    tmp.write_text(json.dumps(value, indent=2, allow_nan=False) + '\n', encoding='utf-8')
    os.replace(tmp, path)


def finite(value: Any) -> bool:
    try:
        return not isinstance(value, bool) and math.isfinite(float(value))
    except (TypeError, ValueError, OverflowError):
        return False


def strict_bool(value: Any) -> bool:
    if value is True or value == 'True':
        return True
    if value is False or value == 'False':
        return False
    raise ValueError(f'Expected an explicit boolean, found {value!r}')


def require_complete(completed: Any, final_time: Any, expected_end: float,
                     *, label: str = 'run', tolerance_s: float = 1e-9) -> None:
    if not strict_bool(completed) or not finite(final_time):
        raise ValueError(f'{label}: calculation did not complete (end={final_time!r})')
    if not math.isclose(float(final_time), float(expected_end), rel_tol=0,
                        abs_tol=tolerance_s * max(1., abs(expected_end))):
        raise ValueError(f'{label}: ended at {final_time}, expected {expected_end}')


def safe_relative(root: Path, name: str) -> Path:
    root = Path(root).resolve()
    path = (root / name.replace('\\', '/')).resolve()
    if not path.is_relative_to(root):
        raise ValueError(f'Path escapes evidence directory: {name}')
    return path


def verify_hashes(root: Path, expected: dict[str, str]) -> int:
    if not expected:
        raise ValueError(f'Empty integrity manifest: {root}')
    for name, value in expected.items():
        path = safe_relative(root, name)
        if not path.is_file():
            raise MissingEvidence(f'Missing hashed evidence: {path}')
        if digest(path) != value:
            raise ValueError(f'Evidence hash mismatch: {path}')
    return len(expected)


def source_hashes(root: Path, paths: Iterable[Path]) -> dict[str, str]:
    root = Path(root).resolve()
    return {p.resolve().relative_to(root).as_posix(): digest(p)
            for p in sorted(set(paths)) if p.is_file()}


def simulation_fingerprint(study: Path, *, include_runner: bool = True) -> str:
    """Identify generating source and executable inputs, not README/figure styling.

    A study runner may also contain legacy plotting functions; changes to such a
    mixed file conservatively invalidate that study's cache. Dedicated analysis
    and plotting modules are excluded. This does not replace output integrity.
    """
    study = Path(study).resolve()
    release = study.parents[1]
    paths = []
    for folder in ('infrastructure', 'experiments', 'inputs', 'reference'):
        base = study / folder
        paths.extend(p for p in base.rglob('*') if p.is_file()
                     and p.suffix in {'.py', '.json', '.csv'}
                     and not {'__pycache__', 'artifacts', 'work'} & set(p.parts))
    for folder in (release / 'defaults', release / 'results_health'):
        paths.extend(p for p in folder.rglob('*') if p.is_file()
                     and p.suffix in {'.py', '.json', '.csv'})
    paths.append(study / 'study.json')
    if include_runner:
        paths.append(study / 'run.py')
    # Compact publication seeds are executable inputs, unlike their derived audits.
    for name in ('primary_publication.json', 'secondary_initial_conditions.json',
                 'secondary_backshift_initial.json', 'run_plan.json'):
        paths.append(study / 'publication_inputs' / name)
    paths.extend((study / 'publication_inputs' / 'cases').rglob('*.json'))
    identity = source_hashes(release, paths)
    return hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()


def verify_current_ballew_execution(study: Path, directory: Path) -> None:
    """A baseline made with the old mass mapping must never enter new refinements."""
    p = read_json(directory / 'execution_provenance.json')
    if p.get('cinder_version') != '1.1.2':
        raise ValueError('Incorrect CINDER version in reused benchmark')
    current = simulation_fingerprint(study)
    if p.get('simulation_fingerprint') != current:
        raise ValueError('Benchmark cache belongs to a different generator/input set; '
                         'run a fresh nominal case in a new output directory')
    verify_hashes(directory, p['output_sha256'])
    m = read_json(directory / 'metrics.json')
    require_complete(m['completed'], m['final_time_s'], 5., label=str(directory))
