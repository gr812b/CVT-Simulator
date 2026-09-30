"""Focused Ballew reporting regressions; no CVT transient integration."""
import ast
from collections import Counter
import contextlib
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import shutil
import sys
import tempfile
from types import SimpleNamespace
import unittest
import numpy as np

ROOT=Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
from results_health.slip import (DEFINITION, HEALTH_POLICY,
    RELATIVE_SPEED_TOLERANCE_M_PER_S, publication_slip_channels,
    require_slip_health, verify_publication_slip_channels, cumulative_segmentwise)


def fixture(relative=(1e-7,1e-7,-1.,-1.),force=461.5384615384613):
    data={'time_s':np.array([0.,.001,.001,5.]),'segment_id':np.array([0,0,1,1])}
    for side in ('primary','secondary'):
        data[f'contact.{side}_lambda']=np.ones(4)
        data[f'contact.{side}_normal_resultant']=np.full(4,force)
        data[f'contact.{side}_relative_speed']=np.array(relative if side=='primary' else [0.,0.,0.,0.])
    modes={0:'engaged/free/both_slip',1:'engaged/free/both_slip'}
    return data,modes


class BallewAccountingHotfixTests(unittest.TestCase):
    def test_observed_microwatt_scale_no_longer_aborts_near_zero(self):
        d,m=fixture();o,a=publication_slip_channels(d,m)
        p=a['contacts']['primary']
        self.assertAlmostEqual(p['max_sliding_pair_power_W'],4.615384615384613e-5)
        self.assertTrue(a['health']['passed'])
        self.assertGreater(p['positive_sliding_work_J'],0)
        self.assertLess(p['positive_sliding_work_J'],p['positive_work_allowance_J'])
        self.assertTrue(p['max_positive_power_sample']['near_zero_speed'])

    def test_same_power_outside_zero_band_fails(self):
        d,m=fixture(relative=(1e-4,1e-4,-1.,-1.),force=.4615384615384613)
        with self.assertRaisesRegex(ValueError,'outside the numerical zero-speed band'):
            publication_slip_channels(d,m)

    def test_near_zero_is_not_unlimited_energy_permission(self):
        d,m=fixture(relative=(1e-7,)*4,force=1e10)
        o,a=publication_slip_channels(d,m,enforce_health=False)
        self.assertFalse(a['health']['passed'])
        self.assertTrue(a['contacts']['primary']['sign_check_passed'])
        self.assertFalse(a['contacts']['primary']['work_budget_passed'])
        with self.assertRaises(ValueError):require_slip_health(a)

    def test_wrong_sign_retains_diagnostic_when_requested(self):
        d,m=fixture(relative=(.1,.1,-1.,-1.))
        o,a=publication_slip_channels(d,m,enforce_health=False)
        self.assertFalse(a['health']['passed'])
        self.assertEqual(a['contacts']['primary']['outside_speed_band_count'],2)
        self.assertGreater(o['publication.primary_positive_sliding_work_J'][-1],0)
        with self.assertRaises(ValueError):require_slip_health(a)

    def test_endpoint_not_blanket_exempted(self):
        d,m=fixture(relative=(0.,.1,-1.,-1.))
        o,a=publication_slip_channels(d,m,enforce_health=False)
        self.assertFalse(a['health']['passed'])
        example=a['contacts']['primary']['outside_speed_band_examples'][0]
        self.assertTrue(example['retained_endpoint'])

    def test_gross_minus_positive_equals_net(self):
        d,m=fixture();o,a=publication_slip_channels(d,m)
        np.testing.assert_allclose(o['publication.primary_net_sliding_work_removed_J'],
            o['publication.primary_slip_dissipation_J']-o['publication.primary_positive_sliding_work_J'])

    def test_sticking_drift_stays_separate(self):
        d,m=fixture(relative=(1e-4,1e-4,-1.,-1.));m[0]='engaged/free/stick_stick'
        o,a=publication_slip_channels(d,m)
        self.assertEqual(o['publication.primary_slip_dissipation_J'][1],0)
        self.assertGreater(o['publication.primary_sticking_drift_work_J'][1],0)
        self.assertEqual(a['contacts']['primary']['positive_sliding_work_J'],0)

    def test_original_tiny_injection_regression(self):
        d,m=fixture(relative=(1e-9,)*4,force=500.)
        o,a=publication_slip_channels(d,m)
        self.assertTrue(a['health']['passed'])
        self.assertEqual(a['contacts']['primary']['sliding_loss_J'],0)

    def test_pure_dissipation_unchanged(self):
        d,m=fixture(relative=(-1.,)*4,force=500.)
        o,a=publication_slip_channels(d,m)
        self.assertEqual(a['contacts']['primary']['sliding_loss_J'],2500)
        self.assertEqual(a['contacts']['primary']['positive_sliding_work_J'],0)

    def test_input_not_mutated(self):
        d,m=fixture();before={k:v.copy() for k,v in d.items()}
        publication_slip_channels(d,m)
        self.assertEqual(set(d),set(before))
        for key in d:np.testing.assert_array_equal(d[key],before[key])

    def test_reconstructed_arrays_are_checked(self):
        d,m=fixture();o,a=publication_slip_channels(d,m);d.update(o)
        verify_publication_slip_channels(d,m)
        d['publication.primary_slip_dissipation_J'][-1]+=1
        with self.assertRaisesRegex(ValueError,'does not match'):verify_publication_slip_channels(d,m)

    def test_gap_is_not_dropped_from_full_run(self):
        d,m=fixture();d['time_s']=np.array([0.,1.,2.,5.])
        with self.assertRaisesRegex(ValueError,'Missing continuous interval'):publication_slip_channels(d,m)

    def test_event_sides_not_bridged(self):
        np.testing.assert_allclose(cumulative_segmentwise([0,1,1,2],[2,2,8,8],[0,0,1,1]),[0,2,2,10])

    def test_finite_contact_values_required(self):
        d,m=fixture();d['contact.primary_lambda'][0]=np.nan
        with self.assertRaisesRegex(ValueError,'nonfinite'):publication_slip_channels(d,m)

    def test_unknown_mode_not_assumed_sticking(self):
        d,m=fixture();m[0]='engaged/free/wrong'
        with self.assertRaises(ValueError):publication_slip_channels(d,m)

    def test_wrong_dimensions_rejected(self):
        d,m=fixture();d['contact.primary_lambda']=np.ones(3)
        with self.assertRaisesRegex(ValueError,'unaligned'):publication_slip_channels(d,m)

    def test_all_segments_must_have_modes(self):
        d,m=fixture();m.pop(1)
        with self.assertRaisesRegex(ValueError,'enumerate'):publication_slip_channels(d,m)

    def test_noninteger_segment_not_truncated(self):
        d,m=fixture();d['segment_id']=np.array([0.,0.,1.2,1.2])
        with self.assertRaises(ValueError):publication_slip_channels(d,m)

    def test_old_policy_not_silently_accepted(self):
        with self.assertRaises(ValueError):require_slip_health({'definition':'old','health':{'passed':True}})

    def test_deadzone_nans_not_included(self):
        d,m=fixture();m={0:'deadzone/free',1:'deadzone/free'};d['contact.primary_lambda'][:]=np.nan
        o,a=publication_slip_channels(d,m)
        self.assertTrue(a['health']['passed'])
        self.assertEqual(a['contacts']['primary']['sliding_loss_J'],0)


class RetentionHotfixTests(unittest.TestCase):
    """Exercise production retention functions with synthetic result objects."""
    def functions(self):
        path=ROOT/'studies/ballew-2015/infrastructure/benchmark/retention.py'
        tree=ast.parse(path.read_text())
        definitions=[n for n in tree.body if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef))]
        namespace=dict(np=np,Path=Path,json=json,sys=sys,shutil=shutil,hashlib=hashlib,Counter=Counter,
            cinder=SimpleNamespace(__version__='1.1.2',__file__=__file__),
            ContactKinematicTolerances=lambda:SimpleNamespace(relative_speed_tolerance=1e-7),
            DEFINITION=DEFINITION,HEALTH_POLICY=HEALTH_POLICY,
            RELATIVE_SPEED_TOLERANCE_M_PER_S=RELATIVE_SPEED_TOLERANCE_M_PER_S,
            publication_slip_channels=publication_slip_channels,
            simulation_fingerprint=lambda study:'synthetic-fingerprint',compact_mode=lambda mode:mode)
        exec(compile(ast.Module(body=definitions,type_ignores=[]),str(path),'exec'),namespace)
        return namespace

    def example(self,relative=.1):
        t=np.array([0.,1.]);state=np.zeros((6,2))
        native=SimpleNamespace(time=t,state=state,start_time=0.,end_time=1.,
            mode='engaged/free/both_slip',dense_state_at=lambda times:np.zeros((6,len(times))))
        signals={}
        for side in ('primary','secondary'):
            for field,value in (('lambda',1.),('normal_resultant',1000.),('relative_speed',relative)):
                signals[f'contact.{side}_{field}']=SimpleNamespace(values=np.full(2,value))
        result=SimpleNamespace(trace=SimpleNamespace(segments=[native],transitions=[],final_time=1.),
            segments=[SimpleNamespace(time=t,signals=signals)])
        belt=SimpleNamespace(mass=1.,linear_density=1.,density=1000.,center_of_mass_path_length=1.,outer_length=1.1)
        setup=SimpleNamespace(assembly=SimpleNamespace(inertias=SimpleNamespace(belt=belt)),
            system=SimpleNamespace(layout=SimpleNamespace(view_matrix=lambda v,name:v[:5])))
        return setup,result

    def test_failed_energy_check_does_not_destroy_completed_trace(self):
        ns=self.functions();setup,result=self.example()
        with tempfile.TemporaryDirectory() as d,contextlib.redirect_stderr(io.StringIO()):
            out=Path(d);ns['retain_result'](setup,result,out)
            for name in ('native_trace.npz','segmented_report.npz','comparison_grid.npz','trace_manifest.json','resolved_belt_mass.json','slip_accounting.json'):
                self.assertTrue((out/name).is_file(),name)
            a=json.loads((out/'slip_accounting.json').read_text())
            self.assertFalse(a['health']['passed'])
            with self.assertRaises(ValueError):require_slip_health(a)
            with np.load(out/'segmented_report.npz') as r:self.assertIn('publication.primary_positive_sliding_work_J',r.files)

    def test_nonfinite_diagnostic_still_keeps_raw_data(self):
        ns=self.functions();setup,result=self.example(relative=float('nan'))
        with tempfile.TemporaryDirectory() as d,contextlib.redirect_stderr(io.StringIO()):
            out=Path(d);ns['retain_result'](setup,result,out)
            self.assertTrue((out/'segmented_report.npz').is_file())
            a=json.loads((out/'slip_accounting.json').read_text())
            self.assertFalse(a['health']['passed']);self.assertIn('structural_accounting_error',a)

    def test_shared_accounting_is_snapshotted(self):
        ns=self.functions()
        with tempfile.TemporaryDirectory() as d:
            release=Path(d);study=release/'studies/ballew-2015';out=release/'new_output'
            (study/'reference').mkdir(parents=True);out.mkdir();(release/'results_health').mkdir()
            (study/'study.json').write_text('{}');(study/'reference/manifest.json').write_text('{}')
            (study/'run.py').write_text('pass\n')
            for name in ('__init__.py','common.py','slip.py'):(release/'results_health'/name).write_text('# '+name+'\n')
            ns['record_execution'](study,out,{'method':'LSODA'})
            p=json.loads((out/'execution_provenance.json').read_text())
            self.assertIn('_results_health/slip.py',p['input_sha256'])
            self.assertEqual(p['input_sha256']['_results_health/slip.py'],hashlib.sha256((out/'execution_inputs/_results_health/slip.py').read_bytes()).hexdigest())


@unittest.skipUnless(importlib.util.find_spec('cinder') is not None,'Requires installed CINDER 1.1.2')
class InstalledToleranceCheck(unittest.TestCase):
    def test_reporting_band_matches_pinned_release(self):
        from cinder.model.cvt.contact.tolerances import ContactKinematicTolerances
        self.assertEqual(ContactKinematicTolerances().relative_speed_tolerance,RELATIVE_SPEED_TOLERANCE_M_PER_S)


if __name__=='__main__':unittest.main()
