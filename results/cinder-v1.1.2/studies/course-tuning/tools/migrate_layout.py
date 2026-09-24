#!/usr/bin/env python3
"""Preview or apply the one-time move from two course folders to one study.

Uses only Python's standard library. Stop running studies before applying this.
No existing file is overwritten: source trees are archived, artifacts are moved
as whole trees, and every moved file is verified against its original SHA-256.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import html
import json
import os
from pathlib import Path
import sys
from typing import Any
from urllib.parse import quote
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
LEGACY = ('course-tuning-exploration', 'course-tuning-final')


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


def file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def inventory(folder: Path) -> dict[str, Any]:
    """Include every file and empty directory; reject links rather than follow them."""
    files, dirs = {}, []
    for parent, children, names in os.walk(folder, followlinks=False):
        children.sort()
        names.sort()
        directory = Path(parent)
        for name in children + names:
            if (directory/name).is_symlink():
                raise RuntimeError(f'Symlink found: {directory/name}. No migration performed; resolve or archive it explicitly first.')
        dirs.extend((directory/n).relative_to(folder).as_posix() for n in children)
        for name in names:
            path = directory/name
            if name in ('RUNNING.lock', 'MIGRATING.lock', 'plan.lock'):
                # Selection lock metadata is not a live lock.
                raise RuntimeError(f'Lock found: {path}. Stop its writer, and resolve stale locks before migrating.')
            if not path.is_file():
                raise RuntimeError(f'Unsupported filesystem entry: {path}')
            files[path.relative_to(folder).as_posix()] = {
                'bytes': path.stat().st_size, 'sha256': file_hash(path)}
    return {'directories': sorted(dirs), 'files': files}


def dump(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + '.tmp')
    temporary.write_text(json.dumps(payload, indent=2) + '\n', encoding='utf-8')
    os.replace(temporary, path)


def plan_migration(root: Path, tag: str | None = None) -> dict[str, Any]:
    root = root.resolve()
    config = root/'study.json'
    if not config.is_file() or json.loads(config.read_text(encoding='utf-8'))['study_slug'] != 'course-tuning':
        raise RuntimeError('Extract the consolidated studies/course-tuning folder first.')
    tag = tag or datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '_' + uuid4().hex[:8]
    if any(c not in '0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz_-' for c in tag):
        raise ValueError('Invalid migration tag.')
    entries = []
    for name in LEGACY:
        source = root.parent/name
        if source.is_symlink():
            raise RuntimeError(f'Refusing a symlinked legacy study: {source}')
        if not source.exists():
            continue
        if not source.is_dir():
            raise RuntimeError(f'Legacy path is not a directory: {source}')
        if name.endswith('-exploration'):
            archive = root/'exploration/history'/tag/name
            destination = root/'exploration/artifacts'
        else:
            archive = root/'provenance/layout_history'/tag/name
            destination = root/'artifacts'
        if archive.exists():
            raise FileExistsError(archive)
        # An existing destination is never merged or overwritten, even when empty.
        if destination.exists() or destination.is_symlink():
            if destination.is_symlink():
                raise RuntimeError(f'Refusing a symlinked destination: {destination}')
            destination = destination/('imported_' + name + '_' + tag)
        if destination.exists():
            raise FileExistsError(destination)
        artifact_source = source/'artifacts'
        if artifact_source.exists() and not artifact_source.is_dir():
            raise RuntimeError(f'Artifacts path is not a directory: {artifact_source}')
        entries.append({'name': name, 'source': str(source), 'archive': str(archive),
                        'artifact_destination': str(destination) if artifact_source.exists() else None})
    return {'tag': tag, 'root': str(root), 'created_utc': now(), 'entries': entries}


def relocated_path(entry: dict[str, Any], relative: str) -> Path:
    parts = Path(relative).parts
    if parts and parts[0] == 'artifacts' and entry['artifact_destination']:
        return Path(entry['artifact_destination']).joinpath(*parts[1:])
    return Path(entry['archive'])/relative


def _rename(source: Path, destination: Path) -> None:
    if destination.exists() or destination.is_symlink():
        raise FileExistsError(f'Refusing to overwrite {destination}')
    destination.parent.mkdir(parents=True, exist_ok=True)
    source.rename(destination)


def apply_migration(plan: dict[str, Any]) -> dict[str, Any]:
    """Apply a preflighted plan. A caught failure reverses completed renames."""
    root = Path(plan['root'])
    if not plan['entries']:
        return {**plan, 'status': 'nothing_to_move', 'verified_file_count': 0}
    lock_path = root/'MIGRATING.lock'
    try:
        handle = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError as exc:
        raise RuntimeError(f'{lock_path} exists. Check the previous migration before removing it.') from exc
    os.write(handle, f'pid={os.getpid()} started={now()}\n'.encode())
    os.close(handle)
    log_path = root/'provenance/migrations'/(plan['tag']+'.json')
    log = {**plan, 'status': 'preflight', 'completed_moves': []}
    moves: list[tuple[Path, Path]] = []
    try:
        # No source move occurs before all trees and destination paths are checked.
        for e in plan['entries']:
            if Path(e['archive']).exists():
                raise FileExistsError(e['archive'])
            dest = e['artifact_destination']
            if dest and Path(dest).exists():
                raise FileExistsError(dest)
            print(f"Hashing {e['name']} (including all existing artifacts)...", flush=True)
            e['original_inventory'] = inventory(Path(e['source']))
        log['status'] = 'moving'
        dump(log_path, log)
        for e in plan['entries']:
            source, archive = Path(e['source']), Path(e['archive'])
            _rename(source, archive)
            moves.append((source, archive))
            log['completed_moves'] = [[str(a), str(b)] for a, b in moves]
            dump(log_path, log)
            if e['artifact_destination']:
                old = archive/'artifacts'; new = Path(e['artifact_destination'])
                _rename(old, new)
                moves.append((old, new))
                log['completed_moves'] = [[str(a), str(b)] for a, b in moves]
                dump(log_path, log)
        total = 0
        for e in plan['entries']:
            original = e['original_inventory']
            for relative, expected in original['files'].items():
                target = relocated_path(e, relative)
                if not target.is_file() or target.stat().st_size != expected['bytes'] or file_hash(target) != expected['sha256']:
                    raise RuntimeError(f'Post-move integrity mismatch: {target}')
                total += 1
            for relative in original['directories']:
                if not relocated_path(e, relative).is_dir():
                    raise RuntimeError(f'Missing moved directory: {relative}')
        log.update(status='complete', completed_utc=now(), verified_file_count=total,
                   note='Original files and recorded provenance are unchanged. No run is relabelled or adopted into the new final cache.')
        dump(log_path, log)
    except BaseException as exc:
        failures = []
        for source, destination in reversed(moves):
            try:
                if destination.exists() and not source.exists():
                    _rename(destination, source)
                else:
                    failures.append(f'Cannot roll back {destination} -> {source}')
            except OSError as rollback_error:
                failures.append(str(rollback_error))
        log.update(status='rollback_incomplete' if failures else 'rolled_back', error=str(exc), rollback_errors=failures)
        try:
            dump(log_path, log)
        except OSError:
            pass
        raise
    finally:
        lock_path.unlink(missing_ok=True)
    return log


def report_links(artifacts: Path):
    """List campaign/summary entry points; don't descend into per-case/figure trees."""
    if not artifacts.exists():
        return []
    result = []
    for parent, children, files in os.walk(artifacts, followlinks=False):
        children[:] = sorted(n for n in children if n not in
                             ('cases', 'figures', 'provenance', 'previous_attempts', '__pycache__'))
        directory = Path(parent)
        if 'index.html' in files:
            result.append(directory/'index.html')
    return sorted(result)


def build_index(root: Path) -> Path:
    """A new navigation file, never a rewrite of an original campaign report."""
    def link(path: Path, label: str) -> str:
        href = quote(os.path.relpath(path, root).replace(os.sep, '/'), safe='/')
        return f'<li><a href="{href}">{html.escape(label)}</a></li>'
    sections = []
    for title, location in [('Final results', root/'artifacts'),
                             ('Exploratory results', root/'exploration/artifacts')]:
        links = [link(p, p.parent.relative_to(location).as_posix()) for p in report_links(location)]
        sections.append(f'<h2>{title}</h2><ul>{"".join(links)}</ul>' if links else f'<h2>{title}</h2><p>No reports yet.</p>')
    logs = sorted((root/'provenance/migrations').glob('*.json'))
    sections.append('<h2>Migration records</h2><ul>'+''.join(link(p,p.name) for p in logs)+'</ul>')
    text = '''<!doctype html><html><head><meta charset="utf-8"><title>Course tuning — migrated results</title>
<style>body{font:16px system-ui;max-width:1100px;margin:2rem auto;padding:0 1rem}li{margin:.4rem 0}</style></head><body>
<h1>Course tuning: existing results</h1><p>Exploration and final results remain separate. Historical reports and numerical files retain their original contents and provenance. Root run.py produces the selected final 12-case study only.</p>
'''+''.join(sections)+'</body></html>\n'
    output=root/'migration_report.html'
    output.write_text(text,encoding='utf-8')
    return output


def main(argv=None) -> int:
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply',action='store_true',help='Move existing folders after verifying their file hashes; default is preview only')
    parser.add_argument('--index-only',action='store_true',help='Rebuild navigation links without moving anything')
    args=parser.parse_args(argv)
    if args.index_only:
        print(build_index(ROOT)); return 0
    plan=plan_migration(ROOT)
    if not plan['entries']:
        print('No legacy course-study folders remain. The consolidated layout is ready.')
        if args.apply:
            print(build_index(ROOT))
        return 0
    print('Stop all course runners before applying this migration.\n')
    for e in plan['entries']:
        print(f"{e['source']}\n  source/history -> {e['archive']}")
        if e['artifact_destination']:
            print(f"  artifacts     -> {e['artifact_destination']}")
    if not args.apply:
        print('\nPreview only. Rerun with --apply to perform these moves. No files changed.')
        return 0
    log=apply_migration(plan)
    print(f"\nMoved and hash-verified {log['verified_file_count']} files; no files overwritten.")
    print(f'Navigation: {build_index(ROOT)}')
    print('Use studies/course-tuning/run.py for the selected final study.')
    return 0


if __name__=='__main__':
    try:
        raise SystemExit(main())
    except (ValueError,KeyError,OSError,RuntimeError) as exc:
        raise SystemExit(str(exc))
