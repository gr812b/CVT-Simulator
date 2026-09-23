"""Regression checks for the specific event-side and sign risks in this figure.

Run after canonical run.py; retained evidence is required. These tests change
copies in memory and never modify raw artifacts or run simulator mechanics.
"""
import copy
import json
from pathlib import Path
import sys
import unittest

STUDY = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(STUDY))
from analysis.verification import read_rows, trace_checks


class EnergyEvidenceIntegrity(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        artifacts = STUDY / "artifacts"
        cls.trace = read_rows(artifacts / "energy_trace_finest.csv")
        cls.transitions = read_rows(artifacts / "native_transitions.csv")
        cls.events = read_rows(artifacts / "event_energy_balance.csv")
        cls.headline = json.loads((artifacts / "summary.json").read_text())["nominal_energy_balance"]
        trace_checks(cls.trace, cls.transitions, cls.events, cls.headline)

    def check_rejected(self, trace):
        with self.assertRaises(ValueError):
            trace_checks(trace, self.transitions, self.events, self.headline)

    def test_dropped_incoming_endpoint_is_rejected(self):
        event = self.events[0]
        trace = [r for r in self.trace
                 if not (r["segment_index"] == event["transition_index"]
                         and r["sample_location"] == "segment_end")]
        self.check_rejected(trace)

    def test_absolute_value_residual_is_rejected(self):
        trace = copy.deepcopy(self.trace)
        for row in trace:
            row["balance_residual_J"] = abs(row["balance_residual_J"])
        self.check_rejected(trace)

    def test_capture_counted_on_incoming_side_is_rejected(self):
        trace = copy.deepcopy(self.trace)
        event = self.events[0]
        row = next(r for r in trace if r["segment_index"] == event["transition_index"]
                   and r["sample_location"] == "segment_end")
        loss = event["recorded_impact_loss_J"]
        # Preserve the row's algebraic identity: the event-side check must
        # still reject this premature physical loss assignment.
        row["impact_capture_dissipation_J"] += loss
        row["accounted_energy_J"] += loss
        row["balance_residual_J"] -= loss
        self.check_rejected(trace)


if __name__ == "__main__":
    unittest.main()
