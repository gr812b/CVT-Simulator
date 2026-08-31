"""Static integrity checks for the migrated Ballew results study."""
from __future__ import annotations

import hashlib
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent
EXPECTED_PDF_SHA = "cafead74895bbfaf092fe0354f0572064f44c6b4ff10c422877c5ae587f8df44"


def sha256(path: Path) -> str:
    h=hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda:f.read(1024*1024),b''):
            h.update(chunk)
    return h.hexdigest()


def main() -> int:
    required = [
        ROOT/'README.md', ROOT/'study.json', ROOT/'run.py', ROOT/'run_convergence.py',
        ROOT/'migrate_legacy.py', ROOT/'benchmark/constants.py', ROOT/'benchmark/case.py',
        ROOT/'benchmark/controller.py', ROOT/'provenance/RECONSTRUCTION.md',
        ROOT/'provenance/CINDER_FIXES.md', ROOT/'provenance/CURRENT_STUDY_SUMMARY.md',
        ROOT/'artifacts/historical-v1.0.0/headline/historical_metrics.json',
        ROOT/'reference/source/Ballew_2015_thesis.pdf',
    ]
    missing=[str(p.relative_to(ROOT)) for p in required if not p.exists()]
    if missing:
        print('Missing required study files: '+', '.join(missing),file=sys.stderr); return 1
    actual=sha256(ROOT/'reference/source/Ballew_2015_thesis.pdf')
    if actual != EXPECTED_PDF_SHA:
        print(f'Ballew thesis SHA mismatch: {actual}',file=sys.stderr); return 1
    forbidden=[]
    for path in [ROOT/'run.py',ROOT/'run_convergence.py',*sorted((ROOT/'benchmark').glob('*.py'))]:
        text=path.read_text(encoding='utf-8')
        for needle in ('sys.path.insert', 'cvtModel/src'):
            if needle in text:
                forbidden.append(f'{path.relative_to(ROOT)} contains {needle!r}')
    if forbidden:
        print('\n'.join(forbidden),file=sys.stderr); return 1
    print('Static study verification passed.')
    manifest=ROOT/'provenance/migration_manifest.json'
    if manifest.exists():
        print('Historical migration manifest present; run migrate_legacy.py --verify for byte checks.')
    else:
        print('Historical heavy assets not hydrated yet; migrate_legacy.py will materialize them from cinder-v1.0.0.')
    return 0

if __name__=='__main__':
    raise SystemExit(main())
