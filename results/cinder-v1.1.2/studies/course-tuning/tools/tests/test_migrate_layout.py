"""Filesystem migration tests; synthetic fixtures require no CINDER installation."""
import importlib.util
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[2]
spec=importlib.util.spec_from_file_location('migrate_course_layout',ROOT/'tools/migrate_layout.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)


def put(root,name,data='fixture'):
    p=root/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_text(data)
    return p


def fixture(t,both=True):
    studies=Path(t)/'studies';root=studies/'course-tuning'
    put(root,'study.json','{"study_slug":"course-tuning"}')
    names=m.LEGACY if both else m.LEGACY[:1]
    for name in names:
        old=studies/name
        put(old,'run.py',f'# original edited {name}\n')
        put(old,'artifacts/campaign/index.html','<a href="cases/R00/data.csv">data</a>')
        put(old,'artifacts/campaign/cases/R00/data.csv','x,y\n1,2\n')
        put(old,'artifacts/portable.zip','zip content')
        (old/'empty').mkdir()
    return root


class MigrationTests(unittest.TestCase):
    def test_preview_changes_nothing(self):
        with TemporaryDirectory() as t:
            root=fixture(t);before=sorted(str(p) for p in Path(t).rglob('*'))
            plan=m.plan_migration(root,tag='test')
            self.assertEqual(len(plan['entries']),2)
            self.assertEqual(before,sorted(str(p) for p in Path(t).rglob('*')))
    def test_move_both_preserves_files_empty_directories_and_modifications(self):
        with TemporaryDirectory() as t:
            root=fixture(t);plan=m.plan_migration(root,tag='test');result=m.apply_migration(plan)
            self.assertEqual(result['status'],'complete');self.assertEqual(result['verified_file_count'],8)
            for e in result['entries']:
                self.assertFalse(Path(e['source']).exists())
                self.assertTrue((Path(e['archive'])/'empty').is_dir())
                for relative,v in e['original_inventory']['files'].items():
                    self.assertEqual(m.file_hash(m.relocated_path(e,relative)),v['sha256'])
            self.assertTrue((root/'exploration/artifacts/campaign/index.html').is_file())
            self.assertTrue((root/'artifacts/campaign/index.html').is_file())
    def test_existing_artifacts_never_overwritten(self):
        with TemporaryDirectory() as t:
            root=fixture(t);put(root,'exploration/artifacts/campaign/index.html','KEEP')
            plan=m.plan_migration(root,tag='test');m.apply_migration(plan)
            self.assertEqual((root/'exploration/artifacts/campaign/index.html').read_text(),'KEEP')
            self.assertEqual((root/'exploration/artifacts/imported_course-tuning-exploration_test/campaign/index.html').read_text(),'<a href="cases/R00/data.csv">data</a>')
    def test_repeated_migration_is_noop(self):
        with TemporaryDirectory() as t:
            root=fixture(t);m.apply_migration(m.plan_migration(root))
            again=m.plan_migration(root)
            self.assertEqual(again['entries'],[])
            self.assertEqual(m.apply_migration(again)['status'],'nothing_to_move')
    def test_new_install_has_no_migration_work(self):
        with TemporaryDirectory() as t:
            root=Path(t)/'studies/course-tuning';put(root,'study.json','{"study_slug":"course-tuning"}')
            self.assertEqual(m.plan_migration(root)['entries'],[])
    def test_source_without_artifacts_is_preserved(self):
        with TemporaryDirectory() as t:
            root=Path(t)/'studies/course-tuning';put(root,'study.json','{"study_slug":"course-tuning"}')
            put(root.parent/'course-tuning-exploration','notes.md','user notes')
            plan=m.plan_migration(root);self.assertIsNone(plan['entries'][0]['artifact_destination'])
            log=m.apply_migration(plan);self.assertEqual(log['verified_file_count'],1)
    def test_lock_prevents_all_source_moves(self):
        with TemporaryDirectory() as t:
            root=fixture(t);old=root.parent/'course-tuning-final';put(old,'artifacts/campaign/RUNNING.lock','running')
            with self.assertRaisesRegex(RuntimeError,'Lock found'):m.apply_migration(m.plan_migration(root))
            self.assertTrue((root.parent/'course-tuning-exploration/run.py').is_file())
            self.assertTrue((old/'run.py').is_file())
    def test_selection_lock_json_is_not_a_live_lock(self):
        with TemporaryDirectory() as t:
            root=fixture(t);put(root.parent/'course-tuning-final','inputs/selection.lock.json','{}')
            self.assertEqual(m.apply_migration(m.plan_migration(root))['status'],'complete')
    def test_inner_symlink_refused(self):
        with TemporaryDirectory() as t:
            root=fixture(t);old=root.parent/'course-tuning-exploration'
            (old/'link').symlink_to(old/'run.py')
            with self.assertRaisesRegex(RuntimeError,'Symlink found'):m.apply_migration(m.plan_migration(root))
            self.assertTrue((old/'run.py').exists())
    def test_legacy_root_symlink_refused(self):
        with TemporaryDirectory() as t:
            root=Path(t)/'studies/course-tuning';put(root,'study.json','{"study_slug":"course-tuning"}')
            outside=Path(t)/'outside';outside.mkdir()
            (root.parent/'course-tuning-exploration').symlink_to(outside,target_is_directory=True)
            with self.assertRaisesRegex(RuntimeError,'symlinked legacy'):m.plan_migration(root)
    def test_caught_failure_rolls_back_all_moves(self):
        with TemporaryDirectory() as t:
            root=fixture(t);before={n:m.inventory(root.parent/n) for n in m.LEGACY}
            real=m._rename;count=0
            def fail_fourth(source,dest):
                nonlocal count
                count+=1
                if count==4:raise OSError('injected move failure')
                real(source,dest)
            with patch.object(m,'_rename',side_effect=fail_fourth):
                with self.assertRaisesRegex(OSError,'injected'):m.apply_migration(m.plan_migration(root))
            for n in m.LEGACY:self.assertEqual(m.inventory(root.parent/n),before[n])
            self.assertFalse((root/'MIGRATING.lock').exists())
    def test_non_consolidated_destination_refused(self):
        with TemporaryDirectory() as t:
            root=Path(t)/'studies/course-tuning';put(root,'study.json','{"study_slug":"other"}')
            with self.assertRaisesRegex(RuntimeError,'Extract'):m.plan_migration(root)
    def test_navigation_contains_real_relative_links(self):
        from html.parser import HTMLParser
        from urllib.parse import unquote
        class Links(HTMLParser):
            def __init__(self):super().__init__();self.links=[]
            def handle_starttag(self,tag,attrs):
                if tag=='a':self.links += [v for k,v in attrs if k=='href']
        with TemporaryDirectory() as t:
            root=fixture(t);m.apply_migration(m.plan_migration(root))
            p=m.build_index(root);parsed=Links();parsed.feed(p.read_text())
            self.assertGreaterEqual(len(parsed.links),3)
            self.assertTrue(all((root/unquote(link)).is_file() for link in parsed.links))
    def test_destination_created_after_plan_causes_no_moves(self):
        with TemporaryDirectory() as t:
            root=fixture(t);plan=m.plan_migration(root)
            Path(plan['entries'][0]['artifact_destination']).mkdir(parents=True)
            with self.assertRaises(FileExistsError):m.apply_migration(plan)
            self.assertTrue((root.parent/m.LEGACY[0]/'run.py').is_file())

if __name__=='__main__':unittest.main()
