from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
EXPERIMENTS = ROOT / "experiments"
for path in (ROOT, EXPERIMENTS):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

import run_paired_helix_performance as e58


def _row(t, margin, stick=True):
    return {
        'time_s': t,
        'e58_helix_actual_margin_Nm': margin,
        'e58_stick_stick': stick,
    }


def test_first_zero_crossing_interpolates():
    rows = [_row(0.0, 2.0), _row(0.1, 1.0), _row(0.2, -1.0)]
    t = e58._first_zero_crossing(rows, 'e58_helix_actual_margin_Nm', onset_s=0.05)
    assert abs(t - 0.15) < 1e-12


def test_slip_duration_counts_nonstick_intervals():
    rows = [
        _row(0.0, 1.0, True),
        _row(0.1, 1.0, True),
        _row(0.2, 1.0, False),
        _row(0.3, 1.0, False),
        _row(0.4, 1.0, True),
    ]
    assert abs(e58._slip_duration(rows, onset_s=0.0) - 0.2) < 1e-12
