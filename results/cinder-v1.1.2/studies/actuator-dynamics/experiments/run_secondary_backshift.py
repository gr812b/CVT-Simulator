"""Refine the selected E3 continuous-backshift window with frozen CINDER 1.1.2.

Exact archived restart, no conditioning rerun. Nominal settings retain E3's
integration tolerances and step cap; tighter settings resolve the selected
force peak. Both write 0.1 ms samples and native segment endpoints.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time

STUDY = Path(__file__).resolve().parents[1]
RELEASE = STUDY.parents[1]


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--level', choices=['nominal', 'tight'], required=True)
    p.add_argument('--torque', type=float, choices=[0., -120., -240., -480.], required=True)
    p.add_argument('--variant', choices=['full', 'qs'], default='full')
    p.add_argument('--output-dir', type=Path, default=STUDY/'artifacts/secondary-backshift')
    args = p.parse_args()
    subprocess.run([sys.executable, str(RELEASE/'verify_environment.py')], check=True)
    import cinder
    from run_secondary_publication import initial_state, stick_mode, write_rows, audit_samples
    helix = RELEASE/'studies/helix-topology'
    sys.path[:0] = [str(helix), str(RELEASE)]
    from infrastructure import study_support as hs
    ab, route = hs.load_study_modules()
    source = STUDY/'publication_inputs/secondary_backshift_initial.json'
    cfg = json.loads(source.read_text())
    _, resolved, assembly, engine, road = hs.build_reference_components(route, duration_s=10.)
    variant = next(v for v in ab.VARIANTS if v.key ==
                   ('quasi_static_helix' if args.variant == 'qs' else 'full'))
    if args.variant == 'qs':
        assembly = ab.ablate_assembly(assembly, variant)
    programme = hs.flat_programme(route, cfg['end_s'])
    base, _ = hs.build_slotted_system(route=route, assembly=assembly, engine=engine,
        road_load=road, constants=resolved.constants, programme=programme)
    mode = stick_mode()
    assert str(mode.cvt) == cfg['expected_mode']
    state = initial_state(base, cfg['cvt_vector'])
    # The archived reaction guards the unchanged full model. The reduction
    # changes the closure at the same coordinates, so establish its own
    # initial reaction independently before integrating; do not demand the
    # full model's force from a mechanically different model.
    expected_reaction = cfg['expected_initial_helix_reaction_Nm']
    if args.variant == 'qs':
        from cinder.results.inspection import inspect_cvt_state
        from cinder.model.cvt.actuation import HelicalTorqueReactionForce
        inspection = inspect_cvt_state(system=base.cvt, time=0.,
            vector=base.layout.view(state, 'cvt'), mode=mode.cvt,
            shaft_boundaries=base._shaft_boundaries(time=0., state=state),
            include_closure_audit=True)
        law = next(l for l in assembly.pulleys.secondary.actuator.force_laws
                   if isinstance(l, HelicalTorqueReactionForce))
        coord = inspection.contact.snapshot.geometry.secondary_axial_coordinate
        coupling = base.cvt.model.secondary_helical_coupling.evaluate_from_local_coordinate(
            axial_position=coord.value, d_axial_position_ds=coord.d_value_ds,
            d2_axial_position_ds2=coord.d2_value_ds2)
        expected_reaction = (.5 * inspection.closure_audit.unknowns.secondary_torque
            + law.spec.torsional_stiffness * (law.spec.initial_twist - coupling.theta))
    restart = hs.Restart(50., 49.991117969970205, 0., state, mode, expected_reaction)
    settings = dict(zip(('rtol','atol','max_step_s'),
                       (3e-4,3e-7,.002) if args.level=='nominal' else (1e-5,1e-8,.0002)))
    out = args.output_dir/(f'm{abs(args.torque):g}_{args.level}'
        + ('_qs' if args.variant == 'qs' else ''))
    out.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()
    print('START', out.name, flush=True)
    run, result, status = hs.run_secondary_torque_probe(route=route, ab=ab,
        restart=restart, assembly=assembly, engine=engine, road_load=road,
        constants=resolved.constants, added_torque_Nm=args.torque,
        onset_s=cfg['onset_s'], ramp_s=cfg['ramp_s'],
        hold_s=cfg['end_s']-cfg['onset_s']-cfg['ramp_s'], sample_step_s=.0001,
        reporting_variant=variant, **settings)
    if run is None:
        raise RuntimeError(str(result.termination_reason))
    assert len(result.segments)==1, 'Selected continuous window acquired a transition'
    signal=hs.SmoothStep(onset_s=cfg['onset_s'],ramp_s=cfg['ramp_s'],target=args.torque)
    fresh,_=hs.build_slotted_system(route=route, assembly=assembly, engine=engine,
        road_load=road, constants=resolved.constants, programme=programme, added_secondary_torque=signal)
    local, audit = audit_samples(fresh,run.samples)
    assert audit['negative_local_load_count']==0
    assert audit['minimum_static_margin']>0
    write_rows(out/'trajectory.csv.gz',[s.row for s in run.samples])
    write_rows(out/'local_wrap_audit.csv.gz',local)
    (out/'events.json').write_text(json.dumps([{'start_s':s.start_time,'end_s':s.end_time,
        'mode':str(s.mode),'events':list(s.fired_event_names)} for s in result.segments],indent=2)+'\n')
    sources=[Path(__file__),Path(__file__).with_name('run_secondary_publication.py'),source,
             *helix.glob('infrastructure/*.py'),*STUDY.glob('infrastructure/*.py'),
             *RELEASE.glob('defaults/**/*.py'),*RELEASE.glob('defaults/**/*.json')]
    summary={'release_commit':cfg['release_commit'],'cinder_version':cinder.__version__,
        'cinder_path':str(Path(cinder.__file__).resolve()),'level':args.level,
        'variant':args.variant, 'initial_reaction_guard_Nm':float(expected_reaction),
        'added_secondary_torque_Nm':args.torque,'settings':settings,'sample_step_s':.0001,
        'completed':result.completed,'segment_count':len(result.segments),'audit':audit,
        'elapsed_s':time.monotonic()-started,
        'source_sha256':{str(s.relative_to(RELEASE)):hashlib.sha256(s.read_bytes()).hexdigest() for s in sources},
        'output_sha256':{s.name:hashlib.sha256(s.read_bytes()).hexdigest() for s in out.iterdir() if s.name!='summary.json'}}
    (out/'summary.json').write_text(json.dumps(summary,indent=2,allow_nan=False)+'\n')
    print('DONE',out.name,summary['elapsed_s'],flush=True)


if __name__=='__main__':
    main()
