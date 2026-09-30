"""Fast regression tests; none integrates a CVT trajectory."""
import ast
import importlib.util
import json
import math
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
import numpy as np
from results_health.common import require_complete,strict_bool,verify_hashes,digest,write_json,simulation_fingerprint
from results_health.slip import publication_slip_channels,cumulative_segmentwise
from results_health.guards import course_row_failures,course_endpoint_audit,belt_run_findings
from results_health.engine import Step,run_plan
from results_health.plan import build_plan
from results_health.audits import event_sides


def contact_input():
    d={'time_s':np.array([0.,1.,1.,2.]),'segment_id':np.array([0,0,1,1])}
    for side in ('primary','secondary'):
        d['contact.'+side+'_lambda']=np.full(4,-.5)
        d['contact.'+side+'_normal_resultant']=np.full(4,1000.)
        d['contact.'+side+'_relative_speed']=np.zeros(4)
    return d


class SlipTests(unittest.TestCase):
    def test_sticking_drift_is_not_slip_loss(self):
        d=contact_input();d['contact.primary_relative_speed']=np.array([.2,.2,1e-5,1e-5])
        o,a=publication_slip_channels(d,{0:'engaged/free/primary_slip_secondary_stick',1:'engaged/free/stick_stick'})
        self.assertAlmostEqual(o['publication.primary_slip_dissipation_J'][-1],100.)
        self.assertAlmostEqual(o['publication.primary_sticking_drift_work_J'][-1],-.005)
        self.assertAlmostEqual(a['contacts']['primary']['legacy_minus_sliding_J'],.005)
        self.assertNotIn('publication.primary_slip_dissipation_J',d)

    def test_sticking_positive_drift_is_signed_not_heat(self):
        d=contact_input();d['contact.primary_relative_speed'][:]=-1e-5
        o,_=publication_slip_channels(d,{0:'engaged/free/stick_stick',1:'engaged/free/stick_stick'})
        self.assertEqual(o['publication.primary_slip_dissipation_J'][-1],0)
        self.assertGreater(o['publication.primary_sticking_drift_work_J'][-1],0)

    def test_wrong_sign_sliding_raises(self):
        d=contact_input();d['contact.primary_relative_speed'][:]=-.2
        with self.assertRaisesRegex(ValueError,'energy-adding'):
            publication_slip_channels(d,{0:'engaged/free/both_slip',1:'engaged/free/both_slip'})

    def test_tiny_injection_is_recorded(self):
        d=contact_input();d['contact.primary_relative_speed'][:]=-1e-9
        o,a=publication_slip_channels(d,{0:'engaged/free/both_slip',1:'engaged/free/both_slip'})
        self.assertEqual(o['publication.primary_slip_dissipation_J'][-1],0)
        self.assertGreater(a['contacts']['primary']['tolerated_positive_sliding_work_J'],0)

    def test_nonfinite_engaged_fails(self):
        d=contact_input();d['contact.primary_lambda'][1]=np.nan
        with self.assertRaises(ValueError):publication_slip_channels(d,{0:'engaged/free/stick_stick',1:'engaged/free/stick_stick'})

    def test_deadzone_nonapplicable_nan_not_used(self):
        d=contact_input();d['contact.primary_lambda'][:]=np.nan
        o,_=publication_slip_channels(d,{0:'deadzone/free',1:'deadzone/lower_stop'})
        self.assertEqual(o['publication.primary_slip_dissipation_J'][-1],0)

    def test_unknown_mode_fails(self):
        with self.assertRaises(ValueError):publication_slip_channels(contact_input(),{0:'engaged/free/unknown',1:'engaged/free/stick_stick'})

    def test_segment_modes_required(self):
        with self.assertRaises(ValueError):publication_slip_channels(contact_input(),{0:'engaged/free/stick_stick'})

    def test_no_bridge_across_reset(self):
        np.testing.assert_allclose(cumulative_segmentwise([0,1,5,6],[2,2,10,10],[0,0,1,1]),[0,2,2,12])

    def test_disjoint_segment_fails(self):
        with self.assertRaises(ValueError):cumulative_segmentwise([0,1,2],[1,1,1],[0,1,0])

    def test_nonchronological_fails(self):
        with self.assertRaises(ValueError):cumulative_segmentwise([1,0],[1,1],[0,0])

    def test_empty_fails(self):
        with self.assertRaises(ValueError):cumulative_segmentwise([],[],[])


def good_course_row():
    return {'time_s':1.,'segment_id':0,'sample_location':'end','engagement':'engaged',
            'shift_constraint':'free','normal_primary_N':1.,'normal_secondary_N':1.,
            'min_tension_N':1.,'primary_min_dN_dtheta_N_per_rad':1.,'secondary_min_dN_dtheta_N_per_rad':1.,
            'primary_lambda':.1,'secondary_lambda':-.1,'primary_vrel_m_s':0.,'secondary_vrel_m_s':0.,
            'primary_sliding':False,'secondary_sliding':False,
            'primary_static_utilization':.2,'secondary_static_utilization':.2,
            'primary_slip_loss_W':0.,'secondary_slip_loss_W':0.}


def good_belt():
    return {'completed':True,'audit':{'inspection_errors':0,'engaged_samples':10,
        'primary.min_tension_N':1.,'secondary.min_tension_N':1.,
        'primary.min_local_normal_N_per_rad':1.,'secondary.min_local_normal_N_per_rad':1.,
        'max_endpoint_vs_equation_residual_N':0.,'closure.max_abs_residual':0.}}


class GuardTests(unittest.TestCase):
    def test_course_endpoint_is_checked(self):
        r=good_course_row();r['normal_primary_N']=-1
        a=course_endpoint_audit([r]);self.assertEqual(a['failed_rows'],1)
        self.assertEqual(a['failures_by_location'],{'end':1})

    def test_course_valid_endpoint(self):self.assertEqual(course_row_failures(good_course_row()),[])

    def test_endpoint_inspection_error_fails(self):
        r=good_course_row();r['inspection_error']='bad';self.assertEqual(course_row_failures(r),['inspection_error'])

    def test_nan_contact_fails(self):
        r=good_course_row();r['min_tension_N']=float('nan');self.assertTrue(course_row_failures(r))

    def test_static_margin_fails(self):
        r=good_course_row();r['primary_static_utilization']=1.1;self.assertTrue(course_row_failures(r))

    def test_unknown_boolean_fails(self):
        r=good_course_row();r['primary_sliding']='maybe';self.assertTrue(course_row_failures(r))

    def test_csv_false_is_not_truthy(self):
        r=good_course_row();r['primary_sliding']='False';self.assertFalse(course_row_failures(r))

    def test_negative_support_fails(self):
        r=good_course_row();r.update(shift_constraint='upper_stop',upper_stop_reaction_N=-1.);self.assertTrue(course_row_failures(r))

    def test_missing_support_fails(self):
        r=good_course_row();r['shift_constraint']='upper_stop';self.assertTrue(course_row_failures(r))

    def test_belt_valid(self):self.assertEqual(belt_run_findings('valid',good_belt()),[])

    def test_belt_negative_fails(self):
        s=good_belt();s['audit']['primary.min_tension_N']=-.001;self.assertTrue(belt_run_findings('bad',s))

    def test_belt_nan_fails(self):
        s=good_belt();s['audit']['secondary.min_local_normal_N_per_rad']=float('nan');self.assertTrue(belt_run_findings('bad',s))

    def test_belt_missing_count_fails(self):
        s=good_belt();s['audit'].pop('inspection_errors');self.assertTrue(belt_run_findings('bad',s))

    def test_belt_incomplete_fails(self):
        s=good_belt();s['completed']=False;self.assertTrue(belt_run_findings('bad',s))

    def test_complete_requires_true(self):
        with self.assertRaises(ValueError):require_complete(False,10,10)

    def test_complete_requires_final_time(self):
        with self.assertRaises(ValueError):require_complete(True,9,10)

    def test_nan_time_fails(self):
        with self.assertRaises(ValueError):require_complete(True,float('nan'),10)

    def test_good_completion(self):require_complete(True,10.,10.)

    def test_unknown_bool_fails(self):
        with self.assertRaises(ValueError):strict_bool('false')

    def test_missing_outgoing_event_side(self):
        e=[dict(event_id='E1',time_s=1.,pre_state=[0]*5,post_state=[0]*5,previous_mode='x',next_mode='y')]
        self.assertEqual(len(event_sides([],e)['missing_event_sides']),2)

    def test_exact_sides_match(self):
        rows=[dict(time_s=1.,sample_location=location,regime=mode,omega_p_rad_s=0,omega_s_rad_s=0,belt_speed_m_s=0,shift_mm=0,shift_rate_mm_s=0)
              for location,mode in [('end','x'),('start','y')]]
        e=[dict(event_id='E1',time_s=1.,pre_state=[0]*5,post_state=[0]*5,previous_mode='xx',next_mode='yy')]
        self.assertEqual(event_sides(rows,e)['verified_event_sides'],2)


class PipelineTests(unittest.TestCase):
    def test_independent_failure_does_not_abort(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);good=root/'good.txt'
            steps=[Step('bad','test',[sys.executable,'-c','raise RuntimeError("intentional")']),
                   Step('dependent','test',[sys.executable,'-c','raise RuntimeError("must not run")'],['bad']),
                   Step('good','test',[sys.executable,'-c',f'from pathlib import Path;Path({str(good)!r}).write_text("ok")'],products=[str(good)],role='health')]
            r=run_plan(steps,root,root,{'mode':'unit','source_identity':'x'})
            self.assertEqual([x['status'] for x in r['steps']],['FAIL','BLOCKED','PASS'])
            self.assertTrue(good.exists());self.assertFalse(r['all_requested_steps_passed'])
            for name in ('health_report.json','health_report.md','health_report.html'):self.assertTrue((root/name).is_file())

    def test_timeout_does_not_abort_independent_health(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            steps=[Step('slow','test',[sys.executable,'-c','import time;time.sleep(30)']),
                   Step('after-timeout','test',[sys.executable,'-c','pass'],role='health')]
            r=run_plan(steps,root,root,{'mode':'timeout-test'},timeout_s=5.0)
            self.assertEqual([x['status'] for x in r['steps']],['TIMEOUT','PASS'])
            self.assertTrue((root/'health_report.json').is_file())

    def test_missing_input_is_not_a_pass(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);s=Step('missing','test',[sys.executable,'-c','pass'],requires=[str(root/'absent')],role='health')
            r=run_plan([s],root,root,{'mode':'unit'});self.assertEqual(r['steps'][0]['status'],'MISSING')

    def test_missing_interpreter_report(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);s=Step('bad','test',[str(root/'no-python')])
            r=run_plan([s],root,root,{'mode':'unit'});self.assertEqual(r['steps'][0]['status'],'FAIL')

    def test_generation_reuse_hashes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);dest=root/'file';count=root/'count'
            code=f'from pathlib import Path;p=Path({str(count)!r});p.write_text(str(int(p.read_text())+1) if p.exists() else "1");Path({str(dest)!r}).write_text("ok")'
            s=Step('generate','test',[sys.executable,'-c',code],products=[str(dest)])
            run_plan([s],root,root,{'source_identity':'x'})
            r=run_plan([s],root,root,{'source_identity':'x'},resume=True)
            self.assertEqual(r['steps'][0]['status'],'REUSED');self.assertEqual(count.read_text(),'1')
            dest.write_text('changed');r=run_plan([s],root,root,{'source_identity':'x'},resume=True)
            self.assertEqual(r['steps'][0]['status'],'PASS');self.assertEqual(count.read_text(),'2')

    def test_health_checks_always_repeat(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);s=Step('health','test',[sys.executable,'-c','pass'],role='health')
            run_plan([s],root,root,{'source_identity':'x'})
            r=run_plan([s],root,root,{'source_identity':'x'},resume=True)
            self.assertEqual(r['steps'][0]['status'],'PASS')

    def test_nonzero_without_declared_output_cannot_pass(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);s=Step('empty','test',[sys.executable,'-c','pass'],products=[str(root/'absent')])
            r=run_plan([s],root,root,{});self.assertEqual(r['steps'][0]['status'],'FAIL')

    def test_correct_plan_has_five_ballew_runs(self):
        with tempfile.TemporaryDirectory() as tmp:
            steps=build_plan(ROOT,Path(tmp),sys.executable,'correct',save=False)
            self.assertEqual(len([s for s in steps if s.group=='ballew' and s.role=='generation']),5)
            self.assertEqual(len({s.id for s in steps}),len(steps))

    def test_all_plan_has_independent_belt_jobs(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);plan=root/'studies/reduced-belt-transients/publication_inputs/run_plan.json';plan.parent.mkdir(parents=True)
            plan.write_text(json.dumps([dict(case='flat',level=level,variant='full') for level in ('nominal','tight')]))
            steps=build_plan(root,root/'out',sys.executable,'all',save=False)
            ids=set()
            for s in steps:self.assertTrue(set(s.dependencies)<=ids);ids.add(s.id)
            self.assertEqual(len([s for s in steps if s.id.startswith('belt-flat_')]),2)
            self.assertEqual(len([s for s in steps if s.id.startswith('primary-baseline_') or s.id.startswith('primary-transient_')]),8)
            self.assertEqual(len([s for s in steps if s.id.startswith('backshift-')]),16)

    def test_hash_mismatch_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);p=root/'a';p.write_text('a');h=digest(p);p.write_text('b')
            with self.assertRaises(ValueError):verify_hashes(root,{'a':h})

    def test_hash_path_escape_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ValueError):verify_hashes(Path(tmp),{'../outside':'hash'})


class InstalledSourceTests(unittest.TestCase):
    """These run against the real CINDER assembly when the local environment exists."""
    @unittest.skipUnless(importlib.util.find_spec('cinder') and (ROOT/'studies/ballew-2015/study.json').exists(),'CINDER/repository not present in packaging test environment')
    def test_ballew_resolved_assembly_mass(self):
        import subprocess
        source=ROOT/'studies/ballew-2015'
        code='from infrastructure.benchmark.case import build_ballew_inertias; b=build_ballew_inertias().belt; assert abs(b.mass-1.)<2e-12; print(b.mass,b.density,b.center_of_mass_path_length)'
        env=__import__('os').environ.copy();env['PYTHONPATH']=str(source)+__import__('os').pathsep+str(ROOT)
        subprocess.run([sys.executable,'-c',code],env=env,check=True)

    @unittest.skipUnless(importlib.util.find_spec('cinder') and (ROOT/'studies/actuator-dynamics/study.json').exists(),'CINDER/repository not present in packaging test environment')
    def test_reduced_helix_keeps_original_diagnostic_inertia(self):
        import subprocess
        source=ROOT/'studies/actuator-dynamics'
        code="""from infrastructure import ablation_core as a
from defaults.reference_model import decode_reference_case
assembly=decode_reference_case().assembly
variant=next(v for v in a.VARIANTS if v.key=='quasi_static_helix')
reduced=a.ablate_assembly(assembly,variant)
law=next(l for l in reduced.pulleys.secondary.actuator.force_laws if isinstance(l,a.QuasiStaticHelicalTorqueReactionForce))
assert law.physical_movable_inertia==assembly.inertias.secondary.movable_sheave_rotational_inertia
assert reduced.inertias.secondary.movable_sheave_rotational_inertia==0.
print('Original physical inertia retained as diagnostic metadata only')
"""
        env=__import__('os').environ.copy();env['PYTHONPATH']=str(source)+__import__('os').pathsep+str(ROOT)
        subprocess.run([sys.executable,'-c',code],env=env,check=True)


class AdapterTests(unittest.TestCase):
    def test_worker_supports_absolute_sibling_import(self):
        from results_health import worker
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);p=root/'studies/toy/example';p.mkdir(parents=True)
            (p/'__init__.py').write_text('')
            (p/'health_test_sibling.py').write_text('VALUE=17\n')
            (p/'task.py').write_text('from health_test_sibling import VALUE\ndef main():\n    return VALUE\n')
            oldpath=sys.path[:]
            try:
                with patch.object(worker,'RELEASE',root):
                    self.assertEqual(worker.module('toy','example/task.py').main(),17)
            finally:
                sys.path[:]=oldpath
                for k in ('example.task','example','health_test_sibling'):sys.modules.pop(k,None)

    def test_fresh_primary_source(self):
        import gzip
        from results_health.primary_source import primary_source
        from results_health import MECHANICS_COMMIT
        with tempfile.TemporaryDirectory() as tmp:
            release=Path(tmp);study=release/'studies/actuator-dynamics';raw=release/'raw'
            base=release/'defaults/baja/simulation_case.json';base.parent.mkdir(parents=True);base.write_text('{"assembly":{}}')
            cfg=study/'publication_inputs/primary_publication.json';cfg.parent.mkdir(parents=True);cfg.write_text('{"baseline_duration_s":10}')
            for level in ('nominal','tight'):
                directory=raw/f'baseline_{level}_full';directory.mkdir(parents=True)
                (directory/'trajectory.csv.gz').write_bytes(gzip.compress(b'time_s,variant\n0,full\n10,full\n'))
                write_json(directory/'provenance.json',{'kind':'baseline','level':level,'variant':'full','cinder_version':'1.1.2',
                    'release_commit':MECHANICS_COMMIT,'source_sha256':{'defaults\\baja\\simulation_case.json':digest(base)}})
            source,identity=primary_source(None,raw,study,'primary/','release/')
            with source as z:self.assertEqual(z.read('release/defaults/baja/simulation_case.json'),base.read_bytes())
            self.assertEqual(identity['kind'],'fresh_full_baselines')

    def test_new_ballew_code_snapshot_changes_cache_identity(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);study=root/'studies/test';(study/'infrastructure').mkdir(parents=True)
            (study/'study.json').write_text('{}')
            file=study/'infrastructure/a.py';file.write_text('X=1')
            a=simulation_fingerprint(study);file.write_text('X=2');b=simulation_fingerprint(study)
            self.assertNotEqual(a,b)
            (study/'README.md').write_text('new prose');self.assertEqual(simulation_fingerprint(study),b)

if __name__=='__main__':unittest.main()
