"""Read-only Ballew accounting recheck; no integrations and no figure changes.

python results/cinder-v1.1.2/results_health/ballew_accounting_audit.py \
    --raw-dir PATH_TO_SUITE/data/ballew --output PATH_TO_NEW_REPORT.json

All five cases are attempted. Raw artifacts and original provenance are never
modified. Output identifies the audited bytes and the current reporting code.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import math
from pathlib import Path
import sys

RELEASE=Path(__file__).resolve().parents[1]
if str(RELEASE) not in sys.path:sys.path.insert(0,str(RELEASE))
import numpy as np
from results_health.slip import (publication_slip_channels,
                                verify_publication_slip_channels)

CASES=('force-replay','closed-loop','convergence/nominal_0p50ms',
       'convergence/nominal_0p25ms','convergence/tight_0p50ms')


def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda:f.read(1024*1024),b''):h.update(block)
    return h.hexdigest()


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def safe_member(root,name):
    # Accept the original Windows manifest spelling without making an arbitrary
    # absolute path or a directory traversal into an evidence source.
    p=(root/str(name).replace('\\','/')).resolve()
    if not p.is_relative_to(root.resolve()):raise ValueError('Manifest escapes its root: '+str(name))
    return p


def check_one(directory):
    record=read(directory/'execution_provenance.json')
    if record.get('cinder_version')!='1.1.2' or record.get('cinder_tag_commit')!='7637a38b4fb9ec21dfb953c1c80a27ec5f389654':
        raise ValueError('Unexpected original mechanics identity')
    for field,root in (('output_sha256',directory),('input_sha256',directory/'execution_inputs')):
        entries=record.get(field,{})
        if not entries:raise ValueError('Missing original execution hashes: '+field)
        for name,digest in entries.items():
            if sha(safe_member(root,name))!=digest:raise ValueError('Original execution hash mismatch: '+name)
    metrics=read(directory/'metrics.json');mass=read(directory/'resolved_belt_mass.json')
    if metrics.get('completed') is not True or not math.isclose(float(metrics['final_time_s']),5.,rel_tol=0.,abs_tol=1e-10):
        raise ValueError('Not a completed five-second execution')
    if not math.isclose(float(mass['mass_kg']),1.,rel_tol=0.,abs_tol=2e-12):raise ValueError('Not the corrected 1 kg assembly')
    manifest=read(directory/'trace_manifest.json')
    modes={s['id']:s['mode'] for s in manifest['segments']}
    with np.load(directory/'segmented_report.npz',allow_pickle=False) as data:
        generated,audit=publication_slip_channels(data,modes,enforce_health=False)
        stored_ok=None
        if audit['health']['passed']:
            # This also detects a manually altered exported loss/mask array.
            verify_publication_slip_channels(data,modes)
            stored_ok=True
    return {'status':'PASS' if audit['health']['passed'] else 'FAIL',
            'original_execution_hashes_verified':True,'stored_derived_arrays_verified':stored_ok,
            'original_manifest_sha256':sha(directory/'execution_provenance.json'),
            'contact_data_sha256':sha(directory/'segmented_report.npz'),
            'resolved_mass':mass,'metrics':metrics.get('metrics',{}),'accounting':audit}


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__,formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--raw-dir',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args(argv);root=a.raw_dir.resolve();target=a.output.resolve()
    if target.is_relative_to(root):p.error('--output must be outside the raw evidence directory')
    result={'scope':'Read-only accounting audit, not a new simulation or automatic approval of conclusions',
            'raw_directory':str(root),'reporting_source_sha256':sha(Path(__file__).with_name('slip.py')),
            'cases':{}}
    for name in CASES:
        try:r=check_one(root/name)
        except FileNotFoundError as exc:r={'status':'MISSING','reason':str(exc)}
        except Exception as exc:r={'status':'FAIL','reason':f'{type(exc).__name__}: {exc}'}
        result['cases'][name]=r;print(name+': '+r['status'])
    result['all_five_passed']=all(r['status']=='PASS' for r in result['cases'].values())
    target.parent.mkdir(parents=True,exist_ok=True)
    temporary=target.with_name(target.name+'.tmp')
    temporary.write_text(json.dumps(result,indent=2,allow_nan=False)+'\n',encoding='utf-8')
    temporary.replace(target)
    print('Accounting review:',target)
    return 0 if result['all_five_passed'] else 2


if __name__=='__main__':raise SystemExit(main())
