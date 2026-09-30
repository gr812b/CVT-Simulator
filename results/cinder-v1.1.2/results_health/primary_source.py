"""An explicit alternative to the historical primary ZIP used by the helix story."""
from contextlib import contextmanager
import csv
import gzip
import hashlib
import io
from pathlib import Path
import json
import zipfile
from .common import digest, read_json, verify_hashes, require_complete
from . import MECHANICS_COMMIT

HISTORICAL_SHA='692742ece9ddff7b6f8b532ddb42121a8027b6a3689db63ad45da38f11b0e505'

class BytesSource:
    def __init__(self, entries):self.entries=entries
    def __enter__(self):return self
    def __exit__(self,*args):return False
    def read(self,name):return self.entries[name]


def primary_source(archive, raw_dir, study, primary_prefix, release_prefix):
    """Expose the same input vocabulary for historical or fresh full-model baselines.

    Fresh files are hashed here and named explicitly in the resulting story audit.
    Their source provenance must match the executable reference configuration.
    This does not rewrite the identity of a historical archive.
    """
    if archive is not None:
        if digest(archive)!=HISTORICAL_SHA:
            raise ValueError('Incorrect historical primary archive')
        return zipfile.ZipFile(archive),{'kind':'historical_zip','archive_sha256':HISTORICAL_SHA}
    raw_dir=Path(raw_dir);study=Path(study);release=study.parents[1]
    baseline=release/'defaults/baja/simulation_case.json'
    cfg=read_json(study/'publication_inputs/primary_publication.json')
    entries={release_prefix+'defaults/baja/simulation_case.json':baseline.read_bytes()}
    hashes={};provenance={}
    for level in ('nominal','tight'):
        name=f'baseline_{level}_full';root=raw_dir/name
        meta=read_json(root/'provenance.json')
        if (meta.get('kind'),meta.get('level'),meta.get('variant'),meta.get('cinder_version'),meta.get('release_commit')) != ('baseline',level,'full','1.1.2',MECHANICS_COMMIT):
            raise ValueError('Incorrect fresh primary baseline provenance: '+name)
        baseline_key='defaults/baja/simulation_case.json'
        normalized_sources={key.replace('\\','/'):value for key,value in meta['source_sha256'].items()}
        if normalized_sources.get(baseline_key)!=digest(baseline):
            raise ValueError('Fresh primary baseline was generated from a different reference configuration')
        raw=(root/'trajectory.csv.gz').read_bytes()
        with gzip.open(io.BytesIO(raw),'rt',newline='') as stream:
            rows=list(csv.DictReader(stream))
        if not rows or {r['variant'] for r in rows}!={'full'}:
            raise ValueError('Expected the full primary baseline, not a reduced trajectory')
        require_complete(True,float(rows[-1]['time_s']),cfg['baseline_duration_s'],label=name)
        if float(rows[0]['time_s'])!=0.:
            raise ValueError('Primary baseline is missing its initial state')
        key=name+'/trajectory.csv.gz';hashes[key]=hashlib.sha256(raw).hexdigest()
        entries[primary_prefix+'artifacts/primary-publication/'+key]=raw
        provenance[name]=digest(root/'provenance.json')
    entries[primary_prefix+'publication_inputs/primary_publication_audit.json']=json.dumps({'raw_sha256':hashes}).encode()
    return BytesSource(entries),{'kind':'fresh_full_baselines','raw_directory':str(raw_dir.resolve()),
        'raw_sha256':hashes,'provenance_sha256':provenance,'reference_sha256':digest(baseline)}
