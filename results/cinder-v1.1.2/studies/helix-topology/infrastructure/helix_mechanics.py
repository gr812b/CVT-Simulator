"""Helix-study-local mechanics adapter for CINDER v1.1.2.

Only the mechanics required by helix-topology live here: full dynamic helix
sampling, the quasi-static helix counterfactual, transition reporting, and the
inspection fields used by the study. Shared Baja/reference definitions remain
under defaults/.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any

import numpy as np

from cinder.execution.hybrid.composed import ComposedCVTHybridSystem
from cinder.execution.hybrid.cvt_regime import CVTEngagementState
from cinder.model.cvt.actuation import (
    FixedPivotFlyweightForce,
    HelicalTorqueReactionForce,
    PulleyActuator,
    PulleyActuationContext,
)
from cinder.model.cvt.actuation.types import ActuationContribution, PulleyElementContribution
from cinder.model.cvt.closure import AffineClosureScalar, ClosureGains, ClosureUnknown, ClosureUnknowns
from cinder.model.cvt.inertia import ResolvedSecondaryInertia, SecondaryFixedInertia
from cinder.model.system import CVTAssemblySpec, CVTState, MechanicalCVTPlant, PulleyPairSpec, PulleySpec
from cinder.results.inspection import inspect_cvt_state
from defaults.reference_model.slotted_helix import BILATERAL_TOPOLOGY

RPM_PER_RADIAN_PER_SECOND = 60.0 / (2.0 * np.pi)
MILLIMETRE = 1.0e-3
NAN = float("nan")
SCVT_TOTAL_MOI_KG_M2 = 0.00484016
SCVT_MOVABLE_SHEAVE_MOI_KG_M2 = 0.0025139


class QuasiStaticHelicalTorqueReactionForce(HelicalTorqueReactionForce):
    """Classical torque-reactive helix with no dynamic movable-member term."""

    contact_topology = BILATERAL_TOPOLOGY

    compressive_contact_margin = None
    has_compressive_contact = None

    def evaluate(
        self,
        context: PulleyActuationContext,
    ) -> AffineClosureScalar:
        coupling = context.helical_coupling
        channels = context.closure_channels
        if coupling is None:
            raise ValueError("Quasi-static helix requires helical coupling.")
        if channels is None:
            raise ValueError("Quasi-static helix requires closure channels.")

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
                        motion_ratio * self.spec.movable_member_torque_fraction
                    )
                }
            ),
        )

    def evaluate_element(
        self,
        context: PulleyActuationContext,
    ) -> PulleyElementContribution:
        return PulleyElementContribution.from_closing_force(self.evaluate(context))

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
                relation=AffineClosureScalar.constant(motion_ratio * spring_torque),
            ),
            ActuationContribution(
                key="quasi_static_helix_reacted_belt_torque",
                label="Quasi-static helix reacted belt torque",
                relation=AffineClosureScalar(
                    gains=ClosureGains.from_by_unknown(
                        {
                            channels.shaft_torque: (
                                motion_ratio * self.spec.movable_member_torque_fraction
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
        key="quasi_static_helix",
        label="QS helix",
        dynamic_flyweight=True,
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
                law if dynamic else QuasiStaticHelicalTorqueReactionForce(spec=law.spec)
            )
        else:
            laws.append(law)
    if found != 1:
        raise RuntimeError("Expected exactly one helix force law; " f"found {found}.")
    return PulleyActuator(*laws)


def ablate_assembly(full: CVTAssemblySpec, variant: AblationVariant) -> CVTAssemblySpec:
    """Apply the helix-only dynamic ablation used by this study."""
    if not variant.dynamic_flyweight:
        raise ValueError(
            "helix-topology supports only full and quasi_static_helix variants"
        )
    if variant.dynamic_helix:
        return full

    secondary_actuator = _replace_helix_law(
        full.pulleys.secondary.actuator,
        dynamic=False,
    )
    secondary_inertia = full.inertias.secondary
    fixed_total = (
        secondary_inertia.fixed_side.total
        + secondary_inertia.movable_sheave_rotational_inertia
    )
    if abs(fixed_total - SCVT_TOTAL_MOI_KG_M2) > 1.0e-10:
        raise RuntimeError(
            "Current secondary fixed + movable inertia does not recover the frozen SCVT CAD total."
        )
    reduced_secondary_inertia = ResolvedSecondaryInertia(
        fixed_side=SecondaryFixedInertia(fixed_rotating_hardware_inertia=fixed_total),
        movable_sheave_rotational_inertia=0.0,
    )
    return replace(
        full,
        pulleys=PulleyPairSpec(
            primary=full.pulleys.primary,
            secondary=PulleySpec(
                actuator=secondary_actuator,
                helical_coupling=full.pulleys.secondary.helical_coupling,
            ),
        ),
        inertias=replace(full.inertias, secondary=reduced_secondary_inertia),
    )


def _mode_name(value: object) -> str:
    name = getattr(value, "name", None)
    return str(name if name is not None else value)


def _find_flyweight(actuator: PulleyActuator):
    laws = [
        law for law in actuator.force_laws if isinstance(law, FixedPivotFlyweightForce)
    ]
    if len(laws) != 1:
        raise RuntimeError(f"Expected one flyweight law; found {len(laws)}.")
    return laws[0]


def _find_helix(actuator: PulleyActuator):
    laws = [
        law
        for law in actuator.force_laws
        if isinstance(law, HelicalTorqueReactionForce)
    ]
    if len(laws) != 1:
        raise RuntimeError(f"Expected one helix law; found {len(laws)}.")
    return laws[0]


def _geometry_for_mode(
    model: MechanicalCVTPlant,
    state: CVTState,
    composed_mode,
):
    if composed_mode.cvt.engagement is CVTEngagementState.ENGAGED:
        return model.geometry.evaluate_engaged(state.shift_position)
    return model.geometry.evaluate_deadzone(state.shift_position)


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
        "alpha_primary_rad_s2": (closure.primary_angular_acceleration),
        "alpha_secondary_rad_s2": (closure.secondary_angular_acceleration),
        "belt_acceleration_closure_m_s2": (closure.belt_acceleration),
        "shift_acceleration_closure_m_s2": (closure.shift_acceleration),
        "tau_primary_belt_Nm": closure.primary_torque,
        "tau_secondary_belt_Nm": closure.secondary_torque,
        "normal_primary_N": (closure.primary_normal_resultant),
        "normal_secondary_N": (closure.secondary_normal_resultant),
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
            row[f"gain__{unknown.name.lower()}"] = relation.gains[unknown]
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
    )
    base_mass = axial.primary.reflected_mass + axial.secondary.reflected_mass

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
    helix_mass = SCVT_MOVABLE_SHEAVE_MOI_KG_M2 * hk.dtheta_ds**2

    result = {
        "mass_primary_translation_kg": (axial.primary.reflected_mass),
        "mass_secondary_translation_kg": (axial.secondary.reflected_mass),
        "mass_base_axial_total_kg": base_mass,
        "mass_flyweight_reflected_candidate_kg": fly_mass,
        "mass_helix_reflected_candidate_kg": helix_mass,
        "flyweight_q_rad": fw.angle,
        "flyweight_q_prime_rad_per_m": fw.angle_gradient,
        "flyweight_q_second_rad_per_m2": fw.angle_curvature,
        "flyweight_pivot_inertia_kg_m2": fw.pivot_inertia,
        "flyweight_shaft_inertia_kg_m2": fw.shaft_inertia,
        "flyweight_shaft_inertia_gradient_kg_m": (fw.shaft_inertia_gradient),
        "helix_theta_rad": hk.theta,
        "helix_dtheta_ds_rad_per_m": hk.dtheta_ds,
        "helix_d2theta_ds2_rad_per_m2": hk.d2theta_ds2,
        "helix_dtheta_dopening_rad_per_m": (hk.dtheta_dopening),
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
    xddot_p = pcoord.d_value_ds * sddot + pcoord.d2_value_ds2 * sdot**2
    fly_qs = 0.5 * state.primary_angular_speed**2 * fw.shaft_inertia_gradient
    fly_axial = -fw.pivot_inertia * fw.angle_gradient**2 * xddot_p
    fly_curvature = (
        -fw.pivot_inertia * fw.angle_gradient * fw.angle_curvature * xdot_p**2
    )
    fly_delta = fly_axial + fly_curvature
    j0 = fly_law.spec.mechanism_map.evaluate(0.0).shaft_inertia
    fly_shaft_delta = (
        -(fw.shaft_inertia - j0) * closure.primary_angular_acceleration
        - fw.shaft_inertia_gradient * xdot_p * state.primary_angular_speed
    )

    helix_law = _find_helix(model.secondary_actuator)
    opening_gain = coupling.opening_per_axial_position
    dtheta_dx = hk.dtheta_dopening * opening_gain
    theta_ddot = hk.dtheta_ds * sddot + hk.d2theta_ds2 * sdot**2
    spring_torque = helix_law.spec.torsional_stiffness * (
        helix_law.spec.initial_twist - hk.theta
    )
    qs_helix_torque = (
        helix_law.spec.movable_member_torque_fraction * closure.secondary_torque
        + spring_torque
    )
    helix_qs_force = dtheta_dx * qs_helix_torque
    helix_shaft_accel_force = (
        -dtheta_dx
        * SCVT_MOVABLE_SHEAVE_MOI_KG_M2
        * closure.secondary_angular_acceleration
    )
    helix_shift_accel_force = (
        -dtheta_dx * SCVT_MOVABLE_SHEAVE_MOI_KG_M2 * hk.dtheta_ds * sddot
    )
    helix_curvature_force = (
        -dtheta_dx * SCVT_MOVABLE_SHEAVE_MOI_KG_M2 * hk.d2theta_ds2 * sdot**2
    )
    helix_delta = (
        helix_shaft_accel_force + helix_shift_accel_force + helix_curvature_force
    )
    helix_shaft_delta = -SCVT_MOVABLE_SHEAVE_MOI_KG_M2 * theta_ddot

    result.update(
        {
            "fly_qs_centrifugal_force_N": fly_qs,
            "fly_dynamic_axial_inertia_force_N": fly_axial,
            "fly_dynamic_curvature_force_N": fly_curvature,
            "fly_dynamic_total_correction_N": fly_delta,
            "fly_full_force_N": fly_qs + fly_delta,
            "fly_dynamic_correction_pct_of_qs_force": (
                100.0 * fly_delta / fly_qs if abs(fly_qs) > 1.0e-12 else NAN
            ),
            "fly_dynamic_shaft_torque_correction_vs_constant_Nm": (fly_shaft_delta),
            "helix_qs_reaction_force_N": helix_qs_force,
            "helix_dynamic_shaft_accel_force_N": (helix_shaft_accel_force),
            "helix_dynamic_shift_accel_force_N": (helix_shift_accel_force),
            "helix_dynamic_curvature_force_N": (helix_curvature_force),
            "helix_dynamic_total_correction_N": helix_delta,
            "helix_full_reaction_force_N": (helix_qs_force + helix_delta),
            "helix_dynamic_correction_pct_of_qs_force": (
                100.0 * helix_delta / helix_qs_force
                if abs(helix_qs_force) > 1.0e-12
                else NAN
            ),
            "helix_dynamic_shaft_torque_correction_vs_constant_Nm": (helix_shaft_delta),
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
                        "segment_end" if local_index == len(times) - 1 else "interior"
                    )
                ),
                "segment_has_event": bool(segment.fired_event_names),
                "segment_event_names": "|".join(segment.fired_event_names),
                "mode": str(mode),
                "cvt_mode": str(mode.cvt),
                "engagement_state": _mode_name(mode.cvt.engagement),
                "primary_omega_rad_s": (cvt_state.primary_angular_speed),
                "primary_rpm": (
                    cvt_state.primary_angular_speed * RPM_PER_RADIAN_PER_SECOND
                ),
                "secondary_omega_rad_s": (cvt_state.secondary_angular_speed),
                "secondary_rpm": (
                    cvt_state.secondary_angular_speed * RPM_PER_RADIAN_PER_SECOND
                ),
                "belt_speed_m_s": cvt_state.belt_speed,
                "shift_m": cvt_state.shift_position,
                "shift_mm": (cvt_state.shift_position / MILLIMETRE),
                "shift_speed_m_s": cvt_state.shift_speed,
                "shift_speed_mm_s": (cvt_state.shift_speed / MILLIMETRE),
                # Continuous RHS values: no numerical differentiation.
                "rhs_alpha_primary_rad_s2": float(cvt_rhs[0]),
                "rhs_alpha_secondary_rad_s2": float(cvt_rhs[1]),
                "rhs_belt_acceleration_m_s2": float(cvt_rhs[2]),
                "rhs_shift_speed_m_s": float(cvt_rhs[3]),
                "rhs_shift_acceleration_m_s2": float(cvt_rhs[4]),
                "primary_external_torque_Nm": (boundaries.primary.external_torque),
                "primary_boundary_inertia_kg_m2": (
                    boundaries.primary.equivalent_inertia
                ),
                "secondary_external_torque_Nm": (boundaries.secondary.external_torque),
                "secondary_boundary_inertia_kg_m2": (
                    boundaries.secondary.equivalent_inertia
                ),
                "ratio_secondary_over_primary": (
                    inspection.geometry.effective_ratio_secondary_over_primary
                ),
                "primary_effective_radius_m": (inspection.geometry.primary.effective),
                "secondary_effective_radius_m": (
                    inspection.geometry.secondary.effective
                ),
                "primary_wrap_rad": (inspection.geometry.primary_wrap_angle),
                "secondary_wrap_rad": (inspection.geometry.secondary_wrap_angle),
                "primary_axial_x_m": (geometry.primary_axial_coordinate.value),
                "primary_dx_ds": (geometry.primary_axial_coordinate.d_value_ds),
                "primary_d2x_ds2_per_m": (
                    geometry.primary_axial_coordinate.d2_value_ds2
                ),
                "secondary_axial_x_m": (geometry.secondary_axial_coordinate.value),
                "secondary_dx_ds": (geometry.secondary_axial_coordinate.d_value_ds),
                "secondary_d2x_ds2_per_m": (
                    geometry.secondary_axial_coordinate.d2_value_ds2
                ),
                "belt_axial_x_m": (geometry.belt_axial_coordinate.value),
                "belt_dx_ds": (geometry.belt_axial_coordinate.d_value_ds),
                "belt_d2x_ds2_per_m": (geometry.belt_axial_coordinate.d2_value_ds2),
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
                primary_total = inspection.primary_actuation.resolve_total(closure)
                secondary_total = (
                    inspection.secondary_actuation.resolve_total(closure)
                    if inspection.secondary_actuation is not None
                    else NAN
                )
                row["primary_actuator_closing_force_N"] = primary_total
                row["secondary_actuator_closing_force_N"] = secondary_total

                contact = inspection.contact
                if contact is not None:
                    traction = contact.traction_utilization
                    row["lambda_primary"] = traction.primary_lambda
                    row["lambda_secondary"] = traction.secondary_lambda
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


def transition_rows(
    result: VariantResult,
) -> list[dict[str, Any]]:
    rows = []
    segments = result.hybrid_result.segments

    for index, record in enumerate(result.hybrid_result.transitions):
        pre = np.asarray(
            segments[index].state[:, -1],
            dtype=float,
        )
        post = np.asarray(
            record.post_transition_state,
            dtype=float,
        )
        pre_cvt = CVTState.from_vector(result.system.layout.view(pre, "cvt"))
        post_cvt = CVTState.from_vector(result.system.layout.view(post, "cvt"))

        rows.append(
            {
                "variant": result.variant.key,
                "variant_label": result.variant.label,
                "transition_index": index,
                "time_s": record.time,
                "previous_mode": str(record.previous_mode),
                "next_mode": str(record.transition.next_mode),
                "fired_events": "|".join(record.fired_event_names),
                "reason": record.transition.reason,
                "has_state_reset": (record.transition.has_successor_state),
                "pre_primary_rpm": (
                    pre_cvt.primary_angular_speed * RPM_PER_RADIAN_PER_SECOND
                ),
                "post_primary_rpm": (
                    post_cvt.primary_angular_speed * RPM_PER_RADIAN_PER_SECOND
                ),
                "delta_primary_rpm": (
                    (post_cvt.primary_angular_speed - pre_cvt.primary_angular_speed)
                    * RPM_PER_RADIAN_PER_SECOND
                ),
                "pre_secondary_rpm": (
                    pre_cvt.secondary_angular_speed * RPM_PER_RADIAN_PER_SECOND
                ),
                "post_secondary_rpm": (
                    post_cvt.secondary_angular_speed * RPM_PER_RADIAN_PER_SECOND
                ),
                "pre_shift_mm": (pre_cvt.shift_position / MILLIMETRE),
                "post_shift_mm": (post_cvt.shift_position / MILLIMETRE),
                "delta_shift_mm": (
                    (post_cvt.shift_position - pre_cvt.shift_position) / MILLIMETRE
                ),
                "pre_shift_speed_mm_s": (pre_cvt.shift_speed / MILLIMETRE),
                "post_shift_speed_mm_s": (post_cvt.shift_speed / MILLIMETRE),
                "delta_shift_speed_mm_s": (
                    (post_cvt.shift_speed - pre_cvt.shift_speed) / MILLIMETRE
                ),
                "pre_belt_speed_m_s": pre_cvt.belt_speed,
                "post_belt_speed_m_s": post_cvt.belt_speed,
                "delta_belt_speed_m_s": (post_cvt.belt_speed - pre_cvt.belt_speed),
            }
        )
    return rows
