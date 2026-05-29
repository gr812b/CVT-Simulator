from dataclasses import dataclass
from typing import Any, Callable, Optional

import numpy as np

from cvt_simulator.core.data_types import SlipBranch
from cvt_simulator.sim.simulation_ode import SimulationODE

from cvt_simulator.sim.events.simulation_constraints import (
    car_velocity_constraint_event,
    shift_constraint_event,
)

from cvt_simulator.sim.events.shift_branch_events import (
    get_shift_steady_event,
    get_back_shift_event,
    get_mid_shift_steady_event,
    get_mid_shift_wake_event,
)

from cvt_simulator.sim.events.contact_branch_events import (
    get_contact_branch_events,
    next_contact_branch,
)

CONTACT_EVENT_NAMES = {
    "primary_slip_entry_event",
    "secondary_slip_entry_event",
    "primary_slip_exit_event",
    "secondary_slip_exit_event",
}


@dataclass
class SimulationBranchTransition:
    did_transition: bool

    next_shift_mode: str
    next_contact_branch: SlipBranch

    next_time: Optional[float]
    next_state: Optional[np.ndarray]
    reason: Optional[str]

    locked_shift_distance: Optional[float]
    mid_shift_enter_time: Optional[float]
    last_mid_shift_wake_time: Optional[float]


class SimulationBranchManager:
    """Owns segment-level simulation mode behavior.

    Responsibilities:
    - build the ODE for the accepted shift/contact modes
    - build active shift/contact events
    - map fired events to the next accepted modes

    This class does not solve the ODE.
    This class does not compute contact torques directly.
    """

    def __init__(
        self,
        contact_model: Any,
        mid_shift_min_hold_time: float,
        mid_shift_relock_delay: float,
        progress_tracker: Callable[[float, float], None],
    ) -> None:
        self.contact_model = contact_model
        self.mid_shift_min_hold_time = mid_shift_min_hold_time
        self.mid_shift_relock_delay = mid_shift_relock_delay

        self.ode = SimulationODE(
            contact_model=contact_model,
            progress_tracker=progress_tracker,
        )

    def get_ode_function(
        self,
        shift_mode: str,
        contact_branch: SlipBranch,
        locked_shift_distance: Optional[float] = None,
    ):
        return self.ode.make(
            shift_mode=shift_mode,
            contact_branch=contact_branch,
            locked_shift_distance=locked_shift_distance,
        )

    def get_events(
        self,
        shift_mode: str,
        contact_branch: SlipBranch,
        locked_shift_distance: Optional[float] = None,
        mid_shift_enter_time: Optional[float] = None,
        last_mid_shift_wake_time: Optional[float] = -float("inf"),
    ) -> tuple[list[Callable], list[str]]:
        """Return events active for the current accepted modes."""

        shift_events, shift_event_names = self._get_shift_events(
            shift_mode=shift_mode,
            contact_branch=contact_branch,
            locked_shift_distance=locked_shift_distance,
            mid_shift_enter_time=mid_shift_enter_time,
            last_mid_shift_wake_time=last_mid_shift_wake_time,
        )

        contact_events, contact_event_names = get_contact_branch_events(
            contact_branch=contact_branch,
            contact_model=self.contact_model,
        )

        return (
            shift_events + contact_events,
            shift_event_names + contact_event_names,
        )

    def get_transition(
        self,
        shift_mode: str,
        contact_branch: SlipBranch,
        solution: Any,
        event_names: list[str],
        locked_shift_distance: Optional[float] = None,
        mid_shift_enter_time: Optional[float] = None,
        last_mid_shift_wake_time: Optional[float] = None,
    ) -> SimulationBranchTransition:
        """Convert the events that stopped the segment into next modes."""

        fired_names, event_time, event_state = self._segment_stop_events(
            solution=solution,
            event_names=event_names,
        )

        if not fired_names:
            return SimulationBranchTransition(
                did_transition=False,
                next_shift_mode=shift_mode,
                next_contact_branch=contact_branch,
                next_time=None,
                next_state=None,
                reason=None,
                locked_shift_distance=locked_shift_distance,
                mid_shift_enter_time=mid_shift_enter_time,
                last_mid_shift_wake_time=last_mid_shift_wake_time,
            )

        next_shift_mode = shift_mode
        next_contact_branch = contact_branch
        next_locked_shift_distance = locked_shift_distance
        next_mid_shift_enter_time = mid_shift_enter_time
        next_last_mid_shift_wake_time = last_mid_shift_wake_time

        if "shift_steady_event" in fired_names:
            next_shift_mode = "full_shift"

        if "mid_shift_steady_event" in fired_names:
            next_shift_mode = "mid_shift"
            next_locked_shift_distance = float(event_state[0])
            next_mid_shift_enter_time = event_time

        if "back_shift_event" in fired_names:
            next_shift_mode = "normal"

        if "mid_shift_wake_event" in fired_names:
            next_shift_mode = "normal"
            next_mid_shift_enter_time = None
            next_last_mid_shift_wake_time = event_time

        fired_contact_events = [
            name for name in fired_names if name in CONTACT_EVENT_NAMES
        ]

        if fired_contact_events:
            next_contact_branch = next_contact_branch_from_events(
                current_branch=contact_branch,
                fired_event_names=fired_contact_events,
            )

        did_transition = (
            next_shift_mode != shift_mode or next_contact_branch is not contact_branch
        )

        return SimulationBranchTransition(
            did_transition=did_transition,
            next_shift_mode=next_shift_mode,
            next_contact_branch=next_contact_branch,
            next_time=event_time,
            next_state=event_state,
            reason=", ".join(fired_names),
            locked_shift_distance=next_locked_shift_distance,
            mid_shift_enter_time=next_mid_shift_enter_time,
            last_mid_shift_wake_time=next_last_mid_shift_wake_time,
        )

    def _get_shift_events(
        self,
        shift_mode: str,
        contact_branch: SlipBranch,
        locked_shift_distance: Optional[float],
        mid_shift_enter_time: Optional[float],
        last_mid_shift_wake_time: Optional[float],
    ) -> tuple[list[Callable], list[str]]:
        """Return shift-mode events for the current accepted contact branch."""

        if shift_mode == "normal":
            base_mid_shift_steady_event = get_mid_shift_steady_event(
                contact_model=self.contact_model,
                contact_branch=contact_branch,
            )

            def guarded_mid_shift_steady_event(t, y):
                last_wake = (
                    -float("inf")
                    if last_mid_shift_wake_time is None
                    else last_mid_shift_wake_time
                )

                if (t - last_wake) < self.mid_shift_relock_delay:
                    return 1.0

                return base_mid_shift_steady_event(t, y)

            guarded_mid_shift_steady_event.terminal = True
            guarded_mid_shift_steady_event.direction = -1

            return (
                [
                    get_shift_steady_event(
                        contact_model=self.contact_model,
                        contact_branch=contact_branch,
                    ),
                    guarded_mid_shift_steady_event,
                    car_velocity_constraint_event,
                    shift_constraint_event,
                ],
                [
                    "shift_steady_event",
                    "mid_shift_steady_event",
                    "car_velocity_constraint_event",
                    "shift_constraint_event",
                ],
            )

        if shift_mode == "full_shift":
            return (
                [
                    get_back_shift_event(
                        contact_model=self.contact_model,
                        contact_branch=contact_branch,
                    ),
                    car_velocity_constraint_event,
                ],
                [
                    "back_shift_event",
                    "car_velocity_constraint_event",
                ],
            )

        if shift_mode == "mid_shift":
            if locked_shift_distance is None:
                raise ValueError("locked_shift_distance required for mid_shift mode")

            base_mid_shift_wake_event = get_mid_shift_wake_event(
                contact_model=self.contact_model,
                contact_branch=contact_branch,
            )

            def guarded_mid_shift_wake_event(t, y):
                if (
                    mid_shift_enter_time is not None
                    and (t - mid_shift_enter_time) < self.mid_shift_min_hold_time
                ):
                    return -1.0

                return base_mid_shift_wake_event(t, y)

            guarded_mid_shift_wake_event.terminal = True
            guarded_mid_shift_wake_event.direction = 1

            return (
                [
                    guarded_mid_shift_wake_event,
                    car_velocity_constraint_event,
                ],
                [
                    "mid_shift_wake_event",
                    "car_velocity_constraint_event",
                ],
            )

        raise ValueError(f"Unknown shift mode: {shift_mode}")

    def _segment_stop_events(
        self,
        solution: Any,
        event_names: list[str],
        time_tol: float = 1e-8,
    ) -> tuple[list[str], Optional[float], Optional[np.ndarray]]:
        """Return event names that fired at the segment stop time.

        If multiple terminal events fire at effectively the same time, return
        all of them so simultaneous contact transitions can be handled together.
        """

        fired: list[tuple[str, float, np.ndarray]] = []

        for index, name in enumerate(event_names):
            if index >= len(solution.t_events):
                continue

            times = np.asarray(solution.t_events[index])
            if times.size == 0:
                continue

            fired.append(
                (
                    name,
                    float(times[0]),
                    solution.y_events[index][0],
                )
            )

        if not fired:
            return [], None, None

        stop_time = min(time for _, time, _ in fired)

        simultaneous = [
            (name, time, state)
            for name, time, state in fired
            if abs(time - stop_time) <= time_tol
        ]

        names = [name for name, _, _ in simultaneous]
        state = simultaneous[0][2]

        return names, stop_time, state


def next_contact_branch_from_events(
    current_branch: SlipBranch,
    fired_event_names: list[str],
) -> SlipBranch:
    return next_contact_branch(
        current_branch=current_branch,
        fired_event_names=fired_event_names,
    )
