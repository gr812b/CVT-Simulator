"""Mechanism-first dynamic actuator ablation study for the Baja CVT.

The study answers two different questions without conflating them:

A. DIRECT PREDICTION COMPARISON
   Evaluate full-dynamic and quasi-static actuator laws on the SAME operating
   point and the SAME solved full-model closure unknowns. This isolates the
   force/torque prediction change created by the new dynamic terms.

B. TRAJECTORY CONSEQUENCE
   Integrate all four models independently, then compare the resulting clamp,
   belt-normal force, traction utilization, shift dynamics, and shaft speeds.

Four model variants are retained:
    full
    quasi_static_flyweight
    quasi_static_helix
    fully_quasi_static

The quasi-static reductions preserve the same hardware and static force maps.
Only mechanism-specific dynamic coupling is removed, with hardware rotational
inertia returned to the classical constant shaft inertia so mass is not deleted.
"""

from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass, replace
import json
from math import isfinite
from pathlib import Path
import sys
from typing import Any

import matplotlib.pyplot as plt
import numpy as np

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import run_route_grade_response as route  # noqa: E402
from cad_drivetrain_inertias import (  # noqa: E402
    PCVT_TOTAL_MOI_KG_M2,
    SCVT_TOTAL_MOI_KG_M2,
    SCVT_MOVABLE_SHEAVE_MOI_KG_M2,
)
from cinder.execution.hybrid import (  # noqa: E402
    HybridIntegratorSettings,
    integrate_hybrid,
)
from cinder.execution.hybrid.composed import (  # noqa: E402
    ComposedCVTHybridSystem,
)
from cinder.execution.hybrid.cvt_regime import (  # noqa: E402
    CVTEngagementState,
)
from cinder.hosts import SecondaryShaftAngleHost  # noqa: E402
from cinder.model.boundaries.shaft import (  # noqa: E402
    FullThrottleEngineBoundary,
)
from cinder.model.cvt.actuation import (  # noqa: E402
    FixedPivotFlyweightForce,
    HelicalCouplingState,
    HelicalTorqueReactionForce,
    PulleyActuator,
    PulleyActuationContext,
    PulleyClosureChannels,
)
from cinder.model.cvt.actuation.types import (  # noqa: E402
    ActuationContribution,
    PulleyElementContribution,
)
from cinder.model.cvt.closure import (  # noqa: E402
    AffineClosureScalar,
    ClosureGains,
    ClosureUnknown,
    ClosureUnknowns,
)
from cinder.model.cvt.inertia import (  # noqa: E402
    PrimaryInertia,
    ResolvedSecondaryInertia,
    SecondaryFixedInertia,
)
from cinder.model.system import (  # noqa: E402
    CVTAssemblySpec,
    CVTState,
    MechanicalCVTPlant,
    PulleyPairSpec,
    PulleySpec,
)
from cinder.results.inspection import inspect_cvt_state  # noqa: E402

RPM_PER_RADIAN_PER_SECOND = 60.0 / (2.0 * np.pi)
MILLIMETRE = 1.0e-3
NAN = float("nan")


# ---------------------------------------------------------------------------
# Quasi-static reductions
# ---------------------------------------------------------------------------


class QuasiStaticFixedPivotFlyweightForce(FixedPivotFlyweightForce):
    """Force-only reduction of the exact physical fixed-pivot map."""

    def evaluate(
        self,
        context: PulleyActuationContext,
    ) -> AffineClosureScalar:
        sample = self.spec.mechanism_map.evaluate(
            context.axial_position
        )
        return AffineClosureScalar.constant(
            0.5
            * context.shaft_speed**2
            * sample.shaft_inertia_gradient
        )

    def evaluate_element(
        self,
        context: PulleyActuationContext,
    ) -> PulleyElementContribution:
        return PulleyElementContribution.from_closing_force(
            self.evaluate(context)
        )

    def kinetic_modes(
        self,
        context: PulleyActuationContext,
    ):
        return ()

    def inspect(
        self,
        context: PulleyActuationContext,
    ) -> tuple[ActuationContribution, ...]:
        return (
            ActuationContribution(
                key="quasi_static_fixed_pivot_centrifugal",
                label="Quasi-static fixed-pivot centrifugal drive",
                relation=self.evaluate(context),
            ),
        )


class QuasiStaticHelicalTorqueReactionForce(
    HelicalTorqueReactionForce
):
    """Classical torque-reactive helix with no dynamic movable-member term."""

    def evaluate(
        self,
        context: PulleyActuationContext,
    ) -> AffineClosureScalar:
        coupling = context.helical_coupling
        channels = context.closure_channels
        if coupling is None:
            raise ValueError(
                "Quasi-static helix requires helical coupling."
            )
        if channels is None:
            raise ValueError(
                "Quasi-static helix requires closure channels."
            )

        motion_ratio = coupling.dtheta_daxial
        theta = coupling.kinematics.theta
        spring_torque = self.spec.torsional_stiffness * (
            self.spec.initial_twist - theta
        )
        return AffineClosureScalar(
            bias=motion_ratio * spring_torque,
            gains=ClosureGains.from_by_unknown(
                {
                    channels.shaft_torque: (
                        motion_ratio
                        * self.spec.movable_member_torque_fraction
                    )
                }
            ),
        )

    def evaluate_element(
        self,
        context: PulleyActuationContext,
    ) -> PulleyElementContribution:
        return PulleyElementContribution.from_closing_force(
            self.evaluate(context)
        )

    def inspect(
        self,
        context: PulleyActuationContext,
    ) -> tuple[ActuationContribution, ...]:
        coupling = context.helical_coupling
        channels = context.closure_channels
        if coupling is None or channels is None:
            raise ValueError(
                "Quasi-static helix inspection requires coupling "
                "and closure channels."
            )
        motion_ratio = coupling.dtheta_daxial
        theta = coupling.kinematics.theta
        spring_torque = self.spec.torsional_stiffness * (
            self.spec.initial_twist - theta
        )
        return (
            ActuationContribution(
                key="quasi_static_helix_torsional_spring",
                label="Quasi-static helix torsional spring",
                relation=AffineClosureScalar.constant(
                    motion_ratio * spring_torque
                ),
            ),
            ActuationContribution(
                key="quasi_static_helix_reacted_belt_torque",
                label="Quasi-static helix reacted belt torque",
                relation=AffineClosureScalar(
                    gains=ClosureGains.from_by_unknown(
                        {
                            channels.shaft_torque: (
                                motion_ratio
                                * self.spec.movable_member_torque_fraction
                            )
                        }
                    )
                ),
            ),
        )


@dataclass(frozen=True, slots=True)
class AblationVariant:
    key: str
    label: str
    dynamic_flyweight: bool
    dynamic_helix: bool


VARIANTS = (
    AblationVariant(
        key="full",
        label="Full dynamic",
        dynamic_flyweight=True,
        dynamic_helix=True,
    ),
    AblationVariant(
        key="quasi_static_flyweight",
        label="QS flyweight",
        dynamic_flyweight=False,
        dynamic_helix=True,
    ),
    AblationVariant(
        key="quasi_static_helix",
        label="QS helix",
        dynamic_flyweight=True,
        dynamic_helix=False,
    ),
    AblationVariant(
        key="fully_quasi_static",
        label="Fully quasi-static",
        dynamic_flyweight=False,
        dynamic_helix=False,
    ),
)


@dataclass(slots=True)
class SampleRecord:
    row: dict[str, Any]
    time: float
    full_state: np.ndarray
    composed_mode: object
    cvt_state: CVTState
    closure: ClosureUnknowns | None
    geometry: object


@dataclass(slots=True)
class VariantResult:
    variant: AblationVariant
    assembly: CVTAssemblySpec
    system: ComposedCVTHybridSystem
    hybrid_result: object
    samples: list[SampleRecord]
    contribution_rows: list[dict[str, Any]]
    metrics: dict[str, Any]


# ---------------------------------------------------------------------------
# CLI / scenario
# ---------------------------------------------------------------------------


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--scenario",
        choices=("launch", "hill"),
        default="launch",
    )
    parser.add_argument("--duration-s", type=float, default=None)
    parser.add_argument(
        "--sample-step-s",
        type=float,
        default=0.001,
        help=(
            "Dense-output sampling interval inside each continuous hybrid "
            "segment. Segment endpoints are always retained exactly."
        ),
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path(
            "outputs/dynamic_actuator_ablation_rich"
        ),
    )
    parser.add_argument("--rtol", type=float, default=1.0e-3)
    parser.add_argument("--atol", type=float, default=1.0e-6)
    parser.add_argument("--max-step-s", type=float, default=0.025)
    parser.add_argument("--no-show", action="store_true")
    return parser.parse_args()


def programme_for_scenario(
    scenario: str,
    duration_override: float | None,
):
    if scenario == "launch":
        duration = (
            10.0
            if duration_override is None
            else float(duration_override)
        )
        return (
            route.GradeProgramme(
                (
                    route.GradePhase(
                        name="flat launch",
                        start_s=0.0,
                        end_s=duration,
                        start_degrees=0.0,
                        end_degrees=0.0,
                        transition=False,
                    ),
                )
            ),
            duration,
        )

    programme = route.GradeProgramme.default()
    duration = (
        programme.end_time_s
        if duration_override is None
        else float(duration_override)
    )
    return programme, duration


# ---------------------------------------------------------------------------
# Variant construction
# ---------------------------------------------------------------------------


def _replace_flyweight_law(
    actuator: PulleyActuator,
    *,
    dynamic: bool,
) -> PulleyActuator:
    laws = []
    found = 0
    for law in actuator.force_laws:
        if isinstance(law, FixedPivotFlyweightForce):
            found += 1
            laws.append(
                law
                if dynamic
                else QuasiStaticFixedPivotFlyweightForce(
                    law.spec
                )
            )
        else:
            laws.append(law)
    if found != 1:
        raise RuntimeError(
            "Expected exactly one fixed-pivot flyweight law; "
            f"found {found}."
        )
    return PulleyActuator(*laws)


def _replace_helix_law(
    actuator: PulleyActuator,
    *,
    dynamic: bool,
) -> PulleyActuator:
    laws = []
    found = 0
    for law in actuator.force_laws:
        if isinstance(law, HelicalTorqueReactionForce):
            found += 1
            laws.append(
                law
                if dynamic
                else QuasiStaticHelicalTorqueReactionForce(
                    spec=law.spec
                )
            )
        else:
            laws.append(law)
    if found != 1:
        raise RuntimeError(
            "Expected exactly one helix force law; "
            f"found {found}."
        )
    return PulleyActuator(*laws)


def ablate_assembly(
    full: CVTAssemblySpec,
    variant: AblationVariant,
) -> CVTAssemblySpec:
    primary_actuator = _replace_flyweight_law(
        full.pulleys.primary.actuator,
        dynamic=variant.dynamic_flyweight,
    )
    secondary_actuator = _replace_helix_law(
        full.pulleys.secondary.actuator,
        dynamic=variant.dynamic_helix,
    )

    primary_inertia = full.inertias.primary
    secondary_inertia = full.inertias.secondary

    if not variant.dynamic_flyweight:
        primary_inertia = PrimaryInertia(
            fixed_rotating_hardware_inertia=(
                PCVT_TOTAL_MOI_KG_M2
            ),
            movable_sheave_rotational_inertia=0.0,
            moving_sheave_mass=(
                full.inertias.primary.moving_sheave_mass
            ),
        )

    if not variant.dynamic_helix:
        fixed_total = (
            secondary_inertia.fixed_side.total
            + secondary_inertia.movable_sheave_rotational_inertia
        )
        if abs(fixed_total - SCVT_TOTAL_MOI_KG_M2) > 1.0e-10:
            raise RuntimeError(
                "Current secondary fixed + movable inertia "
                "does not recover SCVT CAD total."
            )
        secondary_inertia = ResolvedSecondaryInertia(
            fixed_side=SecondaryFixedInertia(
                fixed_rotating_hardware_inertia=fixed_total
            ),
            movable_sheave_rotational_inertia=0.0,
        )

    return replace(
        full,
        pulleys=PulleyPairSpec(
            primary=PulleySpec(
                actuator=primary_actuator,
                helical_coupling=(
                    full.pulleys.primary.helical_coupling
                ),
            ),
            secondary=PulleySpec(
                actuator=secondary_actuator,
                helical_coupling=(
                    full.pulleys.secondary.helical_coupling
                ),
            ),
        ),
        inertias=replace(
            full.inertias,
            primary=primary_inertia,
            secondary=secondary_inertia,
        ),
    )


def build_system_from_assembly(
    *,
    assembly: CVTAssemblySpec,
    engine,
    road_load,
    constants,
    programme,
) -> ComposedCVTHybridSystem:
    plant = MechanicalCVTPlant.from_assembly(assembly)
    host = SecondaryShaftAngleHost()
    secondary_boundary = (
        route.TimeProgrammedLockedFinalDriveBoundary(
            road_load=road_load,
            programme=programme,
            direct_secondary_shaft_inertia=(
                constants.gearbox_input_rotational_inertia
            ),
        )
    )
    return ComposedCVTHybridSystem.from_plant(
        plant=plant,
        primary_boundary=FullThrottleEngineBoundary(
            engine,
            equivalent_rotational_inertia=(
                constants.engine_rotational_inertia
            ),
        ),
        secondary_boundary=secondary_boundary,
        host=host,
    )


# ---------------------------------------------------------------------------
# Helpers for production-model inspection
# ---------------------------------------------------------------------------


def _mode_name(value: object) -> str:
    name = getattr(value, "name", None)
    return str(name if name is not None else value)


def _find_flyweight(actuator: PulleyActuator):
    laws = [
        law
        for law in actuator.force_laws
        if isinstance(law, FixedPivotFlyweightForce)
    ]
    if len(laws) != 1:
        raise RuntimeError(
            f"Expected one flyweight law; found {len(laws)}."
        )
    return laws[0]


def _find_helix(actuator: PulleyActuator):
    laws = [
        law
        for law in actuator.force_laws
        if isinstance(law, HelicalTorqueReactionForce)
    ]
    if len(laws) != 1:
        raise RuntimeError(
            f"Expected one helix law; found {len(laws)}."
        )
    return laws[0]


def _geometry_for_mode(
    model: MechanicalCVTPlant,
    state: CVTState,
    composed_mode,
):
    if (
        composed_mode.cvt.engagement
        is CVTEngagementState.ENGAGED
    ):
        return model.geometry.evaluate_engaged(
            state.shift_position
        )
    return model.geometry.evaluate_deadzone(
        state.shift_position
    )


def _segment_sample_times(segment, step: float) -> np.ndarray:
    start = segment.start_time
    end = segment.end_time
    if end <= start:
        return np.asarray([start], dtype=float)

    interior = np.arange(
        start + step,
        end,
        step,
        dtype=float,
    )
    values = np.concatenate(
        (
            np.asarray([start], dtype=float),
            interior,
            np.asarray([end], dtype=float),
        )
    )
    # Exact unique is safe because endpoints/interior are constructed from
    # the same scalars; do not round physical event times.
    return np.unique(values)


def _closure_dict(
    closure: ClosureUnknowns | None,
) -> dict[str, float]:
    if closure is None:
        return {
            "alpha_primary_rad_s2": NAN,
            "alpha_secondary_rad_s2": NAN,
            "belt_acceleration_closure_m_s2": NAN,
            "shift_acceleration_closure_m_s2": NAN,
            "tau_primary_belt_Nm": NAN,
            "tau_secondary_belt_Nm": NAN,
            "normal_primary_N": NAN,
            "normal_secondary_N": NAN,
        }
    return {
        "alpha_primary_rad_s2": (
            closure.primary_angular_acceleration
        ),
        "alpha_secondary_rad_s2": (
            closure.secondary_angular_acceleration
        ),
        "belt_acceleration_closure_m_s2": (
            closure.belt_acceleration
        ),
        "shift_acceleration_closure_m_s2": (
            closure.shift_acceleration
        ),
        "tau_primary_belt_Nm": closure.primary_torque,
        "tau_secondary_belt_Nm": closure.secondary_torque,
        "normal_primary_N": (
            closure.primary_normal_resultant
        ),
        "normal_secondary_N": (
            closure.secondary_normal_resultant
        ),
    }


def _contribution_rows(
    *,
    variant: AblationVariant,
    time_s: float,
    segment_index: int,
    pulley: str,
    inspection,
    closure: ClosureUnknowns,
) -> list[dict[str, Any]]:
    rows = []
    for contribution in inspection.contributions:
        relation = contribution.relation
        row = {
            "variant": variant.key,
            "variant_label": variant.label,
            "time_s": time_s,
            "segment_index": segment_index,
            "pulley": pulley,
            "contribution_key": contribution.key,
            "contribution_label": contribution.label,
            "resolved_force_N": relation.evaluate(closure),
            "bias_force_N": relation.bias,
        }
        for unknown in ClosureUnknown:
            row[
                f"gain__{unknown.name.lower()}"
            ] = relation.gains[unknown]
        rows.append(row)
    return rows


def _mechanism_terms(
    *,
    model: MechanicalCVTPlant,
    state: CVTState,
    geometry,
    closure: ClosureUnknowns | None,
) -> dict[str, float]:
    """Evaluate physical mechanism terms independent of active ablation.

    These columns always use the physical flyweight map and physical movable
    secondary-sheave inertia. They therefore allow post-processing to ask
    "what would the full correction be at this trajectory point?" even for
    a quasi-static variant.
    """

    pcoord = geometry.primary_axial_coordinate
    scoord = geometry.secondary_axial_coordinate
    axial = model.inertias.axial_translation.evaluate(
        primary_axial_coordinate=pcoord,
        secondary_axial_coordinate=scoord,
        belt_axial_coordinate=geometry.belt_axial_coordinate,
    )
    base_mass = (
        axial.primary.reflected_mass
        + axial.secondary.reflected_mass
        + axial.belt.reflected_mass
    )

    fly_law = _find_flyweight(model.primary_actuator)
    fw = fly_law.spec.mechanism_map.evaluate(pcoord.value)
    dq_ds = fw.angle_gradient * pcoord.d_value_ds
    fly_mass = fw.pivot_inertia * dq_ds**2

    coupling = model.secondary_helical_coupling
    if coupling is None:
        raise RuntimeError("Secondary helix coupling missing.")
    hk = coupling.evaluate_from_local_coordinate(
        axial_position=scoord.value,
        d_axial_position_ds=scoord.d_value_ds,
        d2_axial_position_ds2=scoord.d2_value_ds2,
    )
    helix_mass = (
        SCVT_MOVABLE_SHEAVE_MOI_KG_M2
        * hk.dtheta_ds**2
    )

    result = {
        "mass_primary_translation_kg": (
            axial.primary.reflected_mass
        ),
        "mass_secondary_translation_kg": (
            axial.secondary.reflected_mass
        ),
        "mass_belt_translation_kg": (
            axial.belt.reflected_mass
        ),
        "mass_base_axial_total_kg": base_mass,
        "mass_flyweight_reflected_candidate_kg": fly_mass,
        "mass_helix_reflected_candidate_kg": helix_mass,
        "flyweight_q_rad": fw.angle,
        "flyweight_q_prime_rad_per_m": fw.angle_gradient,
        "flyweight_q_second_rad_per_m2": fw.angle_curvature,
        "flyweight_pivot_inertia_kg_m2": fw.pivot_inertia,
        "flyweight_shaft_inertia_kg_m2": fw.shaft_inertia,
        "flyweight_shaft_inertia_gradient_kg_m": (
            fw.shaft_inertia_gradient
        ),
        "helix_theta_rad": hk.theta,
        "helix_dtheta_ds_rad_per_m": hk.dtheta_ds,
        "helix_d2theta_ds2_rad_per_m2": hk.d2theta_ds2,
        "helix_dtheta_dopening_rad_per_m": (
            hk.dtheta_dopening
        ),
    }

    if closure is None:
        result.update(
            {
                "fly_qs_centrifugal_force_N": NAN,
                "fly_dynamic_axial_inertia_force_N": NAN,
                "fly_dynamic_curvature_force_N": NAN,
                "fly_dynamic_total_correction_N": NAN,
                "fly_full_force_N": NAN,
                "fly_dynamic_correction_pct_of_qs_force": NAN,
                "fly_dynamic_shaft_torque_correction_vs_constant_Nm": NAN,
                "helix_qs_reaction_force_N": NAN,
                "helix_dynamic_shaft_accel_force_N": NAN,
                "helix_dynamic_shift_accel_force_N": NAN,
                "helix_dynamic_curvature_force_N": NAN,
                "helix_dynamic_total_correction_N": NAN,
                "helix_full_reaction_force_N": NAN,
                "helix_dynamic_correction_pct_of_qs_force": NAN,
                "helix_dynamic_shaft_torque_correction_vs_constant_Nm": NAN,
                "helix_theta_ddot_rad_s2": NAN,
            }
        )
        return result

    sdot = state.shift_speed
    sddot = closure.shift_acceleration

    xdot_p = pcoord.d_value_ds * sdot
    xddot_p = (
        pcoord.d_value_ds * sddot
        + pcoord.d2_value_ds2 * sdot**2
    )
    fly_qs = (
        0.5
        * state.primary_angular_speed**2
        * fw.shaft_inertia_gradient
    )
    fly_axial = (
        -fw.pivot_inertia
        * fw.angle_gradient**2
        * xddot_p
    )
    fly_curvature = (
        -fw.pivot_inertia
        * fw.angle_gradient
        * fw.angle_curvature
        * xdot_p**2
    )
    fly_delta = fly_axial + fly_curvature
    j0 = fly_law.spec.mechanism_map.evaluate(0.0).shaft_inertia
    fly_shaft_delta = (
        -(fw.shaft_inertia - j0)
        * closure.primary_angular_acceleration
        - fw.shaft_inertia_gradient
        * xdot_p
        * state.primary_angular_speed
    )

    helix_law = _find_helix(model.secondary_actuator)
    opening_gain = coupling.opening_per_axial_position
    dtheta_dx = hk.dtheta_dopening * opening_gain
    theta_ddot = (
        hk.dtheta_ds * sddot
        + hk.d2theta_ds2 * sdot**2
    )
    spring_torque = (
        helix_law.spec.torsional_stiffness
        * (
            helix_law.spec.initial_twist
            - hk.theta
        )
    )
    qs_helix_torque = (
        helix_law.spec.movable_member_torque_fraction
        * closure.secondary_torque
        + spring_torque
    )
    helix_qs_force = dtheta_dx * qs_helix_torque
    helix_shaft_accel_force = (
        -dtheta_dx
        * SCVT_MOVABLE_SHEAVE_MOI_KG_M2
        * closure.secondary_angular_acceleration
    )
    helix_shift_accel_force = (
        -dtheta_dx
        * SCVT_MOVABLE_SHEAVE_MOI_KG_M2
        * hk.dtheta_ds
        * sddot
    )
    helix_curvature_force = (
        -dtheta_dx
        * SCVT_MOVABLE_SHEAVE_MOI_KG_M2
        * hk.d2theta_ds2
        * sdot**2
    )
    helix_delta = (
        helix_shaft_accel_force
        + helix_shift_accel_force
        + helix_curvature_force
    )
    helix_shaft_delta = (
        -SCVT_MOVABLE_SHEAVE_MOI_KG_M2
        * theta_ddot
    )

    result.update(
        {
            "fly_qs_centrifugal_force_N": fly_qs,
            "fly_dynamic_axial_inertia_force_N": fly_axial,
            "fly_dynamic_curvature_force_N": fly_curvature,
            "fly_dynamic_total_correction_N": fly_delta,
            "fly_full_force_N": fly_qs + fly_delta,
            "fly_dynamic_correction_pct_of_qs_force": (
                100.0 * fly_delta / fly_qs
                if abs(fly_qs) > 1.0e-12
                else NAN
            ),
            "fly_dynamic_shaft_torque_correction_vs_constant_Nm": (
                fly_shaft_delta
            ),
            "helix_qs_reaction_force_N": helix_qs_force,
            "helix_dynamic_shaft_accel_force_N": (
                helix_shaft_accel_force
            ),
            "helix_dynamic_shift_accel_force_N": (
                helix_shift_accel_force
            ),
            "helix_dynamic_curvature_force_N": (
                helix_curvature_force
            ),
            "helix_dynamic_total_correction_N": helix_delta,
            "helix_full_reaction_force_N": (
                helix_qs_force + helix_delta
            ),
            "helix_dynamic_correction_pct_of_qs_force": (
                100.0 * helix_delta / helix_qs_force
                if abs(helix_qs_force) > 1.0e-12
                else NAN
            ),
            "helix_dynamic_shaft_torque_correction_vs_constant_Nm": (
                helix_shaft_delta
            ),
            "helix_theta_ddot_rad_s2": theta_ddot,
        }
    )
    return result


def sample_variant(
    *,
    variant: AblationVariant,
    system: ComposedCVTHybridSystem,
    result,
    step_s: float,
) -> tuple[
    list[SampleRecord],
    list[dict[str, Any]],
]:
    model = system.cvt.model
    records: list[SampleRecord] = []
    contributions: list[dict[str, Any]] = []

    for segment_index, segment in enumerate(result.segments):
        times = _segment_sample_times(segment, step_s)
        states = segment.dense_state_at(times)

        for local_index, time_s in enumerate(times):
            full_state = np.asarray(
                states[:, local_index],
                dtype=float,
            )
            cvt_vector = system.layout.view(
                full_state,
                "cvt",
            )
            cvt_state = CVTState.from_vector(cvt_vector)
            mode = segment.mode
            rhs = system.rhs(
                float(time_s),
                full_state,
                mode,
            )
            cvt_rhs = system.layout.view(rhs, "cvt")
            boundaries = system._shaft_boundaries(
                time=float(time_s),
                state=full_state,
            )
            inspection = inspect_cvt_state(
                system=system.cvt,
                time=float(time_s),
                vector=cvt_vector,
                mode=mode.cvt,
                shaft_boundaries=boundaries,
                include_closure_audit=False,
            )
            closure = inspection.closure_unknowns
            geometry = _geometry_for_mode(
                model,
                cvt_state,
                mode,
            )

            row: dict[str, Any] = {
                "variant": variant.key,
                "variant_label": variant.label,
                "dynamic_flyweight": variant.dynamic_flyweight,
                "dynamic_helix": variant.dynamic_helix,
                "segment_index": segment_index,
                "segment_local_index": local_index,
                "time_s": float(time_s),
                "sample_location": (
                    "segment_start"
                    if local_index == 0
                    else (
                        "segment_end"
                        if local_index == len(times) - 1
                        else "interior"
                    )
                ),
                "segment_has_event": bool(
                    segment.fired_event_names
                ),
                "segment_event_names": "|".join(
                    segment.fired_event_names
                ),
                "mode": str(mode),
                "cvt_mode": str(mode.cvt),
                "engagement_state": _mode_name(
                    mode.cvt.engagement
                ),
                "primary_omega_rad_s": (
                    cvt_state.primary_angular_speed
                ),
                "primary_rpm": (
                    cvt_state.primary_angular_speed
                    * RPM_PER_RADIAN_PER_SECOND
                ),
                "secondary_omega_rad_s": (
                    cvt_state.secondary_angular_speed
                ),
                "secondary_rpm": (
                    cvt_state.secondary_angular_speed
                    * RPM_PER_RADIAN_PER_SECOND
                ),
                "belt_speed_m_s": cvt_state.belt_speed,
                "shift_m": cvt_state.shift_position,
                "shift_mm": (
                    cvt_state.shift_position
                    / MILLIMETRE
                ),
                "shift_speed_m_s": cvt_state.shift_speed,
                "shift_speed_mm_s": (
                    cvt_state.shift_speed
                    / MILLIMETRE
                ),
                # Continuous RHS values: no numerical differentiation.
                "rhs_alpha_primary_rad_s2": float(cvt_rhs[0]),
                "rhs_alpha_secondary_rad_s2": float(cvt_rhs[1]),
                "rhs_belt_acceleration_m_s2": float(cvt_rhs[2]),
                "rhs_shift_speed_m_s": float(cvt_rhs[3]),
                "rhs_shift_acceleration_m_s2": float(cvt_rhs[4]),
                "primary_external_torque_Nm": (
                    boundaries.primary.external_torque
                ),
                "primary_boundary_inertia_kg_m2": (
                    boundaries.primary.equivalent_inertia
                ),
                "secondary_external_torque_Nm": (
                    boundaries.secondary.external_torque
                ),
                "secondary_boundary_inertia_kg_m2": (
                    boundaries.secondary.equivalent_inertia
                ),
                "ratio_secondary_over_primary": (
                    inspection.geometry
                    .effective_ratio_secondary_over_primary
                ),
                "primary_effective_radius_m": (
                    inspection.geometry.primary.effective
                ),
                "secondary_effective_radius_m": (
                    inspection.geometry.secondary.effective
                ),
                "primary_wrap_rad": (
                    inspection.geometry.primary_wrap_angle
                ),
                "secondary_wrap_rad": (
                    inspection.geometry.secondary_wrap_angle
                ),
                "primary_axial_x_m": (
                    geometry.primary_axial_coordinate.value
                ),
                "primary_dx_ds": (
                    geometry.primary_axial_coordinate.d_value_ds
                ),
                "primary_d2x_ds2_per_m": (
                    geometry.primary_axial_coordinate.d2_value_ds2
                ),
                "secondary_axial_x_m": (
                    geometry.secondary_axial_coordinate.value
                ),
                "secondary_dx_ds": (
                    geometry.secondary_axial_coordinate.d_value_ds
                ),
                "secondary_d2x_ds2_per_m": (
                    geometry.secondary_axial_coordinate.d2_value_ds2
                ),
                "belt_axial_x_m": (
                    geometry.belt_axial_coordinate.value
                ),
                "belt_dx_ds": (
                    geometry.belt_axial_coordinate.d_value_ds
                ),
                "belt_d2x_ds2_per_m": (
                    geometry.belt_axial_coordinate.d2_value_ds2
                ),
            }
            row.update(_closure_dict(closure))
            row.update(
                _mechanism_terms(
                    model=model,
                    state=cvt_state,
                    geometry=geometry,
                    closure=closure,
                )
            )

            # Active generalized-mass interpretation for this variant.
            row["mass_flyweight_reflected_active_kg"] = (
                row["mass_flyweight_reflected_candidate_kg"]
                if variant.dynamic_flyweight
                else 0.0
            )
            row["mass_helix_reflected_active_kg"] = (
                row["mass_helix_reflected_candidate_kg"]
                if variant.dynamic_helix
                else 0.0
            )
            row["mass_total_direct_active_kg"] = (
                row["mass_base_axial_total_kg"]
                + row["mass_flyweight_reflected_active_kg"]
                + row["mass_helix_reflected_active_kg"]
            )

            if closure is not None:
                primary_total = (
                    inspection.primary_actuation
                    .resolve_total(closure)
                )
                secondary_total = (
                    inspection.secondary_actuation
                    .resolve_total(closure)
                    if inspection.secondary_actuation is not None
                    else NAN
                )
                row["primary_actuator_closing_force_N"] = (
                    primary_total
                )
                row["secondary_actuator_closing_force_N"] = (
                    secondary_total
                )

                contact = inspection.contact
                if contact is not None:
                    traction = contact.traction_utilization
                    row["lambda_primary"] = (
                        traction.primary_lambda
                    )
                    row["lambda_secondary"] = (
                        traction.secondary_lambda
                    )
                    row["low_ratio_seat_reaction_N"] = (
                        contact.low_ratio_seat_reaction
                        if contact.low_ratio_seat_reaction is not None
                        else NAN
                    )
                    row["upper_stop_reaction_N"] = (
                        contact.upper_stop_reaction
                        if contact.upper_stop_reaction is not None
                        else NAN
                    )
                else:
                    row["lambda_primary"] = NAN
                    row["lambda_secondary"] = NAN
                    row["low_ratio_seat_reaction_N"] = NAN
                    row["upper_stop_reaction_N"] = NAN

                contributions.extend(
                    _contribution_rows(
                        variant=variant,
                        time_s=float(time_s),
                        segment_index=segment_index,
                        pulley="primary",
                        inspection=inspection.primary_actuation,
                        closure=closure,
                    )
                )
                if inspection.secondary_actuation is not None:
                    contributions.extend(
                        _contribution_rows(
                            variant=variant,
                            time_s=float(time_s),
                            segment_index=segment_index,
                            pulley="secondary",
                            inspection=inspection.secondary_actuation,
                            closure=closure,
                        )
                    )
            else:
                row["primary_actuator_closing_force_N"] = NAN
                row["secondary_actuator_closing_force_N"] = NAN
                row["lambda_primary"] = NAN
                row["lambda_secondary"] = NAN
                row["low_ratio_seat_reaction_N"] = NAN
                row["upper_stop_reaction_N"] = NAN

            records.append(
                SampleRecord(
                    row=row,
                    time=float(time_s),
                    full_state=np.array(
                        full_state,
                        dtype=float,
                        copy=True,
                    ),
                    composed_mode=mode,
                    cvt_state=cvt_state,
                    closure=closure,
                    geometry=geometry,
                )
            )

    return records, contributions


# ---------------------------------------------------------------------------
# Counterfactual direct predictions on the same full-model trajectory
# ---------------------------------------------------------------------------


def _actuation_contexts_for_model(
    *,
    model: MechanicalCVTPlant,
    time_s: float,
    state: CVTState,
    geometry,
):
    return (
        model.primary_actuation_context(
            time=time_s,
            state=state,
            geometry=geometry,
        ),
        model.secondary_actuation_context(
            time=time_s,
            state=state,
            geometry=geometry,
        ),
    )


def direct_prediction_on_full_trajectory(
    results: list[VariantResult],
) -> tuple[
    list[dict[str, Any]],
    list[dict[str, Any]],
]:
    full = next(
        item for item in results
        if item.variant.key == "full"
    )
    by_key = {item.variant.key: item for item in results}
    rows: list[dict[str, Any]] = []
    long_contrib: list[dict[str, Any]] = []

    for sample in full.samples:
        if sample.closure is None:
            continue

        row: dict[str, Any] = {
            "time_s": sample.time,
            "segment_index": sample.row["segment_index"],
            "shift_mm": sample.row["shift_mm"],
            "shift_speed_mm_s": sample.row["shift_speed_mm_s"],
            "primary_rpm": sample.row["primary_rpm"],
            "secondary_rpm": sample.row["secondary_rpm"],
            "alpha_primary_rad_s2": (
                sample.closure.primary_angular_acceleration
            ),
            "alpha_secondary_rad_s2": (
                sample.closure.secondary_angular_acceleration
            ),
            "shift_acceleration_m_s2": (
                sample.closure.shift_acceleration
            ),
            "tau_primary_belt_Nm": (
                sample.closure.primary_torque
            ),
            "tau_secondary_belt_Nm": (
                sample.closure.secondary_torque
            ),
            "normal_primary_full_solution_N": (
                sample.closure.primary_normal_resultant
            ),
            "normal_secondary_full_solution_N": (
                sample.closure.secondary_normal_resultant
            ),
        }

        for key, item in by_key.items():
            model = item.system.cvt.model
            # Every variant has identical belt/pulley geometry; use that
            # model's own geometry object at the full state.
            if (
                sample.composed_mode.cvt.engagement
                is CVTEngagementState.ENGAGED
            ):
                geometry = model.geometry.evaluate_engaged(
                    sample.cvt_state.shift_position
                )
            else:
                continue

            pctx, sctx = _actuation_contexts_for_model(
                model=model,
                time_s=sample.time,
                state=sample.cvt_state,
                geometry=geometry,
            )
            pinspect = model.primary_actuator.inspect(pctx)
            sinspect = model.secondary_actuator.inspect(sctx)

            ptotal = pinspect.resolve_total(sample.closure)
            stotal = sinspect.resolve_total(sample.closure)
            row[
                f"primary_total_clamp__{key}_N"
            ] = ptotal
            row[
                f"secondary_total_clamp__{key}_N"
            ] = stotal

            for pulley, inspection in (
                ("primary", pinspect),
                ("secondary", sinspect),
            ):
                for contribution in inspection.contributions:
                    relation = contribution.relation
                    c_row = {
                        "counterfactual_variant": key,
                        "counterfactual_variant_label": (
                            item.variant.label
                        ),
                        "time_s": sample.time,
                        "segment_index": (
                            sample.row["segment_index"]
                        ),
                        "shift_mm": sample.row["shift_mm"],
                        "primary_rpm": sample.row["primary_rpm"],
                        "pulley": pulley,
                        "contribution_key": contribution.key,
                        "contribution_label": contribution.label,
                        "resolved_force_N": (
                            relation.evaluate(sample.closure)
                        ),
                        "bias_force_N": relation.bias,
                    }
                    for unknown in ClosureUnknown:
                        c_row[
                            f"gain__{unknown.name.lower()}"
                        ] = relation.gains[unknown]
                    long_contrib.append(c_row)

        # Direct dynamic prediction deltas, same state and same closure values.
        row["primary_dynamic_correction_to_total_clamp_N"] = (
            row["primary_total_clamp__full_N"]
            - row[
                "primary_total_clamp__quasi_static_flyweight_N"
            ]
        )
        row["secondary_dynamic_correction_to_total_clamp_N"] = (
            row["secondary_total_clamp__full_N"]
            - row[
                "secondary_total_clamp__quasi_static_helix_N"
            ]
        )
        pden = row[
            "primary_total_clamp__quasi_static_flyweight_N"
        ]
        sden = row[
            "secondary_total_clamp__quasi_static_helix_N"
        ]
        row[
            "primary_dynamic_correction_pct_of_qs_total_clamp"
        ] = (
            100.0
            * row["primary_dynamic_correction_to_total_clamp_N"]
            / pden
            if abs(pden) > 1.0e-12
            else NAN
        )
        row[
            "secondary_dynamic_correction_pct_of_qs_total_clamp"
        ] = (
            100.0
            * row["secondary_dynamic_correction_to_total_clamp_N"]
            / sden
            if abs(sden) > 1.0e-12
            else NAN
        )

        # Carry the closed-form mechanism decomposition from the full sample
        # into the direct comparison file as an independent audit.
        for name in (
            "fly_qs_centrifugal_force_N",
            "fly_dynamic_axial_inertia_force_N",
            "fly_dynamic_curvature_force_N",
            "fly_dynamic_total_correction_N",
            "fly_dynamic_shaft_torque_correction_vs_constant_Nm",
            "helix_qs_reaction_force_N",
            "helix_dynamic_shaft_accel_force_N",
            "helix_dynamic_shift_accel_force_N",
            "helix_dynamic_curvature_force_N",
            "helix_dynamic_total_correction_N",
            "helix_dynamic_shaft_torque_correction_vs_constant_Nm",
            "helix_theta_ddot_rad_s2",
        ):
            row[name] = sample.row[name]

        rows.append(row)

    return rows, long_contrib


# ---------------------------------------------------------------------------
# Configuration-only generalized mass map
# ---------------------------------------------------------------------------


def effective_mass_map(
    results: list[VariantResult],
    points: int = 301,
) -> list[dict[str, Any]]:
    full = next(
        item for item in results
        if item.variant.key == "full"
    )
    full_model = full.system.cvt.model
    spec = full_model.geometry.spec

    shift_values = np.linspace(
        spec.deadzone_shift,
        spec.max_shift,
        points,
    )
    rows = []

    for shift_value in shift_values:
        geometry = full_model.geometry.evaluate_engaged(
            float(shift_value)
        )
        pcoord = geometry.primary_axial_coordinate
        scoord = geometry.secondary_axial_coordinate
        axial = full_model.inertias.axial_translation.evaluate(
            primary_axial_coordinate=pcoord,
            secondary_axial_coordinate=scoord,
            belt_axial_coordinate=geometry.belt_axial_coordinate,
        )
        base = (
            axial.primary.reflected_mass
            + axial.secondary.reflected_mass
            + axial.belt.reflected_mass
        )

        fly_law = _find_flyweight(
            full_model.primary_actuator
        )
        fw = fly_law.spec.mechanism_map.evaluate(
            pcoord.value
        )
        fly = (
            fw.pivot_inertia
            * (
                fw.angle_gradient
                * pcoord.d_value_ds
            ) ** 2
        )

        coupling = full_model.secondary_helical_coupling
        if coupling is None:
            raise RuntimeError("Secondary helix missing.")
        hk = coupling.evaluate_from_local_coordinate(
            axial_position=scoord.value,
            d_axial_position_ds=scoord.d_value_ds,
            d2_axial_position_ds2=scoord.d2_value_ds2,
        )
        helix = (
            SCVT_MOVABLE_SHEAVE_MOI_KG_M2
            * hk.dtheta_ds**2
        )

        full_total = base + fly + helix
        pct = (
            100.0
            * (float(shift_value) - spec.deadzone_shift)
            / (spec.max_shift - spec.deadzone_shift)
        )

        for item in results:
            active_fly = (
                fly if item.variant.dynamic_flyweight else 0.0
            )
            active_helix = (
                helix if item.variant.dynamic_helix else 0.0
            )
            total = base + active_fly + active_helix
            rows.append(
                {
                    "variant": item.variant.key,
                    "variant_label": item.variant.label,
                    "shift_m": float(shift_value),
                    "shift_mm": float(
                        shift_value / MILLIMETRE
                    ),
                    "engaged_shift_percent": pct,
                    "mass_primary_translation_kg": (
                        axial.primary.reflected_mass
                    ),
                    "mass_secondary_translation_kg": (
                        axial.secondary.reflected_mass
                    ),
                    "mass_belt_translation_kg": (
                        axial.belt.reflected_mass
                    ),
                    "mass_base_axial_total_kg": base,
                    "mass_flyweight_physical_candidate_kg": fly,
                    "mass_helix_physical_candidate_kg": helix,
                    "mass_flyweight_active_kg": active_fly,
                    "mass_helix_active_kg": active_helix,
                    "mass_total_direct_kg": total,
                    "mass_total_full_model_kg": full_total,
                    "same_force_acceleration_vs_full_percent": (
                        100.0 * full_total / total
                    ),
                    "same_force_acceleration_vs_axial_only_percent": (
                        100.0 * base / total
                    ),
                    "flyweight_share_of_active_total_percent": (
                        100.0 * active_fly / total
                    ),
                    "helix_share_of_active_total_percent": (
                        100.0 * active_helix / total
                    ),
                    "flyweight_q_prime_rad_per_m": (
                        fw.angle_gradient
                    ),
                    "flyweight_q_second_rad_per_m2": (
                        fw.angle_curvature
                    ),
                    "helix_dtheta_ds_rad_per_m": (
                        hk.dtheta_ds
                    ),
                    "secondary_dx_ds": scoord.d_value_ds,
                }
            )

    return rows


# ---------------------------------------------------------------------------
# Transitions / metrics
# ---------------------------------------------------------------------------


def transition_rows(
    result: VariantResult,
) -> list[dict[str, Any]]:
    rows = []
    segments = result.hybrid_result.segments

    for index, record in enumerate(
        result.hybrid_result.transitions
    ):
        pre = np.asarray(
            segments[index].state[:, -1],
            dtype=float,
        )
        post = np.asarray(
            record.post_transition_state,
            dtype=float,
        )
        pre_cvt = CVTState.from_vector(
            result.system.layout.view(pre, "cvt")
        )
        post_cvt = CVTState.from_vector(
            result.system.layout.view(post, "cvt")
        )

        rows.append(
            {
                "variant": result.variant.key,
                "variant_label": result.variant.label,
                "transition_index": index,
                "time_s": record.time,
                "previous_mode": str(record.previous_mode),
                "next_mode": str(
                    record.transition.next_mode
                ),
                "fired_events": "|".join(
                    record.fired_event_names
                ),
                "reason": record.transition.reason,
                "has_state_reset": (
                    record.transition.has_successor_state
                ),
                "pre_primary_rpm": (
                    pre_cvt.primary_angular_speed
                    * RPM_PER_RADIAN_PER_SECOND
                ),
                "post_primary_rpm": (
                    post_cvt.primary_angular_speed
                    * RPM_PER_RADIAN_PER_SECOND
                ),
                "delta_primary_rpm": (
                    (
                        post_cvt.primary_angular_speed
                        - pre_cvt.primary_angular_speed
                    )
                    * RPM_PER_RADIAN_PER_SECOND
                ),
                "pre_secondary_rpm": (
                    pre_cvt.secondary_angular_speed
                    * RPM_PER_RADIAN_PER_SECOND
                ),
                "post_secondary_rpm": (
                    post_cvt.secondary_angular_speed
                    * RPM_PER_RADIAN_PER_SECOND
                ),
                "pre_shift_mm": (
                    pre_cvt.shift_position / MILLIMETRE
                ),
                "post_shift_mm": (
                    post_cvt.shift_position / MILLIMETRE
                ),
                "delta_shift_mm": (
                    (
                        post_cvt.shift_position
                        - pre_cvt.shift_position
                    )
                    / MILLIMETRE
                ),
                "pre_shift_speed_mm_s": (
                    pre_cvt.shift_speed / MILLIMETRE
                ),
                "post_shift_speed_mm_s": (
                    post_cvt.shift_speed / MILLIMETRE
                ),
                "delta_shift_speed_mm_s": (
                    (
                        post_cvt.shift_speed
                        - pre_cvt.shift_speed
                    )
                    / MILLIMETRE
                ),
                "pre_belt_speed_m_s": pre_cvt.belt_speed,
                "post_belt_speed_m_s": post_cvt.belt_speed,
                "delta_belt_speed_m_s": (
                    post_cvt.belt_speed - pre_cvt.belt_speed
                ),
            }
        )
    return rows


def _finite_values(
    records: list[SampleRecord],
    key: str,
) -> np.ndarray:
    values = np.asarray(
        [float(item.row.get(key, NAN)) for item in records],
        dtype=float,
    )
    return values[np.isfinite(values)]


def compute_metrics(
    variant: AblationVariant,
    result,
    samples: list[SampleRecord],
    max_shift: float,
) -> dict[str, Any]:
    engaged = [
        sample
        for sample in samples
        if sample.closure is not None
    ]
    full_rows = [sample.row for sample in samples]

    shift_values = np.asarray(
        [row["shift_m"] for row in full_rows],
        dtype=float,
    )
    time_values = np.asarray(
        [row["time_s"] for row in full_rows],
        dtype=float,
    )
    full_indices = np.flatnonzero(
        shift_values >= max_shift - 0.20 * MILLIMETRE
    )
    time_to_full = (
        float(time_values[full_indices[0]])
        if full_indices.size
        else NAN
    )

    rpm = _finite_values(engaged, "primary_rpm")
    clamp_p = _finite_values(
        engaged,
        "primary_actuator_closing_force_N",
    )
    clamp_s = _finite_values(
        engaged,
        "secondary_actuator_closing_force_N",
    )
    normal_p = _finite_values(engaged, "normal_primary_N")
    normal_s = _finite_values(engaged, "normal_secondary_N")
    sddot = _finite_values(
        engaged,
        "rhs_shift_acceleration_m_s2",
    )

    return {
        "variant": variant.key,
        "variant_label": variant.label,
        "dynamic_flyweight": variant.dynamic_flyweight,
        "dynamic_helix": variant.dynamic_helix,
        "time_to_full_shift_s": time_to_full,
        "hybrid_transition_count": len(result.transitions),
        "engaged_sample_count": len(engaged),
        "primary_rpm_mean_engaged": (
            float(np.mean(rpm)) if rpm.size else NAN
        ),
        "primary_rpm_peak_engaged": (
            float(np.max(rpm)) if rpm.size else NAN
        ),
        "primary_clamp_mean_N": (
            float(np.mean(clamp_p)) if clamp_p.size else NAN
        ),
        "primary_clamp_peak_N": (
            float(np.max(clamp_p)) if clamp_p.size else NAN
        ),
        "secondary_clamp_mean_N": (
            float(np.mean(clamp_s)) if clamp_s.size else NAN
        ),
        "secondary_clamp_peak_N": (
            float(np.max(clamp_s)) if clamp_s.size else NAN
        ),
        "normal_primary_mean_N": (
            float(np.mean(normal_p)) if normal_p.size else NAN
        ),
        "normal_secondary_mean_N": (
            float(np.mean(normal_s)) if normal_s.size else NAN
        ),
        "max_abs_continuous_shift_acceleration_m_s2": (
            float(np.max(np.abs(sddot)))
            if sddot.size
            else NAN
        ),
    }


# ---------------------------------------------------------------------------
# Integration
# ---------------------------------------------------------------------------


def run_variant(
    *,
    variant: AblationVariant,
    full_assembly: CVTAssemblySpec,
    engine,
    road_load,
    constants,
    programme,
    duration_s: float,
    sample_step_s: float,
    rtol: float,
    atol: float,
    max_step_s: float,
) -> VariantResult:
    assembly = ablate_assembly(full_assembly, variant)
    system = build_system_from_assembly(
        assembly=assembly,
        engine=engine,
        road_load=road_load,
        constants=constants,
        programme=programme,
    )

    initial_cvt = route.launch_cvt_state(primary_rpm=1800.0)
    initial_full = system.initial_state(
        cvt_state=initial_cvt,
        host_state=system.host.initial_state(
            secondary_shaft_angle=0.0
        ),
    )
    result = integrate_hybrid(
        system=system,
        time_span=(0.0, duration_s),
        initial_state=initial_full,
        initial_mode=system.classify_initial_mode(
            initial_full
        ),
        settings=HybridIntegratorSettings(
            relative_tolerance=rtol,
            absolute_tolerance=atol,
            method="LSODA",
            max_step=max_step_s,
            maximum_transitions=150,
            retain_dense_output=True,
        ),
    )
    if not result.completed:
        raise RuntimeError(
            f"{variant.label} failed: "
            f"{result.termination_reason}"
        )

    samples, contributions = sample_variant(
        variant=variant,
        system=system,
        result=result,
        step_s=sample_step_s,
    )
    metrics = compute_metrics(
        variant,
        result,
        samples,
        system.cvt.model.geometry.spec.max_shift,
    )
    return VariantResult(
        variant=variant,
        assembly=assembly,
        system=system,
        hybrid_result=result,
        samples=samples,
        contribution_rows=contributions,
        metrics=metrics,
    )


# ---------------------------------------------------------------------------
# File writers
# ---------------------------------------------------------------------------


def _write_dict_rows(
    path: Path,
    rows: list[dict[str, Any]],
) -> None:
    if not rows:
        path.write_text("", encoding="utf-8")
        return

    fieldnames: list[str] = []
    seen: set[str] = set()
    for row in rows:
        for key in row:
            if key not in seen:
                seen.add(key)
                fieldnames.append(key)

    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=fieldnames,
            extrasaction="ignore",
        )
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def _manifest(
    *,
    candidate,
    constants,
    results: list[VariantResult],
    sample_step_s: float,
) -> dict[str, Any]:
    return {
        "study": "dynamic_actuator_ablation_rich",
        "sample_step_s": sample_step_s,
        "candidate": {
            "flyweight_mass_kg": candidate.flyweight_mass_kg,
            "helix_angle_degrees": candidate.helix_angle_degrees,
            "secondary_torsional_pretension_degrees": (
                candidate.secondary_torsional_pretension_degrees
            ),
            "secondary_compression_preload_mm": (
                candidate.secondary_compression_preload_mm
            ),
            "primary_ramp_kind": candidate.primary_ramp_kind,
            "primary_ramp_angle_degrees": (
                candidate.primary_ramp_angle_degrees
            ),
            "primary_ramp_start_angle_degrees": (
                candidate.primary_ramp_start_angle_degrees
            ),
            "primary_ramp_end_angle_degrees": (
                candidate.primary_ramp_end_angle_degrees
            ),
        },
        "inertia_reference": {
            "PCVT_total_CAD_kg_m2": PCVT_TOTAL_MOI_KG_M2,
            "SCVT_total_CAD_kg_m2": SCVT_TOTAL_MOI_KG_M2,
            "SCVT_movable_sheave_kg_m2": (
                SCVT_MOVABLE_SHEAVE_MOI_KG_M2
            ),
            "engine_boundary_kg_m2": (
                constants.engine_rotational_inertia
            ),
            "secondary_downstream_boundary_kg_m2": (
                constants.gearbox_input_rotational_inertia
            ),
            "final_drive_ratio": constants.final_drive_ratio,
        },
        "direct_prediction_method": (
            "All variant actuator force relations are evaluated on the same "
            "full-model state and the same full-model ClosureUnknowns. "
            "This isolates constitutive/mechanism prediction differences "
            "from trajectory feedback."
        ),
        "full_dynamic_flyweight": {
            "quasi_static_force": "0.5 * omega_p^2 * J_f'(x_p)",
            "dynamic_axial_inertia": "-I_f * q_f'^2 * x_p_ddot",
            "dynamic_curvature": (
                "-I_f * q_f' * q_f'' * x_p_dot^2"
            ),
            "shaft_correction_relative_to_constant_CAD": (
                "-(J_f(q)-J_f(0))*alpha_p "
                "- J_f'(x_p)*x_p_dot*omega_p"
            ),
        },
        "full_dynamic_helix": {
            "quasi_static_reacted_torque": (
                "tau_s/2 + k_theta*(theta_pre-theta)"
            ),
            "quasi_static_force": (
                "[tau_s/2 + k_theta*(theta_pre-theta)] "
                "* dtheta/dx_s"
            ),
            "dynamic_clamp_correction": (
                "-I_M*(alpha_s + theta_ddot)*dtheta/dx_s"
            ),
            "theta_ddot": (
                "(dtheta/ds)*s_ddot "
                "+ (d2theta/ds2)*s_dot^2"
            ),
            "shaft_correction_relative_to_constant_CAD": (
                "-I_M*theta_ddot"
            ),
        },
        "variants": [
            {
                "key": item.variant.key,
                "label": item.variant.label,
                "dynamic_flyweight": (
                    item.variant.dynamic_flyweight
                ),
                "dynamic_helix": item.variant.dynamic_helix,
            }
            for item in results
        ],
    }


# ---------------------------------------------------------------------------
# Plot helpers
# ---------------------------------------------------------------------------


def _array(
    rows: list[dict[str, Any]],
    key: str,
) -> np.ndarray:
    return np.asarray(
        [float(row.get(key, NAN)) for row in rows],
        dtype=float,
    )


def _engaged_rows(result: VariantResult):
    return [
        sample.row
        for sample in result.samples
        if sample.closure is not None
    ]


def _plot_direct_clamp(
    direct_rows: list[dict[str, Any]],
    output_dir: Path,
) -> None:
    t = _array(direct_rows, "time_s")

    # Primary direct prediction.
    fig1, (ax11, ax12) = plt.subplots(
        2,
        1,
        figsize=(10.5, 7.5),
        sharex=True,
        constrained_layout=True,
    )
    ax11.plot(
        t,
        _array(
            direct_rows,
            "primary_total_clamp__full_N",
        ),
        label="Full dynamic",
    )
    ax11.plot(
        t,
        _array(
            direct_rows,
            "primary_total_clamp__quasi_static_flyweight_N",
        ),
        linestyle="--",
        label="QS flyweight",
    )
    ax11.set_ylabel("Primary actuator clamp [N]")
    ax11.set_title(
        "Direct primary clamp prediction on identical operating points"
    )
    ax11.legend()
    ax11.grid(True, alpha=0.25)

    ax12.plot(
        t,
        _array(
            direct_rows,
            "fly_dynamic_axial_inertia_force_N",
        ),
        label="pivot acceleration term",
    )
    ax12.plot(
        t,
        _array(
            direct_rows,
            "fly_dynamic_curvature_force_N",
        ),
        label="q'' shift-speed term",
    )
    ax12.plot(
        t,
        _array(
            direct_rows,
            "primary_dynamic_correction_to_total_clamp_N",
        ),
        linewidth=2.0,
        label="total dynamic correction",
    )
    ax12.axhline(0.0, linewidth=0.8)
    ax12.set_xlabel("Time [s]")
    ax12.set_ylabel("Difference from QS [N]")
    ax12.legend()
    ax12.grid(True, alpha=0.25)
    fig1.savefig(
        output_dir / "01_direct_primary_clamp_prediction.png",
        dpi=180,
    )

    # Secondary direct prediction.
    fig2, (ax21, ax22) = plt.subplots(
        2,
        1,
        figsize=(10.5, 7.5),
        sharex=True,
        constrained_layout=True,
    )
    ax21.plot(
        t,
        _array(
            direct_rows,
            "secondary_total_clamp__full_N",
        ),
        label="Full dynamic",
    )
    ax21.plot(
        t,
        _array(
            direct_rows,
            "secondary_total_clamp__quasi_static_helix_N",
        ),
        linestyle="--",
        label="QS helix",
    )
    ax21.set_ylabel("Secondary actuator clamp [N]")
    ax21.set_title(
        "Direct secondary clamp prediction on identical operating points"
    )
    ax21.legend()
    ax21.grid(True, alpha=0.25)

    ax22.plot(
        t,
        _array(
            direct_rows,
            "helix_dynamic_shaft_accel_force_N",
        ),
        label=r"$-I_M\alpha_s\,d\theta/dx_s$",
    )
    ax22.plot(
        t,
        _array(
            direct_rows,
            "helix_dynamic_shift_accel_force_N",
        ),
        label=r"$-I_M H\ddot{s}\,d\theta/dx_s$",
    )
    ax22.plot(
        t,
        _array(
            direct_rows,
            "helix_dynamic_curvature_force_N",
        ),
        label=r"$-I_M H'\dot{s}^2\,d\theta/dx_s$",
    )
    ax22.plot(
        t,
        _array(
            direct_rows,
            "secondary_dynamic_correction_to_total_clamp_N",
        ),
        linewidth=2.0,
        label="total dynamic correction",
    )
    ax22.axhline(0.0, linewidth=0.8)
    ax22.set_xlabel("Time [s]")
    ax22.set_ylabel("Difference from QS [N]")
    ax22.legend(fontsize=8)
    ax22.grid(True, alpha=0.25)
    fig2.savefig(
        output_dir / "02_direct_secondary_clamp_prediction.png",
        dpi=180,
    )


def _plot_effective_mass(
    mass_rows: list[dict[str, Any]],
    output_dir: Path,
) -> None:
    full_rows = [
        row for row in mass_rows
        if row["variant"] == "full"
    ]
    x = _array(full_rows, "engaged_shift_percent")

    fig, (ax1, ax2) = plt.subplots(
        2,
        1,
        figsize=(10.5, 7.8),
        sharex=True,
        constrained_layout=True,
    )
    ax1.stackplot(
        x,
        _array(full_rows, "mass_primary_translation_kg"),
        _array(full_rows, "mass_secondary_translation_kg"),
        _array(full_rows, "mass_belt_translation_kg"),
        _array(full_rows, "mass_flyweight_active_kg"),
        _array(full_rows, "mass_helix_active_kg"),
        labels=(
            "primary translation",
            "secondary translation",
            "belt translation",
            "flyweight pivot rotation",
            "secondary helix rotation",
        ),
        alpha=0.82,
    )
    ax1.set_ylabel(r"Generalized $M_{ss}$ [kg]")
    ax1.set_title(
        "Full-model direct generalized shift-inertia composition"
    )
    ax1.legend(fontsize=8, ncols=2)
    ax1.grid(True, alpha=0.25)

    for key, label in (
        ("full", "Full dynamic"),
        ("quasi_static_flyweight", "QS flyweight"),
        ("quasi_static_helix", "QS helix"),
        ("fully_quasi_static", "Fully quasi-static"),
    ):
        rows = [row for row in mass_rows if row["variant"] == key]
        ax2.plot(
            _array(rows, "engaged_shift_percent"),
            _array(rows, "mass_total_direct_kg"),
            label=label,
        )
    ax2.set_xlabel("Engaged shift travel [%]")
    ax2.set_ylabel(r"Direct generalized $M_{ss}$ [kg]")
    ax2.set_title(
        "Effective-mass prediction of each model"
    )
    ax2.legend()
    ax2.grid(True, alpha=0.25)
    fig.savefig(
        output_dir / "03_effective_mass_predictions.png",
        dpi=180,
    )


def _plot_actual_clamp_and_normal(
    results: list[VariantResult],
    output_dir: Path,
) -> None:
    fig1, (ax11, ax12) = plt.subplots(
        2,
        1,
        figsize=(10.5, 7.5),
        sharex=True,
        constrained_layout=True,
    )
    for item in results:
        rows = _engaged_rows(item)
        ax11.plot(
            _array(rows, "time_s"),
            _array(rows, "primary_actuator_closing_force_N"),
            label=item.variant.label,
        )
        ax12.plot(
            _array(rows, "time_s"),
            _array(rows, "secondary_actuator_closing_force_N"),
            label=item.variant.label,
        )
    ax11.set_ylabel("Primary actuator clamp [N]")
    ax11.set_title(
        "Actual clamp prediction on each model's own trajectory"
    )
    ax11.legend(fontsize=8)
    ax11.grid(True, alpha=0.25)
    ax12.set_xlabel("Time [s]")
    ax12.set_ylabel("Secondary actuator clamp [N]")
    ax12.legend(fontsize=8)
    ax12.grid(True, alpha=0.25)
    fig1.savefig(
        output_dir / "04_actual_actuator_clamp_trajectories.png",
        dpi=180,
    )

    fig2, (ax21, ax22) = plt.subplots(
        2,
        1,
        figsize=(10.5, 7.5),
        sharex=True,
        constrained_layout=True,
    )
    for item in results:
        rows = _engaged_rows(item)
        ax21.plot(
            _array(rows, "time_s"),
            _array(rows, "normal_primary_N"),
            label=item.variant.label,
        )
        ax22.plot(
            _array(rows, "time_s"),
            _array(rows, "normal_secondary_N"),
            label=item.variant.label,
        )
    ax21.set_ylabel(r"$N_p$ [N]")
    ax21.set_title(
        "Solved belt-contact normal resultants"
    )
    ax21.legend(fontsize=8)
    ax21.grid(True, alpha=0.25)
    ax22.set_xlabel("Time [s]")
    ax22.set_ylabel(r"$N_s$ [N]")
    ax22.legend(fontsize=8)
    ax22.grid(True, alpha=0.25)
    fig2.savefig(
        output_dir / "05_contact_normal_force_trajectories.png",
        dpi=180,
    )


def _plot_trajectory(
    results: list[VariantResult],
    output_dir: Path,
) -> None:
    fig1, (ax11, ax12) = plt.subplots(
        2,
        1,
        figsize=(10.5, 7.5),
        sharex=True,
        constrained_layout=True,
    )
    for item in results:
        rows = [sample.row for sample in item.samples]
        ax11.plot(
            _array(rows, "time_s"),
            _array(rows, "primary_rpm"),
            label=item.variant.label,
        )
        ax12.plot(
            _array(rows, "time_s"),
            _array(rows, "shift_mm"),
            label=item.variant.label,
        )
    ax11.axhline(
        3200.0,
        linestyle="--",
        linewidth=1.0,
        label="3200 rpm",
    )
    ax11.set_ylabel("Primary speed [rpm]")
    ax11.set_title("Trajectory consequence")
    ax11.legend(fontsize=8)
    ax11.grid(True, alpha=0.25)
    ax12.set_xlabel("Time [s]")
    ax12.set_ylabel("Shift [mm]")
    ax12.legend(fontsize=8)
    ax12.grid(True, alpha=0.25)
    fig1.savefig(
        output_dir / "06_rpm_and_shift_consequence.png",
        dpi=180,
    )

    # Engagement zoom uses actual continuous RHS acceleration; no finite
    # differencing across hybrid resets.
    first_transition_times = [
        record.time
        for item in results
        for record in item.hybrid_result.transitions
    ]
    zoom_end = (
        min(0.30, max(first_transition_times) + 0.03)
        if first_transition_times
        else 0.30
    )
    fig2, (ax21, ax22) = plt.subplots(
        2,
        1,
        figsize=(10.5, 7.5),
        sharex=True,
        constrained_layout=True,
    )
    for item in results:
        rows = [
            sample.row
            for sample in item.samples
            if sample.time <= zoom_end
        ]
        ax21.plot(
            _array(rows, "time_s"),
            _array(rows, "shift_speed_mm_s"),
            label=item.variant.label,
        )
        ax22.plot(
            _array(rows, "time_s"),
            _array(rows, "rhs_shift_acceleration_m_s2"),
            label=item.variant.label,
        )
    ax21.set_ylabel("Shift speed [mm/s]")
    ax21.set_title(
        "Engagement transient: where mechanism inertia matters"
    )
    ax21.legend(fontsize=8)
    ax21.grid(True, alpha=0.25)
    ax22.set_xlabel("Time [s]")
    ax22.set_ylabel(r"Continuous $\ddot{s}$ [m/s$^2$]")
    ax22.legend(fontsize=8)
    ax22.grid(True, alpha=0.25)
    fig2.savefig(
        output_dir / "07_engagement_transient_consequence.png",
        dpi=180,
    )


def _plot_direct_percent(
    direct_rows: list[dict[str, Any]],
    output_dir: Path,
) -> None:
    t = _array(direct_rows, "time_s")
    fig, (ax1, ax2) = plt.subplots(
        2,
        1,
        figsize=(10.5, 7.2),
        sharex=True,
        constrained_layout=True,
    )
    ax1.plot(
        t,
        _array(
            direct_rows,
            "primary_dynamic_correction_pct_of_qs_total_clamp",
        ),
    )
    ax1.axhline(0.0, linewidth=0.8)
    ax1.set_ylabel("Flyweight dynamic correction [%]")
    ax1.set_title(
        "Dynamic clamp correction as a fraction of quasi-static total clamp"
    )
    ax1.grid(True, alpha=0.25)

    ax2.plot(
        t,
        _array(
            direct_rows,
            "secondary_dynamic_correction_pct_of_qs_total_clamp",
        ),
    )
    ax2.axhline(0.0, linewidth=0.8)
    ax2.set_xlabel("Time [s]")
    ax2.set_ylabel("Helix dynamic correction [%]")
    ax2.grid(True, alpha=0.25)
    fig.savefig(
        output_dir / "08_dynamic_clamp_correction_percent.png",
        dpi=180,
    )


# ---------------------------------------------------------------------------
# Main output orchestration
# ---------------------------------------------------------------------------


def write_outputs(
    *,
    results: list[VariantResult],
    direct_rows: list[dict[str, Any]],
    counterfactual_contrib: list[dict[str, Any]],
    mass_rows: list[dict[str, Any]],
    candidate,
    constants,
    sample_step_s: float,
    output_dir: Path,
    no_show: bool,
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)

    trajectory_rows = [
        sample.row
        for item in results
        for sample in item.samples
    ]
    contribution_rows = [
        row
        for item in results
        for row in item.contribution_rows
    ]
    transitions = [
        row
        for item in results
        for row in transition_rows(item)
    ]
    summaries = [item.metrics for item in results]

    _write_dict_rows(
        output_dir / "trajectory_diagnostics.csv",
        trajectory_rows,
    )
    _write_dict_rows(
        output_dir / "actuator_contributions.csv",
        contribution_rows,
    )
    _write_dict_rows(
        output_dir / "direct_clamp_on_full_trajectory.csv",
        direct_rows,
    )
    _write_dict_rows(
        output_dir
        / "direct_counterfactual_contributions.csv",
        counterfactual_contrib,
    )
    _write_dict_rows(
        output_dir / "effective_mass_map.csv",
        mass_rows,
    )
    _write_dict_rows(
        output_dir / "hybrid_transitions.csv",
        transitions,
    )
    _write_dict_rows(
        output_dir / "summary.csv",
        summaries,
    )
    (output_dir / "summary.json").write_text(
        json.dumps(summaries, indent=2, allow_nan=True)
        + "\n",
        encoding="utf-8",
    )
    (output_dir / "model_manifest.json").write_text(
        json.dumps(
            _manifest(
                candidate=candidate,
                constants=constants,
                results=results,
                sample_step_s=sample_step_s,
            ),
            indent=2,
            allow_nan=True,
        )
        + "\n",
        encoding="utf-8",
    )

    _plot_direct_clamp(direct_rows, output_dir)
    _plot_effective_mass(mass_rows, output_dir)
    _plot_actual_clamp_and_normal(results, output_dir)
    _plot_trajectory(results, output_dir)
    _plot_direct_percent(direct_rows, output_dir)

    print()
    print("RICH DYNAMIC ACTUATOR ABLATION")
    print("=" * 86)
    for item in results:
        m = item.metrics
        print(
            f"{item.variant.label:20s} | "
            f"full shift={m['time_to_full_shift_s']!s:>8} s | "
            f"transitions={m['hybrid_transition_count']:>3} | "
            f"mean P clamp={m['primary_clamp_mean_N']!s:>10} N | "
            f"mean S clamp={m['secondary_clamp_mean_N']!s:>10} N"
        )

    if direct_rows:
        fly_pct = _array(
            direct_rows,
            "primary_dynamic_correction_pct_of_qs_total_clamp",
        )
        helix_pct = _array(
            direct_rows,
            "secondary_dynamic_correction_pct_of_qs_total_clamp",
        )
        fly_pct = fly_pct[np.isfinite(fly_pct)]
        helix_pct = helix_pct[np.isfinite(helix_pct)]
        if fly_pct.size:
            print(
                "max |flyweight dynamic clamp correction| = "
                f"{np.max(np.abs(fly_pct)):.4g}% of QS total primary clamp"
            )
        if helix_pct.size:
            print(
                "max |helix dynamic clamp correction| = "
                f"{np.max(np.abs(helix_pct)):.4g}% of QS total secondary clamp"
            )

    print()
    print(f"Wrote rich dataset and figures to {output_dir}")

    if no_show:
        plt.close("all")
    else:
        plt.show()


def main() -> None:
    args = parse_args()
    if (
        not isfinite(args.sample_step_s)
        or args.sample_step_s <= 0.0
    ):
        raise ValueError(
            "--sample-step-s must be finite and positive."
        )

    programme, duration_s = programme_for_scenario(
        args.scenario,
        args.duration_s,
    )
    preset = (
        HERE
        / "presets"
        / "circular_traction_first_reference.json"
    )
    candidate = route.load_candidate(preset)
    resolved = route.resolve_primary_preload(
        candidate,
        target_engagement_rpm=2000.0,
        programme=programme,
    )
    full_assembly, engine, road_load = route.build_components(
        resolved.constants
    )

    results: list[VariantResult] = []
    for variant in VARIANTS:
        print(f"Running {variant.label}...")
        results.append(
            run_variant(
                variant=variant,
                full_assembly=full_assembly,
                engine=engine,
                road_load=road_load,
                constants=resolved.constants,
                programme=programme,
                duration_s=duration_s,
                sample_step_s=args.sample_step_s,
                rtol=args.rtol,
                atol=args.atol,
                max_step_s=args.max_step_s,
            )
        )

    direct_rows, counterfactual_contrib = (
        direct_prediction_on_full_trajectory(results)
    )
    mass_rows = effective_mass_map(results)

    write_outputs(
        results=results,
        direct_rows=direct_rows,
        counterfactual_contrib=counterfactual_contrib,
        mass_rows=mass_rows,
        candidate=candidate,
        constants=resolved.constants,
        sample_step_s=args.sample_step_s,
        output_dir=args.output_dir,
        no_show=args.no_show,
    )


if __name__ == "__main__":
    main()
