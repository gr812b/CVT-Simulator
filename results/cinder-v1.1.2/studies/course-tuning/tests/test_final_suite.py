"""Selection, execution-isolation, resume and portable-archive regression tests."""
from __future__ import annotations
import ast
from copy import deepcopy
import json
from pathlib import Path
import shutil
import sys
from tempfile import TemporaryDirectory
import unittest
from zipfile import ZipFile
import numpy as np
ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
from infrastructure.common import load_json,write_json,digest,RELEASE_ROOT,final_files
from infrastructure.course import Course
from infrastructure.selection import (validate_selection,canonical_file_hash,
    seal_case,reusable_case,archive_attempt,output_lock,ESSENTIAL_CASE_FILES)
from analysis.report_final import pack_results


class SelectionTests(unittest.TestCase):
    def setUp(self):
        self.spec=load_json(ROOT/'study.json');self.fleet=load_json(ROOT/'inputs/competitors.json')['competitors']
        self.course=Course(load_json(ROOT/'inputs/course.json'))
    def test_selection_lock(self):validate_selection()
    def test_exact_final_fleet(self):
        self.assertEqual([x['id'] for x in self.fleet],['R00','W85','P300','RC10','R26B7','RC40L','H28','U55','D01','D02','D02_M','D02_M150','D02_P'])
    def test_two_separate_experiments_fifteen_runs(self):
        self.assertEqual(len(self.spec['experiments']),2)
        self.assertEqual(sum(len(g['cars']) for g in self.spec['experiments']),15)
        self.assertEqual(self.spec['experiments'][1]['cars'],['R00','U55'])
    def test_no_course_or_tune_sweep(self):
        for file in final_files(ROOT):
            for node in ast.walk(ast.parse(file.read_text())):
                if isinstance(node,ast.ImportFrom):self.assertFalse((node.module or '').startswith('exploration'))
    def test_mechanical_kernel_promoted_without_change(self):
        from infrastructure.common import sha_file
        record=load_json(ROOT/'provenance/inherited_implementation.json')['identical_files']
        for name in ('infrastructure/course.py','infrastructure/model.py','infrastructure/diagnostics.py','experiments/fleet.py','analysis/metrics.py'):
            self.assertEqual(sha_file(ROOT/name),record[name])
    def test_course_intervals(self):
        self.assertEqual(self.course.finish_m,732.)
        sectors={s.name:(s.start_m,s.end_m) for s in self.course.sectors}
        self.assertEqual(sectors['cyclic'],(264.,336.))
        self.assertEqual(sectors['secondary_hill_hold'],(356.,596.))
        self.assertEqual(sectors['descent_hold'],(636.,696.))
    def test_six_cycles_four_untapered(self):
        self.assertEqual(self.course.count,6)
        env=self.course.config['cyclic_envelope_length_m'];w=self.course.wavelength
        self.assertEqual(sum(k*w>=env and (k+1)*w<=6*w-env for k in range(6)),4)
    def test_flat_independent(self):
        c=Course(load_json(ROOT/'inputs/flat_800m.json'))
        self.assertEqual(c.finish_m,800.)
        for x in np.linspace(0,800,501):self.assertEqual(c.grade_and_gradient(x),(0.,0.))
    def test_no_forced_target_state(self):
        s=self.spec['numerical_settings']
        self.assertEqual(s,{'relative_tolerance':3e-5,'absolute_tolerance':3e-8,'max_step_s':.005,'maximum_time_s':180.,'diagnostic_step_s':.005})
        self.assertEqual(self.spec['execution']['checkpoint_interval_s'],2.)
    def test_d02_repairs_and_overcorrection(self):
        by={t['id']:t['knobs'] for t in self.fleet}
        self.assertEqual(by['D02'],{'tip_mass_scale':.65,'primary_preload_scale':1.15})
        self.assertEqual(by['D02_M'],{'primary_preload_scale':1.15})
        self.assertEqual(by['D02_M150'],{'tip_mass_scale':1.5,'primary_preload_scale':1.15})
        self.assertEqual(by['D02_P'],{'tip_mass_scale':.65})
    def test_promoted_shape_cases(self):
        by={t['id']:t['knobs'] for t in self.fleet}
        self.assertEqual(by['P300'],{'primary_rate_scale':3.0})
        self.assertEqual(by['RC10']['ramp_end_deg'],10)
        self.assertEqual(by['R26B7']['ramp_end_deg'],26)
        self.assertEqual(by['R26B7']['ramp_blend_m'],.007)
        self.assertEqual(by['RC40L']['ramp_prefix_m'],.018)
    def test_edited_course_is_rejected(self):
        with TemporaryDirectory() as t:
            r=Path(t);shutil.copytree(ROOT/'inputs',r/'inputs');shutil.copy2(ROOT/'study.json',r/'study.json')
            c=load_json(r/'inputs/course.json');c['hill_angle_deg']=40.;write_json(r/'inputs/course.json',c)
            with self.assertRaisesRegex(ValueError,'selected input changed'):validate_selection(r,RELEASE_ROOT)
    def test_json_reformat_is_not_changed_physics(self):
        with TemporaryDirectory() as t:
            a,b=Path(t)/'a.json',Path(t)/'b.json'
            a.write_text('{"x": 1, "y": [2, 3]}');b.write_text('{\r\n "y":[2,3], "x":1\r\n}')
            self.assertEqual(canonical_file_hash(a),canonical_file_hash(b))


class ReuseTests(unittest.TestCase):
    def make_case(self,p):
        p.mkdir(parents=True)
        for name in ESSENTIAL_CASE_FILES:(p/name).write_text('fixture\n')
        write_json(p/'status.json',{'complete_output':True,'fingerprint':'known','status':'progress_limited'})
        seal_case(p,'known')
    def test_observed_nonfinish_can_be_complete(self):
        with TemporaryDirectory() as t:
            p=Path(t)/'D02';self.make_case(p);self.assertTrue(reusable_case(p,'known'))
    def test_wrong_fingerprint_rejected(self):
        with TemporaryDirectory() as t:
            p=Path(t)/'D02';self.make_case(p);self.assertFalse(reusable_case(p,'other'))
    def test_deleted_data_rejected(self):
        with TemporaryDirectory() as t:
            p=Path(t)/'D02';self.make_case(p);(p/'diagnostics.csv').unlink();self.assertFalse(reusable_case(p,'known'))
    def test_edited_data_rejected(self):
        with TemporaryDirectory() as t:
            p=Path(t)/'D02';self.make_case(p);(p/'events.csv').write_text('changed');self.assertFalse(reusable_case(p,'known'))
    def test_prior_attempt_preserved(self):
        with TemporaryDirectory() as t:
            root=Path(t);p=root/'unified_course/cases/D02';self.make_case(p)
            archive_attempt(p,root);self.assertFalse(p.exists())
            self.assertEqual(len(list((root/'previous_attempts').rglob('diagnostics.csv'))),1)
    def test_concurrent_output_lock_refused(self):
        with TemporaryDirectory() as t:
            p=Path(t)
            with output_lock(p):
                with self.assertRaises(RuntimeError):
                    with output_lock(p):pass
            self.assertFalse((p/'RUNNING.lock').exists())
    def test_lock_removed_on_exception(self):
        with TemporaryDirectory() as t:
            p=Path(t)
            with self.assertRaises(ValueError):
                with output_lock(p):raise ValueError('test')
            self.assertFalse((p/'RUNNING.lock').exists())
    def test_zip_keeps_current_results_not_old_attempts(self):
        with TemporaryDirectory() as t:
            p=Path(t)/'final';p.mkdir();write_json(p/'suite.json',{})
            (p/'index.html').write_text('report');(p/'RUNNING.lock').write_text('lock')
            (p/'previous_attempts').mkdir();(p/'previous_attempts/old.csv').write_text('old')
            z=pack_results(p)
            with ZipFile(z) as archive:
                names=archive.namelist()
                self.assertIn('final/index.html',names)
                self.assertFalse(any('previous_attempts' in n or 'RUNNING.lock' in n for n in names))
                self.assertIsNone(archive.testzip())

if __name__=='__main__':unittest.main()
