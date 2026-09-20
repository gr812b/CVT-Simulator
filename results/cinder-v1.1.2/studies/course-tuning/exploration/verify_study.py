"""Verify source inputs, tune invariants and the installed release; optional decode audit."""
from __future__ import annotations
import argparse
from pathlib import Path
import sys
import unittest
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
from infrastructure.common import load_json
from infrastructure.model import check_environment,build_system
from infrastructure.tunes import resolve_tune
from infrastructure.course import Course


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--decode-all',action='store_true',help='Construct every CINDER assembly and check its dynamic laws; does not integrate')
    p.add_argument('--strict-environment',action='store_true',help='Also require the exact Results Python/NumPy/SciPy/Matplotlib versions')
    a=p.parse_args();env=check_environment();print('Environment:',env)
    if a.strict_environment and not env['frozen_environment_match']:raise RuntimeError('Frozen dependency versions do not match. Activate the release Results environment.')
    suite=unittest.defaultTestLoader.discover(str(HERE/'tests'),pattern='test_*.py')
    success=unittest.TextTestRunner(verbosity=2).run(suite).wasSuccessful()
    if not success:return 1
    if a.decode_all:
        spec=load_json(HERE/'exploration.json');base=load_json(HERE/spec['base_document']);course=Course(load_json(HERE/'inputs/course.json'))
        signatures=[]
        for tune in load_json(HERE/'inputs/competitors.json')['competitors']:
            document,_=resolve_tune(base,tune)
            _,_,_,identity=build_system(document,course,spec['execution'])
            signatures.append(identity)
            print(tune['id'],'dynamic/slotted/reference-boundary checks passed',flush=True)
        if any(s!=signatures[0] for s in signatures[1:]):raise AssertionError('Mechanism or boundary identity differs across entrants')
    return 0
if __name__=='__main__':raise SystemExit(main())
