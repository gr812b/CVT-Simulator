from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest
ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
from infrastructure.paths import saved_campaign_path
from infrastructure.common import source_fingerprint


def put(root,name,text='{}'):
    p=root/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_text(text);return p


class RelocationTests(unittest.TestCase):
    def test_absolute_macos_path_resolves_from_moved_plan(self):
        with TemporaryDirectory() as d:
            r=Path(d)/'artifacts';put(r,'campaign/campaign.json')
            plan=put(r,'feature_explorations/a/plan.json')
            target=saved_campaign_path('/Users/kai/repo/studies/course-tuning-exploration/artifacts/campaign',plan)
            self.assertEqual(target,r/'campaign')
    def test_windows_path_resolves_from_import_container(self):
        with TemporaryDirectory() as d:
            r=Path(d)/'artifacts/imported_old';put(r,'campaign/campaign.json')
            plan=put(r,'feature_explorations/a/plan.json')
            target=saved_campaign_path(r'C:\repo\studies\course-tuning-exploration\artifacts\campaign',plan)
            self.assertEqual(target,r/'campaign')
    def test_bad_relative_traversal_rejected(self):
        with TemporaryDirectory() as d:
            with self.assertRaises(ValueError):saved_campaign_path('/old/artifacts/../../outside',Path(d)/'plan.json')
    def test_missing_path_remains_missing(self):
        with TemporaryDirectory() as d:
            target=saved_campaign_path('/old/artifacts/not-present',Path(d)/'plan.json')
            self.assertFalse(target.exists())
    def test_source_identity_excludes_history(self):
        # Archives cannot change identity. A fixture file is removed immediately.
        old=source_fingerprint()
        p=ROOT/'history/test-isolation/oops.py';p.parent.mkdir(parents=True,exist_ok=True)
        try:
            p.write_text('# archived')
            self.assertEqual(old,source_fingerprint())
        finally:
            p.unlink();p.parent.rmdir()

if __name__=='__main__':unittest.main()
