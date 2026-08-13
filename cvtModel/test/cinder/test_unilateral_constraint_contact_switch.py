from __future__ import annotations

from types import SimpleNamespace

import numpy as np

from cinder.execution.hybrid import cvt_regime_switching
from cinder.execution.hybrid.cvt_regime import CVTShiftConstraint
from cinder.model.cvt.contact import ContactRegime


class _ReactionEvaluator:
    def __init__(self, *, low_ratio: float | None = None, upper: float | None = None):
        self.low_ratio = low_ratio
        self.upper = upper

    def evaluate_vector(self, **_kwargs):
        return SimpleNamespace(
            low_ratio_seat_reaction=self.low_ratio,
            upper_stop_reaction=self.upper,
        )


def test_contact_switch_releases_low_ratio_seat_when_successor_reaction_is_tensile() -> None:
    contact = ContactRegime.stick_stick()
    result = cvt_regime_switching._constraint_release_after_contact_transition(
        time=0.0,
        vector=np.zeros(5, dtype=float),
        shift_constraint=CVTShiftConstraint.LOW_RATIO_SEAT,
        contact_regime=contact,
        evaluator=_ReactionEvaluator(low_ratio=-1.0),
    )

    assert result is not None
    mode, reason, reaction_name, reaction = result
    assert mode.shift_constraint is CVTShiftConstraint.FREE
    assert mode.contact_regime == contact
    assert reason == "contact_transition_released_low_ratio_seat_by_tensile_reaction"
    assert reaction_name == "low_ratio_seat_reaction"
    assert reaction == -1.0


def test_contact_switch_keeps_low_ratio_seat_when_successor_reaction_can_push() -> None:
    result = cvt_regime_switching._constraint_release_after_contact_transition(
        time=0.0,
        vector=np.zeros(5, dtype=float),
        shift_constraint=CVTShiftConstraint.LOW_RATIO_SEAT,
        contact_regime=ContactRegime.stick_stick(),
        evaluator=_ReactionEvaluator(low_ratio=1.0),
    )
    assert result is None


def test_contact_switch_releases_upper_stop_when_successor_reaction_is_tensile() -> None:
    contact = ContactRegime.stick_stick()
    result = cvt_regime_switching._constraint_release_after_contact_transition(
        time=0.0,
        vector=np.zeros(5, dtype=float),
        shift_constraint=CVTShiftConstraint.UPPER_STOP,
        contact_regime=contact,
        evaluator=_ReactionEvaluator(upper=-2.0),
    )

    assert result is not None
    mode, reason, reaction_name, reaction = result
    assert mode.shift_constraint is CVTShiftConstraint.FREE
    assert mode.contact_regime == contact
    assert reason == "contact_transition_released_upper_stop_by_tensile_reaction"
    assert reaction_name == "upper_stop_reaction"
    assert reaction == -2.0
