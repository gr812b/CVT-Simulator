#!/usr/bin/env python3
"""Validate the fixed selection, shared reference, tests, and all twelve selected model assemblies."""
from __future__ import annotations
import argparse
from pathlib import Path
import sys
import unittest
ROOT=Path(__file__).resolve().parent
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
from infrastructure.common import load_json,RELEASE_ROOT
from infrastructure.selection import validate_selection
from infrastructure.course import Course
from infrastructure.tunes import resolve_tune

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--allow-environment-mismatch',action='store_true')
    a=p.parse_args();validate_selection()
    from infrastructure.model import check_environment,build_system
    env=check_environment()
    if not env['frozen_environment_match'] and not a.allow_environment_mismatch:
        raise RuntimeError('Use the frozen Results environment, or explicitly mark diagnostic verification with --allow-environment-mismatch.')
    result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.discover(str(ROOT/'tests')))
    if not result.wasSuccessful():return 1
    spec=load_json(ROOT/'study.json');base=load_json(RELEASE_ROOT/'defaults/baja/simulation_case.json')
    course=Course(load_json(ROOT/'inputs/course.json'));identities=[]
    for tune in load_json(ROOT/'inputs/competitors.json')['competitors']:
        doc,_=resolve_tune(base,tune);system,y,mode,identity=build_system(doc,course,spec['execution'])
        identities.append(identity)
        print(tune['id']+': full dynamic flyweights, bilateral dynamic helix, unchanged shaft boundaries')
    if any(i!=identities[0] for i in identities):raise AssertionError('Competitors changed boundary/model identity')
    print('Selection, unit tests and all twelve selected model assemblies verified. No trajectory was integrated.')
    return 0
if __name__=='__main__':
    try:raise SystemExit(main())
    except (ValueError,RuntimeError,FileNotFoundError) as exc:raise SystemExit(str(exc))
