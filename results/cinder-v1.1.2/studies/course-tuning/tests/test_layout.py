"""Final execution is isolated from the explorations now housed in the same study."""
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest
ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
from infrastructure.common import source_fingerprint, final_files
from infrastructure.selection import snapshot_sources


def put(root, name, data='fixture'):
    path=root/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_text(data)
    return path


class LayoutTests(unittest.TestCase):
    def test_single_active_study_manifest(self):
        self.assertTrue((ROOT/'study.json').is_file())
        self.assertFalse((ROOT/'exploration/study.json').exists())
        if (ROOT/'exploration').exists():
            self.assertTrue((ROOT/'exploration/exploration.json').is_file())
    def test_exploratory_scripts_do_not_change_final_identity(self):
        with TemporaryDirectory() as d:
            r=Path(d);put(r,'run.py','x=1');put(r,'infrastructure/common.py','x=2')
            old=source_fingerprint(r)
            for name in ['exploration/run.py','exploration/scans/scan_courses.py',
                         'exploration/history/old/run.py','artifacts/provenance/study/run.py',
                         'provenance/layout_history/old/run.py','tools/migrate_layout.py']:
                put(r,name,'not an input to the final study')
            self.assertEqual(old,source_fingerprint(r))
    def test_final_runtime_edit_changes_identity(self):
        with TemporaryDirectory() as d:
            r=Path(d);put(r,'run.py','before');old=source_fingerprint(r)
            put(r,'run.py','after');self.assertNotEqual(old,source_fingerprint(r))
    def test_snapshot_excludes_history_and_exploration(self):
        with TemporaryDirectory() as d:
            r=Path(d)/'study';rel=Path(d)/'release';dest=Path(d)/'snapshot'
            for name in ['run.py','study.json','README.md','inputs/course.json',
                         'analysis/report.py','provenance/SOURCES.md']:
                put(r,name)
            for name in ['exploration/run.py','artifacts/old.csv',
                         'provenance/layout_history/old/run.py','provenance/migrations/log.json']:
                put(r,name,'must not appear')
            for name in ['__init__.py','reference_case.py','slotted_helix.py']:
                put(rel,'defaults/reference_model/'+name)
            put(rel,'defaults/reference_model/policy.json','{}')
            put(rel,'defaults/baja/simulation_case.json','{}')
            snapshot_sources(dest,root=r,release=rel)
            copied={p.relative_to(dest).as_posix() for p in dest.rglob('*') if p.is_file()}
            self.assertIn('study/run.py',copied)
            self.assertIn('study/inputs/course.json',copied)
            self.assertIn('shared_results/defaults/baja/simulation_case.json',copied)
            self.assertFalse(any('exploration' in p or 'layout_history' in p or 'migrations' in p or 'artifacts' in p for p in copied))
    def test_final_file_iterator_does_not_follow_symlinks(self):
        with TemporaryDirectory() as d:
            r=Path(d)/'study';other=Path(d)/'outside';put(other,'oops.py')
            (r/'analysis').mkdir(parents=True)
            (r/'analysis/link').symlink_to(other,target_is_directory=True)
            self.assertEqual(final_files(r),[])
    def test_exploration_config_resolves_shared_reference(self):
        import json
        if not (ROOT/'exploration/exploration.json').is_file():
            self.skipTest('Exploration is intentionally absent from final-source snapshots')
        spec=json.loads((ROOT/'exploration/exploration.json').read_text())
        p=(ROOT/'exploration'/spec['base_document']).resolve()
        self.assertEqual(p,(ROOT.parents[1]/'defaults/baja/simulation_case.json').resolve())

if __name__=='__main__':unittest.main()
