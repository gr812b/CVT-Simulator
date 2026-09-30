"""Preparation regressions. Synthetic records, except one installed-law identity.

No transient is integrated. The installed-law test skips outside CINDER 1.1.2.
"""
from __future__ import annotations
import csv
import hashlib
import importlib.util
import io
import json
import math
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

RELEASE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RELEASE))
import numpy as np
from results_health.common import MissingEvidence, digest, read_json, write_json
from results_health.prep_support import (
    PRIMARY_FORCE_COMPONENTS, portable_key, portable_hashes, path_below,
    lfs_pointer, require_data, materialize_asset, validate_primary_screen,
    recover_course_mechanism_margins, recovery_summary, moving_source_hashes,
    verify_saved_subtree, resolve_saved_suite, prepare_course_bundle)
from results_health.guards import course_row_failures, course_endpoint_audit


def pointer_bytes(data):
    oid = hashlib.sha256(data).hexdigest()
    return f'version https://git-lfs.github.com/spec/v1\noid sha256:{oid}\nsize {len(data)}\n'.encode()


def screen_file(path):
    with path.open('w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=['status', 'response_class', 'peak_dynamic_number',
                                        'restart_target_shift_percent', 'ramp_s'])
        w.writeheader()
        for shift in (20., 50., 80.):
            for ramp in (.005, .02, .1, .25):
                for _ in range(6):
                    w.writerow(dict(status='completed', response_class='clean_continuous',
                                    peak_dynamic_number=.001, restart_target_shift_percent=shift, ramp_s=ramp))


def deadzone_row():
    return {'time_s': 0., 'segment_id': 0, 'sample_location': 'start',
            'engagement': 'deadzone', 'shift_constraint': 'free', 'inspection_error': '',
            'mechanism_margin.primary/0:FixedPivotFlyweightForce': '',
            **dict(zip(PRIMARY_FORCE_COMPONENTS, ('100', '-20', '-5')))}


class PortableTests(unittest.TestCase):
    def test_windows_and_posix_keys_are_the_same_identity(self):
        self.assertEqual(portable_hashes({'a\\b.csv': 'x'}), {'a/b.csv': 'x'})

    def test_matching_duplicate_allowed(self):
        self.assertEqual(portable_hashes({'a\\b': 'x', 'a/b': 'x'}), {'a/b': 'x'})

    def test_conflicting_duplicate_rejected(self):
        with self.assertRaises(ValueError): portable_hashes({'a\\b': 'x', 'a/b': 'y'})

    def test_no_traversal(self):
        for name in ('../x', 'a/../x', r'a\..\x', '/root/x', r'C:\x', '', '.', 'x\x00y'):
            with self.subTest(name=name), self.assertRaises(ValueError): portable_key(name)

    def test_resolved_symlink_cannot_escape(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)/'root'; root.mkdir(); outside = Path(d)/'outside'; outside.mkdir()
            try: (root/'link').symlink_to(outside, target_is_directory=True)
            except OSError: self.skipTest('Symlink creation not permitted on this account')
            with self.assertRaises(ValueError): path_below(root, 'link/x')

    def test_moving_source_normalizes_read_manifest(self):
        self.assertEqual(moving_source_hashes({'raw_sha256': {r'unloading_nominal_full\terms.csv.gz': 'hash'}}),
                         {'unloading_nominal_full/terms.csv.gz': 'hash'})


class LfsTests(unittest.TestCase):
    def test_pointer_is_not_csv_data(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d)/'data.csv'; p.write_bytes(pointer_bytes(b'actual csv'))
            self.assertEqual(lfs_pointer(p)['bytes'], 10)
            with self.assertRaises(MissingEvidence): require_data(p)

    def test_missing_file_is_missing_not_empty_data(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(MissingEvidence): require_data(Path(d)/'absent')

    def test_normal_small_data_not_pointer(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d)/'data.csv'; p.write_text('a,b\n1,2\n')
            self.assertIsNone(lfs_pointer(p))

    def test_malformed_pointer_fails(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d)/'data.csv'; p.write_text('version https://git-lfs.github.com/spec/v1\noid invalid\n')
            with self.assertRaises(ValueError): lfs_pointer(p)

    def test_local_object_recovery_does_not_modify_tracked_pointer(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d); source = root/'data.csv'; data = b'a,b\n1,2\n'
            source.write_bytes(pointer_bytes(data)); before = source.read_bytes()
            oid = hashlib.sha256(data).hexdigest(); store = root/'.git/lfs/objects'
            obj = store/oid[:2]/oid[2:4]/oid; obj.parent.mkdir(parents=True); obj.write_bytes(data)
            with patch('results_health.prep_support.git', return_value='.git/lfs/objects') as git:
                result = materialize_asset(source, root/'out/data.csv', root)
            self.assertEqual(git.call_count, 1)
            self.assertEqual(source.read_bytes(), before)
            self.assertEqual((root/'out/data.csv').read_bytes(), data)
            self.assertFalse(result['working_tree_modified'])

    def test_no_network_without_explicit_fetch(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d); source = root/'data.csv'; source.write_bytes(pointer_bytes(b'hello'))
            with patch('results_health.prep_support.git', return_value='.git/lfs/objects') as git:
                with self.assertRaises(MissingEvidence): materialize_asset(source, root/'out.csv', root)
            self.assertEqual(git.call_count, 1)

    def test_explicit_fetch_targets_one_file(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d); source = root/'data.csv'; data = b'hello'; source.write_bytes(pointer_bytes(data))
            oid = hashlib.sha256(data).hexdigest(); obj = root/'.git/lfs/objects'/oid[:2]/oid[2:4]/oid
            calls = []
            def fake(repo, arguments):
                calls.append(arguments)
                if arguments == ['rev-parse', '--git-path', 'lfs/objects']: return '.git/lfs/objects'
                if arguments == ['rev-parse', 'HEAD']: return 'commit'
                obj.parent.mkdir(parents=True); obj.write_bytes(data); return 'downloaded'
            with patch('results_health.prep_support.git', side_effect=fake):
                materialize_asset(source, root/'out.csv', root, fetch=True)
            self.assertEqual(calls[-1], ['lfs', 'fetch', '--include=data.csv', '--exclude=', 'origin', 'commit'])
            self.assertFalse(any('checkout' in a for a in calls))

    def test_corrupt_lfs_object_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d); source = root/'data.csv'; data = b'hello'; source.write_bytes(pointer_bytes(data))
            oid = hashlib.sha256(data).hexdigest(); obj = root/'.git/lfs/objects'/oid[:2]/oid[2:4]/oid
            obj.parent.mkdir(parents=True); obj.write_bytes(b'wrong')
            with patch('results_health.prep_support.git', return_value='.git/lfs/objects'):
                with self.assertRaises(ValueError): materialize_asset(source, root/'out.csv', root)

    def test_existing_other_prepared_data_not_overwritten(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d); source = root/'a'; source.write_text('new'); target = root/'b'; target.write_text('old')
            with self.assertRaises(FileExistsError): materialize_asset(source, target, root)
            self.assertEqual(target.read_text(), 'old')

    def test_screen_retains_grid(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d)/'screen.csv'; screen_file(p)
            self.assertEqual(len(validate_primary_screen(p, expected_sha=None)), 72)

    def test_screen_checksum_required(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d)/'screen.csv'; screen_file(p)
            with self.assertRaises(ValueError): validate_primary_screen(p)

    def test_incomplete_screen_not_silently_omitted(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d)/'screen.csv'; screen_file(p)
            p.write_text(p.read_text().replace('completed', 'failed', 1))
            with self.assertRaises(ValueError): validate_primary_screen(p, expected_sha=None)

    def test_missing_screen_rows_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d)/'screen.csv'; screen_file(p)
            p.write_text('\n'.join(p.read_text().splitlines()[:-1])+'\n')
            with self.assertRaises(ValueError): validate_primary_screen(p, expected_sha=None)


class CourseMarginTests(unittest.TestCase):
    def test_deadzone_blank_reconstructed_without_mutation(self):
        row = deadzone_row(); original = dict(row)
        fixed, notes = recover_course_mechanism_margins(row)
        self.assertEqual(fixed['mechanism_margin.primary/0:FixedPivotFlyweightForce'], 75.)
        self.assertEqual(row, original); self.assertEqual(len(notes), 1)
        self.assertEqual(course_row_failures(row), [])

    def test_negative_reconstructed_margin_still_fails(self):
        row = deadzone_row(); row[PRIMARY_FORCE_COMPONENTS[0]] = '-100'
        self.assertTrue(any('negative_mechanism_margin' in x for x in course_row_failures(row)))

    def test_finite_recorded_margin_not_overwritten(self):
        row = deadzone_row(); row['mechanism_margin.primary/0:FixedPivotFlyweightForce'] = '-2'
        fixed, notes = recover_course_mechanism_margins(row)
        self.assertEqual(fixed['mechanism_margin.primary/0:FixedPivotFlyweightForce'], '-2')
        self.assertEqual(notes, []); self.assertTrue(course_row_failures(row))

    def test_nan_and_infinity_not_excused(self):
        for raw in ('nan', 'inf', '-inf', float('nan')):
            row = deadzone_row(); row['mechanism_margin.primary/0:FixedPivotFlyweightForce'] = raw
            self.assertTrue(course_row_failures(row))

    def test_missing_force_component_does_not_pass(self):
        row = deadzone_row(); row.pop(PRIMARY_FORCE_COMPONENTS[1]); self.assertTrue(course_row_failures(row))

    def test_nonfinite_force_component_does_not_pass(self):
        row = deadzone_row(); row[PRIMARY_FORCE_COMPONENTS[1]] = 'nan'; self.assertTrue(course_row_failures(row))

    def test_engaged_missing_margin_not_excused(self):
        row = deadzone_row(); row['engagement'] = 'engaged'
        fixed, notes = recover_course_mechanism_margins(row)
        self.assertEqual(notes, []); self.assertEqual(fixed, row)
        self.assertTrue(any('nonfinite_mechanism_margin' in f for f in course_row_failures(row)))

    def test_other_mechanism_missing_margin_still_fails(self):
        row = deadzone_row(); row['mechanism_margin.secondary/0:OtherForce'] = ''
        self.assertIn('nonfinite_mechanism_margin.secondary/0:OtherForce', course_row_failures(row))

    def test_inspection_error_not_repaired_away(self):
        row = deadzone_row(); row['inspection_error'] = 'failed'
        self.assertEqual(course_row_failures(row), ['inspection_error'])

    def test_all_event_sides_remain_reviewed(self):
        rows = [deadzone_row(), {**deadzone_row(), 'sample_location':'end', 'time_s': .01}]
        audit = course_endpoint_audit(rows)
        self.assertFalse(audit['event_endpoints_excluded']); self.assertEqual(audit['checked_rows'], 2)
        self.assertEqual(audit['mechanism_margin_recovery']['reconstructed_margin_count'], 2)
        self.assertFalse(audit['mechanism_margin_recovery']['raw_diagnostics_rewritten'])

    @unittest.skipUnless(importlib.util.find_spec('cinder') is not None, 'Requires installed CINDER; no integration')
    def test_exported_components_equal_installed_law_margin(self):
        from cinder.model.cvt.actuation import FixedPivotFlyweightForce
        from cinder.model.cvt.closure import AffineClosureScalar, ClosureUnknowns
        law = object.__new__(FixedPivotFlyweightForce)
        sample = SimpleNamespace(pivot_inertia=.3, angle_gradient=2., angle_curvature=-.4, shaft_inertia_gradient=.6)
        law._spec = SimpleNamespace(mechanism_map=SimpleNamespace(evaluate=lambda x: sample))
        z = ClosureUnknowns.from_components(primary_angular_acceleration=0., secondary_angular_acceleration=0.,
            belt_acceleration=0., shift_acceleration=0., primary_torque=0., secondary_torque=0.)
        for acceleration in (-100., 0., 500.):
            ctx = SimpleNamespace(axial_position=.1, axial_speed=.5, shaft_speed=10.,
                                  axial_acceleration=AffineClosureScalar.constant(acceleration))
            terms = {'primary.'+t.key+'_N': t.relation.evaluate(z) for t in law.inspect(ctx)}
            row = {**deadzone_row(), **terms}
            fixed, _ = recover_course_mechanism_margins(row)
            expected = law.compressive_contact_margin(context=ctx, unknowns=z)
            self.assertAlmostEqual(fixed['mechanism_margin.primary/0:FixedPivotFlyweightForce'], expected, places=10)


class RetainedTests(unittest.TestCase):
    def fixture(self, root, status='PASS'):
        raw = root/'data/primary/baseline/x.csv'; raw.parent.mkdir(parents=True); raw.write_text('original')
        old = r'F:\Code\CVT\health_runs\old_run'
        write_json(root/'health_report.json', {'output': old, 'source_identity':'original_generator', 'git_head':'old_commit',
            'steps':[{'id':'primary-baseline', 'status':status, 'output_sha256':{old+r'\data\primary\baseline\x.csv':digest(raw)}}]})
        return raw

    def test_windows_archive_identity_preserved_when_moved(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d); self.fixture(root)
            result=verify_saved_subtree(root,'data/primary',required_prefix='primary-')
            self.assertEqual(result['verified_files'],1)
            self.assertEqual(result['original_run_source_identity'],'original_generator')

    def test_tampered_original_output_fails(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d); raw=self.fixture(root); raw.write_text('altered')
            with self.assertRaises(ValueError):verify_saved_subtree(root,'data/primary')

    def test_failed_generation_cannot_be_promoted(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d); self.fixture(root,'FAIL')
            with self.assertRaises(ValueError):verify_saved_subtree(root,'data/primary')

    def test_absent_raw_file_is_missing(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d); self.fixture(root).unlink()
            with self.assertRaises(MissingEvidence):verify_saved_subtree(root,'data/primary')

    def test_missing_producer_inventory_is_not_a_pass(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d); self.fixture(root)
            with self.assertRaises(MissingEvidence):verify_saved_subtree(root,'data/secondary')

    def test_selected_course_pointer_rebases_exact_directory(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d); self.fixture(root)
            course=root/'data/course/final_v3_exact'; course.mkdir(parents=True)
            write_json(course/'suite.json',{'test':True})
            (course.parent/'latest_final.txt').write_text(r'F:\Code\CVT\health_runs\old_run\data\course\final_v3_exact')
            self.assertEqual(resolve_saved_suite(root),course)


class CourseBundleTests(unittest.TestCase):
    def fixture(self, root):
        suite=root/'suite'; case=suite/'course/cases/R00'; case.mkdir(parents=True)
        write_json(suite/'suite.json',{'expected_cases':['course/R00']})
        text='time_s,segment_id,speed_m_s,regime,optional\n0,0,0,deadzone,\n1,0,2,stick,\n1,1,2,slip,\n2,1,-1,slip,\n'
        (case/'diagnostics.csv').write_text(text)
        for name in ('resolved_case.json','model_identity.json','events.json','summary.json'):
            write_json(case/name,{'fixture':True})
        for name in ('segments.csv','mechanism_map.csv','ramp_profile.csv','shape_mechanism_map.csv'):
            (case/name).write_text('a\n1\n')
        audit=root/'audit.json'
        write_json(audit,{'passed':True,'suite_sha256':digest(suite/'suite.json'),
            'cases':{'course/R00':{'input_sha256':{name:digest(case/name) for name in
                ('diagnostics.csv','events.json','summary.json','resolved_case.json')}}}})
        return suite,case,audit

    def test_unfiltered_history_event_duplicates_and_rollback_preserved(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d); suite,case,audit=self.fixture(root)
            result=prepare_course_bundle(suite,root/'out',audit)
            with np.load(root/'out/course_plot_inputs.npz',allow_pickle=False) as z:
                np.testing.assert_array_equal(z['case_00__time_s'],[0,1,1,2])
                np.testing.assert_array_equal(z['case_00__speed_m_s'],[0,2,2,-1])
                self.assertEqual(z['case_00__regime'].tolist(),['deadzone','stick','slip','slip'])
                self.assertTrue(z['case_00__missing__optional'].all())
            self.assertFalse(result['smoothing_or_resampling'])
            self.assertEqual(result['cases']['course/R00']['duplicate_time_pairs'],1)

    def test_source_changed_after_audit_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d); suite,case,audit=self.fixture(root)
            (case/'diagnostics.csv').write_text('time_s\n0\n')
            with self.assertRaises(ValueError):prepare_course_bundle(suite,root/'out',audit)

    def test_failed_audit_not_published(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d); suite,case,audit=self.fixture(root)
            data=read_json(audit);data['passed']=False;write_json(audit,data)
            with self.assertRaises(ValueError):prepare_course_bundle(suite,root/'out',audit)

    def test_bundle_files_and_audit_hashes_valid(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d); suite,case,audit=self.fixture(root)
            result=prepare_course_bundle(suite,root/'out',audit)
            for name,value in result['files'].items():self.assertEqual(digest(root/'out'/name),value)
            self.assertEqual(result['health_audit_sha256'],digest(root/'out/course_health_audit.json'))


if __name__=='__main__':unittest.main()
