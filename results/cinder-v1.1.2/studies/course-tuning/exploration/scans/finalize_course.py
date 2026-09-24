"""Prepare or run the focused unified-course confirmation (no parameter sweep)."""
from __future__ import annotations

import argparse
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from infrastructure.common import load_json, write_json, digest, utc_now
from infrastructure.course import Course


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument('--course', type=Path, default=ROOT/'inputs/course_unified_candidate.json')
    parser.add_argument('--competitors', type=Path, default=ROOT/'inputs/competitors_final_check.json')
    parser.add_argument('--cars', nargs='+', help='Subset of entrant IDs; default all ten')
    parser.add_argument('--preset', choices=['smoke','screen','research','tight'], default='tight')
    parser.add_argument('--jobs', type=int, default=4)
    parser.add_argument('--max-time', type=float, default=None, help='Common simulated-time limit, normally the preset default')
    parser.add_argument('--execute', action='store_true', help='Without this flag only resolve the campaign; do not simulate')
    parser.add_argument('--resume', action='store_true')
    parser.add_argument('--retry-errors', action='store_true')
    parser.add_argument('--no-plots', action='store_true')
    args = parser.parse_args()
    if args.jobs < 1:
        parser.error('--jobs must be positive')
    if args.retry_errors and not args.resume:
        parser.error('--retry-errors requires --resume')
    fleet = load_json(args.competitors)['competitors']
    ids = [c['id'] for c in fleet]
    chosen = args.cars or ids
    if set(chosen)-set(ids):
        parser.error('Unknown car IDs: '+', '.join(sorted(set(chosen)-set(ids))))
    course_config=load_json(args.course);course=Course(course_config)
    invocation={'course_file':str(args.course.resolve()),'course':course_config,
                'fleet_file':str(args.competitors.resolve()),'cars':chosen,'preset':args.preset,
                'maximum_time_override_s':args.max_time}
    work=ROOT/'artifacts/unified_checks'/digest(invocation)[:12]
    work.mkdir(parents=True,exist_ok=True)
    record=work/'campaign_path.txt'
    command=[sys.executable,str(ROOT/'run.py'),'--course',str(args.course.resolve()),
             '--competitors',str(args.competitors.resolve()),'--preset',args.preset,
             '--cars',*chosen,'--focus',*chosen,'--jobs',str(args.jobs),
             '--record-campaign',str(record)]
    if args.max_time is not None:command+=['--max-time',str(args.max_time)]
    if args.resume:command+=['--resume']
    if args.retry_errors:command+=['--retry-errors']
    if args.no_plots:command+=['--no-plots']
    if not args.execute:command+=['--prepare-only']
    write_json(work/'request.json',{'recorded_utc':utc_now(),**invocation,'command':command,
                                  'execution_requested':args.execute})
    print(f'{len(chosen)} entrants on one {course.finish_m:g} m course.',flush=True)
    print('Full throttle, dynamic flyweights and bilateral dynamic helix for every entrant.',flush=True)
    print('Independent full histories; no sector resets or settled-state forcing.',flush=True)
    completed=subprocess.run(command,cwd=ROOT.parents[2])
    if not record.exists():return completed.returncode or 1
    campaign=Path(record.read_text(encoding='utf-8').strip())
    if args.execute:
        from analysis.final_course_checks import build_report
        result=build_report(campaign,plots=not args.no_plots)
        print(f'Full report: {campaign/"index.html"}',flush=True)
        print(f'Final checks: {result}',flush=True)
    else:
        print('Preparation only. Add --execute --resume to run these cars.',flush=True)
        print(f'Resolved campaign: {campaign}',flush=True)
    return completed.returncode


if __name__=='__main__':
    raise SystemExit(main())
