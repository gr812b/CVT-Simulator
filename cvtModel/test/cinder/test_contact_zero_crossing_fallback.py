"""Regression coverage for the zero-slip Coulomb mode-graph fallback."""

from __future__ import annotations

from types import SimpleNamespace

import numpy as np

from cinder.execution.hybrid.cvt_contact_events import CVTContactEvent
from cinder.execution.hybrid.cvt_contact_switching import (
    CVTEventSwitchingTolerances,
    resolve_cvt_contact_transition,
)
from cinder.model.cvt.contact import (
    ContactInterface,
    ContactRegime,
    EngagedContactMode,
    SlipDirection,
)
from cinder.model.cvt.dynamics.shift_constraints import EngagedShiftConstraint


class _RelativeMotion:
    def __init__(self, regime: ContactRegime, *, kinetic_outgoing: bool) -> None:
        self._regime = regime
        self._kinetic_outgoing = kinetic_outgoing

    def relative_speed_at(self, interface: ContactInterface) -> float:
        del interface
        return 0.0

    def relative_acceleration_at(self, interface: ContactInterface) -> float:
        if interface not in self._regime.mode.slipping_interfaces:
            return 0.0
        direction = self._regime.slip_direction_at(interface)
        sign = 1.0 if direction is SlipDirection.BELT_LEADS_PULLEY else -1.0
        if self._kinetic_outgoing and direction is SlipDirection.BELT_LEADS_PULLEY:
            return sign
        return -sign


class _Evaluation:
    def __init__(
        self, regime: ContactRegime, *, stick_margin: float, kinetic_outgoing: bool
    ) -> None:
        self.regime = regime
        self.normal_primary = 1000.0
        self.normal_secondary = 1000.0
        self.relative_motion = _RelativeMotion(
            regime, kinetic_outgoing=kinetic_outgoing
        )
        self._stick_margin = stick_margin

    def sticks_are_admissible(self, *, traction_law, required_margin: float) -> bool:
        del traction_law
        return self._stick_margin >= required_margin

    def slipped_directions_are_consistent(self) -> bool:
        return True


class _Evaluator:
    def __init__(self, *, stick_margin: float, kinetic_outgoing: bool) -> None:
        self.traction_law = object()
        self.solve_settings = SimpleNamespace(
            contact_tolerances=SimpleNamespace(
                relative_speed_tolerance=1.0e-7,
                relative_acceleration_tolerance=1.0e-8,
            )
        )
        self._stick_margin = stick_margin
        self._kinetic_outgoing = kinetic_outgoing

    def evaluate_vector(self, *, regime: ContactRegime, **kwargs):
        del kwargs
        return _Evaluation(
            regime,
            stick_margin=self._stick_margin,
            kinetic_outgoing=self._kinetic_outgoing,
        )


def _transition(*, stick_margin: float, kinetic_outgoing: bool):
    evaluator = _Evaluator(stick_margin=stick_margin, kinetic_outgoing=kinetic_outgoing)
    return resolve_cvt_contact_transition(
        evaluator=evaluator,
        time=1.0,
        vector=np.zeros(5, dtype=float),
        old_regime=ContactRegime.primary_slip_secondary_stick(
            primary_direction=SlipDirection.BELT_LEADS_PULLEY
        ),
        fired_event_names=(CVTContactEvent.PRIMARY_RESTICK.value,),
        switching_settings=CVTEventSwitchingTolerances(
            stick_exit_static_margin=0.0,
            restick_static_margin=1.0e-3,
        ),
        shift_constraint=EngagedShiftConstraint.FREE,
    )


def test_zero_crossing_falls_back_to_physically_admissible_stick() -> None:
    transition = _transition(stick_margin=5.0e-4, kinetic_outgoing=False)
    assert transition.next_mode == ContactRegime.stick_stick()
    assert (
        transition.reason == "contact_restuck_at_physical_limit_no_kinetic_continuation"
    )
    assert transition.metadata["requested_restick_margin"] == 1.0e-3
    assert transition.metadata["accepted_static_margin_floor"] == 0.0


def test_zero_crossing_keeps_outgoing_kinetic_branch_before_fallback() -> None:
    transition = _transition(stick_margin=5.0e-4, kinetic_outgoing=True)
    assert transition.next_mode is not None
    assert transition.next_mode.mode is EngagedContactMode.PRIMARY_SLIP_SECONDARY_STICK
    assert transition.reason == "kinetic_slip_direction_updated_at_zero_crossing"


def test_zero_crossing_still_terminates_when_no_physical_mode_exists() -> None:
    transition = _transition(stick_margin=-1.0e-4, kinetic_outgoing=False)
    assert transition.next_mode is None
    assert (
        transition.reason
        == "no_admissible_stick_or_direction_consistent_kinetic_branch_at_slip_zero_crossing"
    )


class _ExchangeRelativeMotion:
    def __init__(self, regime: ContactRegime) -> None:
        self._regime = regime

    def relative_speed_at(self, interface: ContactInterface) -> float:
        del interface
        return 0.0

    def relative_acceleration_at(self, interface: ContactInterface) -> float:
        if interface not in self._regime.mode.slipping_interfaces:
            return 0.0
        direction = self._regime.slip_direction_at(interface)
        sign = 1.0 if direction is SlipDirection.BELT_LEADS_PULLEY else -1.0
        if self._regime.mode is EngagedContactMode.PRIMARY_STICK_SECONDARY_SLIP:
            return -sign
        if self._regime.mode is EngagedContactMode.PRIMARY_SLIP_SECONDARY_STICK:
            return sign if direction is SlipDirection.BELT_LEADS_PULLEY else -sign
        return -sign


class _ExchangeEvaluation:
    def __init__(self, regime: ContactRegime) -> None:
        self.regime = regime
        self.normal_primary = 1000.0
        self.normal_secondary = 1000.0
        self.relative_motion = _ExchangeRelativeMotion(regime)

    def sticks_are_admissible(self, *, traction_law, required_margin: float) -> bool:
        del traction_law, required_margin
        return self.regime.mode is not EngagedContactMode.STICK_STICK

    def slipped_directions_are_consistent(self) -> bool:
        return True


class _ExchangeEvaluator:
    def __init__(self) -> None:
        self.traction_law = object()
        self.solve_settings = SimpleNamespace(
            contact_tolerances=SimpleNamespace(
                relative_speed_tolerance=1.0e-7,
                relative_acceleration_tolerance=1.0e-8,
            )
        )

    def evaluate_vector(self, *, regime: ContactRegime, **kwargs):
        del kwargs
        return _ExchangeEvaluation(regime)


def test_zero_crossing_can_exchange_which_contact_is_slipping() -> None:
    transition = resolve_cvt_contact_transition(
        evaluator=_ExchangeEvaluator(),
        time=1.0,
        vector=np.zeros(5, dtype=float),
        old_regime=ContactRegime.primary_stick_secondary_slip(
            secondary_direction=SlipDirection.BELT_LEADS_PULLEY
        ),
        fired_event_names=(CVTContactEvent.SECONDARY_RESTICK.value,),
        switching_settings=CVTEventSwitchingTolerances(
            stick_exit_static_margin=0.0,
            restick_static_margin=1.0e-3,
        ),
        shift_constraint=EngagedShiftConstraint.FREE,
    )
    assert transition.next_mode is not None
    assert transition.next_mode.mode is EngagedContactMode.PRIMARY_SLIP_SECONDARY_STICK
    assert transition.reason == "zero_crossing_simultaneous_contact_topology_exchange"
