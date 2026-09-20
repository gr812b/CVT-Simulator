"""Small IO and provenance utilities; no model mechanics."""
from __future__ import annotations
import csv
from datetime import datetime, timezone
import hashlib
import importlib.metadata
import json
import math
import os
from pathlib import Path
import platform
import sys
from typing import Any

STUDY_ROOT = Path(__file__).resolve().parents[1]
RELEASE_ROOT = STUDY_ROOT.parents[1]


def load_json(path: str | Path) -> Any:
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(k): json_safe(v) for k, v in value.items()}
    if isinstance(value, (tuple, list)):
        return [json_safe(v) for v in value]
    if isinstance(value, Path): return str(value)
    if hasattr(value, 'item'):
        try: return json_safe(value.item())
        except (ValueError, TypeError): pass
    if hasattr(value, 'tolist'): return json_safe(value.tolist())
    if isinstance(value, float) and not math.isfinite(value): return None
    if isinstance(value, (str, int, float, bool)) or value is None: return value
    if hasattr(value, 'value'): return json_safe(value.value)
    return str(value)


def write_json(path: str | Path, payload: Any) -> None:
    path=Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    tmp=path.with_suffix(path.suffix+'.tmp')
    tmp.write_text(json.dumps(json_safe(payload), indent=2, allow_nan=False)+'\n',encoding='utf-8')
    os.replace(tmp,path)


def write_csv(path: str | Path, rows: list[dict], columns: list[str] | None=None) -> None:
    path=Path(path); path.parent.mkdir(parents=True,exist_ok=True)
    if columns is None:
        columns=list(dict.fromkeys(k for row in rows for k in row))
    with path.open('w',newline='',encoding='utf-8') as f:
        writer=csv.DictWriter(f,fieldnames=columns,extrasaction='ignore')
        writer.writeheader()
        for row in rows:
            writer.writerow({k: json.dumps(json_safe(v),separators=(',',':')) if isinstance(v,(dict,list,tuple)) else json_safe(v) for k,v in row.items()})


def read_csv(path: str | Path) -> list[dict]:
    with Path(path).open(newline='',encoding='utf-8-sig') as f:
        rows=list(csv.DictReader(f))
    for row in rows:
        for k,v in row.items():
            if v in ('True','False'): row[k]=(v=='True')
            elif v=='': row[k]=None
            else:
                try: row[k]=float(v)
                except (ValueError,TypeError): pass
    return rows


def sha_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(json_safe(value),sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


def environment() -> dict:
    out={'python':sys.version,'platform':platform.platform(),'machine':platform.machine(),'processor':platform.processor(),'cpu_count':os.cpu_count()}
    for package in ('cinder-cvt','numpy','scipy','matplotlib'):
        try: out[package]=importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError: out[package]=None
    return out


def final_files(root: Path = STUDY_ROOT, *, include_documentation: bool = False):
    """Only the final execution tree participates in identity or run snapshots.

    Never descend into exploration, artifacts, layout-history archives or tools.
    Editing an exploratory script cannot invalidate the final run cache.
    """
    top_names = ('run.py', 'verify_study.py')
    directories = ('infrastructure', 'experiments', 'analysis', 'tests')
    if include_documentation:
        top_names += ('study.json', 'README.md', 'FORMULATION_LINKAGE.md', '.gitignore')
        directories += ('inputs',)
    files = [root/name for name in top_names if (root/name).is_file()]
    for name in directories:
        directory = root/name
        for parent, children, names in os.walk(directory, followlinks=False):
            children[:] = sorted(c for c in children if c not in
                                 ('__pycache__', '.pytest_cache', 'artifacts')
                                 and not (Path(parent)/c).is_symlink())
            for filename in names:
                p = Path(parent)/filename
                if p.is_symlink():
                    continue
                if p.suffix == '.py' or (include_documentation and p.suffix in ('.json', '.md')):
                    files.append(p)
    if include_documentation:
        # Top-level provenance documents only; previous installations/logs live below.
        files += [p for p in (root/'provenance').glob('*')
                  if p.is_file() and not p.is_symlink() and p.suffix in ('.md', '.json')]
    return sorted(files)


def source_fingerprint(root: Path = STUDY_ROOT) -> dict:
    return {p.relative_to(root).as_posix(): sha_file(p)
            for p in final_files(root)}


def finite(value: Any) -> bool:
    try: return math.isfinite(float(value))
    except (ValueError,TypeError): return False
