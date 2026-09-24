"""Fixed input selection, archive identity and safe completed-case reuse."""
from __future__ import annotations
from contextlib import contextmanager
import json
import os
from pathlib import Path
import shutil
import socket
from typing import Iterator

from .common import STUDY_ROOT, RELEASE_ROOT, load_json, write_json, digest, sha_file, utc_now, final_files

ERROR_STATUSES = {'setup_error','integration_error','wall_timeout','worker_error'}
OBSERVED_STATUSES = {'finished','rollback','progress_limited','time_limit','model_domain_stop'}
ESSENTIAL_CASE_FILES = (
    'status.json','summary.json','resolved_case.json','diagnostics.csv',
    'events.json','events.csv','segments.csv','sector_metrics.csv',
    'interesting_windows.csv','event_windows.csv',
)


def canonical_file_hash(path: Path) -> str:
    """Ignore JSON formatting and line endings, but no numerical/data changes."""
    return digest(load_json(path))


def shared_hashes(release: Path = RELEASE_ROOT) -> dict[str,str]:
    folder = release/'defaults/reference_model'
    names = ('__init__.py','reference_case.py','slotted_helix.py','policy.json')
    result = {}
    import hashlib
    for name in names:
        p = folder/name
        if not p.is_file():
            raise FileNotFoundError(f'Missing shared Results helper: {p}')
        result[name] = (canonical_file_hash(p) if p.suffix=='.json' else
                        hashlib.sha256(p.read_text(encoding='utf-8-sig').encode()).hexdigest())
    return result


def validate_selection(root: Path = STUDY_ROOT, release: Path = RELEASE_ROOT) -> dict:
    lock = load_json(root/'inputs/selection.lock.json')
    for relative, expected in lock['inputs'].items():
        if canonical_file_hash(root/relative) != expected:
            raise ValueError(f'The selected input changed: {relative}. Create an explicit new study revision rather than mixing it with this final selection.')
    baseline = release/'defaults/baja/simulation_case.json'
    if not baseline.is_file():
        raise FileNotFoundError(f'Extract studies/course-tuning into results/cinder-v1.1.2. Missing: {baseline}')
    if canonical_file_hash(baseline) != lock['baseline_canonical_sha256']:
        raise ValueError('Shared Baja baseline differs from the accepted final run. Do not silently change the final case definitions.')
    actual = shared_hashes(release)
    if actual != lock['shared_helpers_normalized_sha256']:
        bad = [n for n,v in actual.items() if v != lock['shared_helpers_normalized_sha256'].get(n)]
        raise ValueError('Shared Results helpers differ from the selected reference: '+', '.join(bad))
    return lock


def snapshot_sources(destination: Path, root: Path = STUDY_ROOT, release: Path = RELEASE_ROOT) -> None:
    """Save enough source and inputs to identify/reproduce this exact campaign."""
    for p in final_files(root, include_documentation=True):
        q=destination/'study'/p.relative_to(root)
        q.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(p,q)
    for relative in ('defaults/baja/simulation_case.json', *('defaults/reference_model/'+n for n in shared_hashes(release))):
        q=destination/'shared_results'/relative
        q.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(release/relative,q)


def seal_case(folder: Path, fingerprint: str) -> None:
    paths = [folder/n for n in ESSENTIAL_CASE_FILES if (folder/n).is_file()]
    write_json(folder/'case_integrity.json', {'fingerprint':fingerprint,
        'files':{p.name:sha_file(p) for p in paths}, 'created_utc':utc_now()})


def reusable_case(folder: Path, fingerprint: str) -> bool:
    """Never reuse a half-written or subsequently damaged case as finished output."""
    try:
        status=load_json(folder/'status.json');proof=load_json(folder/'case_integrity.json')
        if not status.get('complete_output') or status.get('fingerprint')!=fingerprint or proof['fingerprint']!=fingerprint:
            return False
        if not all((folder/name).is_file() for name in ESSENTIAL_CASE_FILES):
            return False
        return all(sha_file(folder/name)==proof['files'].get(name) for name in ESSENTIAL_CASE_FILES)
    except (OSError,ValueError,KeyError,TypeError):
        return False


def archive_attempt(folder: Path, output: Path) -> None:
    """Keep incomplete/error outputs rather than silently deleting evidence."""
    if not folder.exists():return
    from uuid import uuid4
    relative=folder.relative_to(output)
    dest=output/'previous_attempts'/relative/(utc_now().replace(':','-')+'_'+uuid4().hex[:6])
    dest.parent.mkdir(parents=True,exist_ok=True);shutil.move(str(folder),str(dest))


@contextmanager
def output_lock(output: Path) -> Iterator[None]:
    path=output/'RUNNING.lock'
    try:
        handle=os.open(path,os.O_CREAT|os.O_EXCL|os.O_WRONLY)
    except FileExistsError as exc:
        raise RuntimeError(f'{output} is already locked. An interrupted run may leave RUNNING.lock; remove it only after confirming no process is still using this output.') from exc
    try:
        with os.fdopen(handle,'w',encoding='utf-8') as stream:
            json.dump({'pid':os.getpid(),'host':socket.gethostname(),'started_utc':utc_now()},stream)
        yield
    finally:
        path.unlink(missing_ok=True)
