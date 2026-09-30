"""Publication-bundle binding for the reduced-belt study (F02)."""
from __future__ import annotations
from pathlib import Path
from .common import digest, read_json, verify_hashes, write_json
from .guards import belt_run_findings
from .prep_support import portable_hashes

BUNDLE_FILES = ('belt_publication.npz', 'belt_events.json', 'belt_publication_audit.json',
                'belt_moving_state_samples.npz', 'belt_moving_state_audit.json', 'run_plan.json')


def seal_bundle(inputs: Path) -> None:
    # A separate manifest avoids trying to put the hash of a file inside itself.
    write_json(inputs / 'publication_manifest.json', {
        'schema': 1, 'definition': 'one prepared set of main, event and moving-state evidence',
        'files': {name: digest(inputs / name) for name in BUNDLE_FILES}})


def verify_bundle(inputs: Path) -> int:
    m = read_json(inputs / 'publication_manifest.json')
    if m.get('schema') != 1 or set(m.get('files', {})) != set(BUNDLE_FILES):
        raise ValueError('Incorrect/incomplete reduced-belt publication manifest')
    return verify_hashes(inputs, m['files'])


def check_publication(inputs: Path, raw: Path, runtime_source_check: Path):
    """Check both compact and available raw evidence, preserving coverage in output."""
    count = verify_bundle(inputs)
    a = read_json(inputs / 'belt_publication_audit.json')
    plan = read_json(inputs / 'run_plan.json')
    expected = {'{case}_{level}_{variant}'.format(**j) for j in plan}
    if len(expected) != len(plan) or set(a.get('runs', {})) != expected:
        raise ValueError('Publication audit does not enumerate the exact run plan')
    if digest(inputs / 'belt_publication.npz') != a['plot_inputs_sha256']:
        raise ValueError('Main belt bundle/audit mismatch')
    events = read_json(inputs / 'belt_events.json')
    if set(events) != expected:
        raise ValueError('Event ledgers do not enumerate the same publication runs')
    moving = read_json(inputs / 'belt_moving_state_audit.json')
    if digest(inputs / 'belt_moving_state_samples.npz') != moving['input_sha256']:
        raise ValueError('Moving-state bundle/audit mismatch')
    import json
    import numpy as np
    with np.load(inputs / 'belt_moving_state_samples.npz', allow_pickle=False) as z:
        provenance = json.loads(str(z['metadata']))
    if provenance != moving['provenance']:
        raise ValueError('Moving-state samples and audit have different provenance')
    normalized_raw = portable_hashes(a['raw_sha256'])
    for name, expected_hash in portable_hashes(provenance['raw_sha256']).items():
        if normalized_raw.get(name) != expected_hash:
            raise ValueError('Moving-state evidence belongs to another raw execution: ' + name)
    raw_verified = 0
    if raw.is_dir():
        raw_verified = verify_hashes(raw, normalized_raw)
    import cinder
    runtime = read_json(runtime_source_check)
    package = Path(cinder.__file__).resolve().parent
    actual_runtime = {name.removeprefix('cvtModel/src/cinder/'): h
                      for name, h in runtime['source_sha256'].items()}
    source_count = verify_hashes(package, actual_runtime)
    findings = [f for name, s in a['runs'].items() for f in belt_run_findings(name, s)]
    result = {'run_count': len(expected), 'bundle_files_verified': count,
              'raw_files_verified': raw_verified, 'frozen_source_files_verified': source_count,
              'local_loading_findings': findings,
              'raw_evidence_available': raw.is_dir(),
              'scope': 'retained sampled states and exact event sides; not an all-time proof'}
    if findings:
        raise ValueError('Reduced-belt health check failed: ' + repr(findings[:20]))
    return result


def bind_existing_bundle(inputs: Path):
    """Add the combined manifest only after verifying the pre-existing inner links.

    This migrates a copied legacy bundle, not an unverified assortment of files.
    The canonical raw preparer uses seal_bundle after rebuilding all components.
    """
    import hashlib
    import json
    import numpy as np
    audit=read_json(inputs/'belt_publication_audit.json')
    if digest(inputs/'belt_publication.npz')!=audit['plot_inputs_sha256']:
        raise ValueError('Legacy main input hash mismatch')
    moving=read_json(inputs/'belt_moving_state_audit.json')
    if digest(inputs/'belt_moving_state_samples.npz')!=moving['input_sha256']:
        raise ValueError('Legacy moving-state input hash mismatch')
    with np.load(inputs/'belt_moving_state_samples.npz',allow_pickle=False) as z:
        provenance=json.loads(str(z['metadata']))
    if provenance!=moving['provenance']:
        raise ValueError('Moving-state archive and audit provenance disagree')
    raw_hashes = portable_hashes(audit['raw_sha256'])
    for name,h in portable_hashes(provenance['raw_sha256']).items():
        if raw_hashes.get(name)!=h:
            raise ValueError('Moving-state evidence belongs to another raw campaign: '+name)
    events=read_json(inputs/'belt_events.json')
    if set(events)!=set(audit['runs']):
        raise ValueError('Main and event bundles have different run sets')
    for name,rows in events.items():
        encoded=(json.dumps(rows,indent=2,allow_nan=False)+'\n').encode()
        if hashlib.sha256(encoded).hexdigest()!=audit['runs'][name]['output_sha256']['events.json']:
            raise ValueError('Retained event ledger differs from the recorded raw execution: '+name)
    seal_bundle(inputs)
