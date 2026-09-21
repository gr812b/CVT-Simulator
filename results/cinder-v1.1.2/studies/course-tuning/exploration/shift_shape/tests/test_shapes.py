from pathlib import Path
from copy import deepcopy
import importlib.util
import sys
import tempfile
import unittest
import numpy as np
ROOT=Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
from infrastructure.common import load_json,write_json
from infrastructure.tunes import resolve_tune,component
from shift_shape.tuning import resolve_shape_tune,_segment,make_ramp
from shift_shape.metrics import launch_parts,describe,compare_to_reference,secants,eligible


def samples(offset=0.,tilt=0.):
    rows=[]
    for n,f in enumerate(np.linspace(.14,.86,401)):
        sec=500+1800*f
        rows.append(dict(time_s=n*.01,distance_m=10+n*.15,primary_rpm=3000+.06*sec+offset+tilt*sec,
            secondary_rpm=sec,active_shift_fraction=float(f),shift_rate_mm_s=1.,engagement='engaged',
            shift_constraint='free',contact_mode='stick_stick',segment_id=0,inspection_error=''))
    return rows


class MetricsTests(unittest.TestCase):
    def test_constant_offset_has_no_shape(self):
        stats,_=compare_to_reference(launch_parts(samples(250)),launch_parts(samples()))
        self.assertAlmostEqual(stats['mean_primary_offset_rpm'],250.,places=8)
        self.assertLess(stats['offset_removed_shape_rms_rpm'],1e-8)
        self.assertLess(abs(stats['delta_fitted_slope_rpm_per_1000_secondary_rpm']),1e-8)
    def test_added_slope_detected(self):
        stats,_=compare_to_reference(launch_parts(samples(tilt=.12)),launch_parts(samples()))
        self.assertAlmostEqual(stats['delta_fitted_slope_rpm_per_1000_secondary_rpm'],120.,places=8)
        self.assertGreater(stats['offset_removed_shape_rms_rpm'],30.)
    def test_secant_units(self):
        row=describe(launch_parts(samples()))
        self.assertEqual(row['shape_status'],'complete_f20_f80')
        self.assertAlmostEqual(row['overall_slope_rpm_per_1000_secondary_rpm'],60.,places=7)
        self.assertTrue(all(abs(r['slope_rpm_per_1000_secondary_rpm']-60)<1e-7 for r in secants(launch_parts(samples()))))
    def test_high_stop_not_a_shift_slope(self):
        r=samples();r=[{**x,'shift_constraint':'upper_stop'} for x in r]
        self.assertEqual(launch_parts(r),[])
    def test_slip_not_a_shift_slope(self):
        self.assertFalse(eligible({**samples()[20],'contact_mode':'primary_slip_secondary_stick'}))
    def test_backshift_not_upshift(self):
        self.assertFalse(eligible({**samples()[20],'shift_rate_mm_s':-1.}))
    def test_road_after_first_flat_excluded(self):
        r=samples();r.insert(100,{**r[100],'distance_m':121.})
        self.assertLess(max(p[-1]['time_s'] for p in launch_parts(r)),r[100]['time_s']+1e-8)
    def test_invalid_gap_not_bridged(self):
        r=samples()
        for i in range(160,210):r[i]['contact_mode']='both_slip'
        p=launch_parts(r)
        self.assertEqual(len(p),2)
        self.assertIsNone(describe(p)['overall_slope_rpm_per_1000_secondary_rpm'])
    def test_administrative_duplicate_joined(self):
        r=samples();r.insert(200,{**r[199],'segment_id':1})
        self.assertEqual(len(launch_parts(r)),1)
    def test_reset_duplicate_splits(self):
        r=samples();r.insert(200,{**r[199],'segment_id':1,'primary_rpm':3300.})
        self.assertGreater(len(launch_parts(r)),1)
    def test_nonmonotonic_speed_not_sorted(self):
        r=samples();r[180]['secondary_rpm']=200.
        self.assertGreater(len(launch_parts(r)),1)
    def test_insufficient_range_is_visible(self):
        short=samples()[:12]
        self.assertNotEqual(describe(launch_parts(short))['shape_status'],'complete_f20_f80')
    def test_partial_earlier_excursion_not_used_for_later_secant(self):
        partial=launch_parts(samples(offset=500.)[:120])[0]
        complete=[{**r,'time_s':r['time_s']+10.} for r in launch_parts(samples())[0]]
        row=describe([partial,complete])
        self.assertAlmostEqual(row['overall_slope_rpm_per_1000_secondary_rpm'],60.,places=7)
        self.assertEqual(row['overall_slope_path_id'],1)
        self.assertGreater(row['overall_slope_start_time_s'],10.)
    def test_narrow_overlap_is_visible(self):
        p=launch_parts(samples()[:45]);stats,_=compare_to_reference(p,p)
        self.assertEqual(stats['comparison_status'],'narrow_overlap_do_not_rank')


class InputTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        release=ROOT.parent.parents[1]
        cls.base=load_json(release/'defaults/baja/simulation_case.json')
        cls.fleet=load_json(ROOT/'inputs/shift_shape_candidates.json')['competitors']
    def test_fleet_size_unique(self):
        self.assertEqual(len(self.fleet),15)
        self.assertEqual(len({t['id'] for t in self.fleet}),15)
    def test_controls_unchanged(self):
        for t in self.fleet[:3]:
            a,_=resolve_tune(self.base,t);b,_=resolve_shape_tune(self.base,t);self.assertEqual(a,b)
    def test_base_not_mutated(self):
        original=deepcopy(self.base)
        for t in self.fleet:resolve_shape_tune(self.base,t)
        self.assertEqual(original,self.base)
    def test_common_physics_unchanged(self):
        for t in self.fleet:
            d,_=resolve_shape_tune(self.base,t)
            for key in ('scenario','host','shaft_boundaries','execution'):self.assertEqual(d[key],self.base[key])
            for key in ('geometry','inertias','contact'):self.assertEqual(d['assembly'][key],self.base['assembly'][key])
            self.assertEqual(d['assembly']['pulleys']['secondary']['helical_coupling'],self.base['assembly']['pulleys']['secondary']['helical_coupling'])
    def test_mass_moments_preserved_for_rate_ramp_candidates(self):
        b=component(self.base,'primary','fixed_pivot_roller_flyweight')['mass_geometry']
        for t in self.fleet[3:]:
            d,_=resolve_shape_tune(self.base,t)
            self.assertEqual(component(d,'primary','fixed_pivot_roller_flyweight')['mass_geometry'],b)
    def test_rate_matching(self):
        for t in self.fleet:
            d,s=resolve_shape_tune(self.base,t)
            for match in s['matches']:
                if match['component']=='secondary_torsional_spring':self.assertAlmostEqual(match['reference_torque_Nm'],match['matched_torque_Nm'],places=11)
                else:self.assertAlmostEqual(match['reference_signed_force_N'],match['matched_signed_force_N'],places=10)
    def test_primary_gradient_actually_changes(self):
        t=next(t for t in self.fleet if t['id']=='P200');d,_=resolve_shape_tune(self.base,t)
        self.assertEqual(component(d,'primary','axial_spring')['stiffness_N_per_m'],2*component(self.base,'primary','axial_spring')['stiffness_N_per_m'])
    def test_matched_preload_not_hidden(self):
        for t in self.fleet:
            d,s=resolve_shape_tune(self.base,t)
            if s['matches']:self.assertTrue(any('initial_compression_m' in r['path'] or 'initial_twist_rad' in r['path'] for r in s['changes']))
    def test_ramp_preserves_entire_declared_prefix(self):
        from cinder.model.cvt.profiles import PiecewiseRamp
        base=component(self.base,'primary','fixed_pivot_roller_flyweight')['geometry']['ramp_profile']
        p0=PiecewiseRamp([_segment(p) for p in base['segments']])
        for t in self.fleet:
            if t['family']!='ramp_shape':continue
            d,_=resolve_shape_tune(self.base,t);profile=component(d,'primary','fixed_pivot_roller_flyweight')['geometry']['ramp_profile']
            p=PiecewiseRamp([_segment(s) for s in profile['segments']]);self.assertAlmostEqual(p.x_max,p0.x_max,places=13)
            self.assertTrue(all(j.is_continuous(order=3) for j in p.junction_continuity()))
            for x in np.linspace(0,t['knobs']['ramp_prefix_m'],25):
                a,b=p.evaluate(float(x)),p0.evaluate(float(x))
                self.assertAlmostEqual(a.value,b.value,places=12)
                self.assertAlmostEqual(a.first_derivative,b.first_derivative,places=11)
                self.assertAlmostEqual(a.second_derivative,b.second_derivative,places=7)
    def test_ramp_endpoint_angles(self):
        for t in self.fleet:
            if t['family']!='ramp_shape':continue
            from math import atan,degrees
            d,_=resolve_shape_tune(self.base,t);p=_segment(component(d,'primary','fixed_pivot_roller_flyweight')['geometry']['ramp_profile']['segments'][-1])
            self.assertAlmostEqual(degrees(atan(p.evaluate_local(p.length).first_derivative)),t['knobs']['ramp_end_deg'],places=9)
    def test_unknown_knob_rejected(self):
        t=deepcopy(self.fleet[0]);t['knobs']={'bad':1}
        with self.assertRaises(ValueError):resolve_shape_tune(self.base,t)
    def test_double_preload_adjustment_rejected(self):
        t=deepcopy(self.fleet[0]);t['knobs']={'primary_rate_scale':2,'primary_preload_scale':2}
        with self.assertRaises(ValueError):resolve_shape_tune(self.base,t)
    def test_invalid_rate_rejected(self):
        for v in (-1,0,float('nan'),4):
            t=deepcopy(self.fleet[0]);t['knobs']={'primary_rate_scale':v}
            with self.assertRaises(ValueError):resolve_shape_tune(self.base,t)
    def test_invalid_ramp_bounds_rejected(self):
        p=component(self.base,'primary','fixed_pivot_roller_flyweight')['geometry']['ramp_profile']
        with self.assertRaises(ValueError):make_ramp(p,end_deg=35,prefix_m=.003)
    def test_only_allowed_fields_changed(self):
        for t in self.fleet[3:]:
            d,s=resolve_shape_tune(self.base,t)
            for r in s['changes']:
                self.assertTrue(r['path'].startswith('/assembly/pulleys/'))
                self.assertTrue(any(k in r['path'] for k in ('stiffness','initial_compression','initial_twist','ramp_profile')))


class ReproducibilityTests(unittest.TestCase):
    def test_cache_checks_file_contents(self):
        from shift_shape.runner import seal,reusable,ESSENTIAL
        with tempfile.TemporaryDirectory() as tmp:
            d=Path(tmp)
            for n in ESSENTIAL:(d/n).write_text('{}')
            write_json(d/'status.json',{'complete_output':True,'fingerprint':'abc'})
            seal(d,'abc');self.assertTrue(reusable(d,'abc'))
            (d/'diagnostics.csv').write_text('changed');self.assertFalse(reusable(d,'abc'))
    def test_final_source_identity_excludes_new_exploration(self):
        path=ROOT.parent/'infrastructure/common.py'
        spec=importlib.util.spec_from_file_location('_final_identity_check',path)
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        before=module.source_fingerprint()
        p=ROOT/'shift_shape/_test_exploration_identity.py'
        try:
            p.write_text('# test only\n');self.assertEqual(before,module.source_fingerprint())
        finally:p.unlink(missing_ok=True)
    def test_output_lock_refuses_concurrent_runner(self):
        from shift_shape.runner import lock
        with tempfile.TemporaryDirectory() as tmp:
            with lock(Path(tmp)):
                with self.assertRaises(RuntimeError):
                    with lock(Path(tmp)):pass
            self.assertFalse((Path(tmp)/'RUNNING.lock').exists())

if __name__=='__main__':unittest.main()
