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
RELEASE_ROOT = STUDY_ROOT.parents[2]


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


def source_fingerprint() -> dict:
    # History and previously produced results do not become executable inputs.
    files = [STUDY_ROOT/n for n in ('run.py', 'verify_study.py')]
    for name in ('infrastructure', 'experiments', 'analysis', 'tests', 'scans'):
        for parent, children, names in os.walk(STUDY_ROOT/name, followlinks=False):
            children[:] = sorted(c for c in children if c not in
                                 ('artifacts', '__pycache__', '.pytest_cache')
                                 and not (Path(parent)/c).is_symlink())
            files.extend(Path(parent)/n for n in names if n.endswith('.py'))
    return {p.relative_to(STUDY_ROOT).as_posix(): sha_file(p)
            for p in sorted(files) if p.is_file() and not p.is_symlink()}


def finite(value: Any) -> bool:
    try: return math.isfinite(float(value))
    except (ValueError,TypeError): return False
