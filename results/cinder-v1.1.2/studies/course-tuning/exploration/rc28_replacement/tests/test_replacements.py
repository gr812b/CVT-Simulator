from __future__ import annotations
import json
from pathlib import Path
import unittest
ROOT=Path(__file__).resolve().parents[2]
CANDIDATES=ROOT/'inputs/rc28_replacement_candidates.json'

class ReplacementDefinitionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.doc=json.loads(CANDIDATES.read_text(encoding='utf-8'));cls.fleet=cls.doc['competitors']
    def test_unique_ids(self):
        ids=[x['id'] for x in self.fleet];self.assertEqual(len(ids),len(set(ids)))
    def test_reference_and_rejection_control(self):
        by={x['id']:x for x in self.fleet}
        self.assertEqual(by['R00']['knobs'],{})
        self.assertTrue(by['RC28X']['expected_preflight_rejection'])
        self.assertEqual(by['RC28X']['knobs'],{'ramp_end_deg':28,'ramp_prefix_m':.01,'ramp_blend_m':.005,'ramp_tail_kind':'arc'})
    def test_replacements_are_only_ramp_geometry(self):
        for t in self.fleet:
            if t['id'] in ('R00','RC28X'):continue
            self.assertEqual(set(t['knobs']),{'ramp_end_deg','ramp_prefix_m','ramp_blend_m','ramp_tail_kind'})
            self.assertEqual(t['knobs']['ramp_tail_kind'],'arc')
            self.assertGreaterEqual(t['knobs']['ramp_end_deg'],22)
            self.assertLessEqual(t['knobs']['ramp_end_deg'],28)
            self.assertGreaterEqual(t['knobs']['ramp_blend_m'],.007)
    def test_search_is_narrow(self):
        replacement=[t for t in self.fleet if t['id'] not in ('R00','RC28X')]
        self.assertEqual(len(replacement),14)
        self.assertEqual(self.doc['id'],'rc28_replacement_v1')

if __name__=='__main__':unittest.main()
