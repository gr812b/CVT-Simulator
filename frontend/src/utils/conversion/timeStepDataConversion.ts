/**
 * Unit conversion utilities for simulation analysis data.
 */

import type { components } from '@types';
import {
  convertValue,
  getTargetUnit,
  type UnitConfiguration,
  DEFAULT_UNIT_CONFIG,
} from './unitConversion';

type AnalysisStepDataModel = components['schemas']['AnalysisStepDataModel'];
type SimulationAnalysisResultModel = components['schemas']['SimulationAnalysisResultModel'];
type ContactDynamicsBreakdownModel = components['schemas']['ContactDynamicsBreakdownModel'];
type CVTGeometryResultModel = components['schemas']['CVTGeometryResultModel'];
type ContactTorqueResultModel = components['schemas']['ContactTorqueResultModel'];
type DrivetrainAccelerationBreakdownModel = components['schemas']['DrivetrainAccelerationBreakdownModel'];
type CvtDynamicsBreakdownModel = components['schemas']['CvtDynamicsBreakdownModel'];
type PulleyForcesModel = components['schemas']['PulleyForcesModel'];
type PrimaryForceBreakdownModel = components['schemas']['PrimaryForceBreakdownModel'];
type SecondaryForceBreakdownModel = components['schemas']['SecondaryForceBreakdownModel'];
type EngineTorqueBreakdownModel = components['schemas']['EngineTorqueBreakdownModel'];
type ExternalLoadForceBreakdownModel = components['schemas']['ExternalLoadForceBreakdownModel'];
type NoSlipBreakdownModel = components['schemas']['NoSlipBreakdownModel'];
type NoSlipResultModel = components['schemas']['NoSlipResultModel'];
type TorqueAdmissibilityResultModel = components['schemas']['TorqueAdmissibilityResultModel'];
type PrimaryTorqueAdmissibilityBreakdownModel = components['schemas']['PrimaryTorqueAdmissibilityBreakdownModel'];
type SecondaryTorqueAdmissibilityBreakdownModel = components['schemas']['SecondaryTorqueAdmissibilityBreakdownModel'];
type SlipMetricsResultModel = components['schemas']['SlipMetricsResultModel'];

function convFactory(config: UnitConfiguration) {
  return <T extends import('./unitConversion').BaseUnitType>(value: number, type: T) =>
    convertValue(value, type, getTargetUnit(type, config));
}

function convertPrimaryForceBreakdown(
  breakdown: PrimaryForceBreakdownModel,
  config: UnitConfiguration
): PrimaryForceBreakdownModel {
  const conv = convFactory(config);
  return {
    flyweightForce: {
      radius: conv(breakdown.flyweightForce.radius, 'distance'),
      angular_velocity: conv(breakdown.flyweightForce.angular_velocity, 'angular_velocity'),
      angle: conv(breakdown.flyweightForce.angle, 'angle'),
      centrifugal_force: conv(breakdown.flyweightForce.centrifugal_force, 'force'),
      angle_multiplier: breakdown.flyweightForce.angle_multiplier,
      net: conv(breakdown.flyweightForce.net, 'force'),
    },
    springForce: {
      compression: conv(breakdown.springForce.compression, 'distance'),
      net: conv(breakdown.springForce.net, 'force'),
    },
    net: conv(breakdown.net, 'force'),
  };
}

function convertSecondaryForceBreakdown(
  breakdown: SecondaryForceBreakdownModel,
  config: UnitConfiguration
): SecondaryForceBreakdownModel {
  const conv = convFactory(config);
  return {
    springCompForce: {
      compression: conv(breakdown.springCompForce.compression, 'distance'),
      net: conv(breakdown.springCompForce.net, 'force'),
    },
    helix_force: {
      feedbackTorque: conv(breakdown.helix_force.feedbackTorque, 'torque'),
      springTorque: {
        rotation: conv(breakdown.helix_force.springTorque.rotation, 'angle'),
        net: conv(breakdown.helix_force.springTorque.net, 'torque'),
      },
      angle: conv(breakdown.helix_force.angle, 'angle'),
      radius: conv(breakdown.helix_force.radius, 'distance'),
      angle_multiplier: breakdown.helix_force.angle_multiplier,
      net: conv(breakdown.helix_force.net, 'force'),
    },
    net: conv(breakdown.net, 'force'),
  };
}

function convertPulleyForces(
  pulleyForces: PulleyForcesModel,
  config: UnitConfiguration
): PulleyForcesModel {
  const conv = convFactory(config);
  const pulleyBreakdown = pulleyForces.pulley_breakdown;
  return {
    pulley_breakdown:
      'flyweightForce' in pulleyBreakdown
        ? convertPrimaryForceBreakdown(pulleyBreakdown, config)
        : convertSecondaryForceBreakdown(pulleyBreakdown, config),
    belt_wrap: {
      wrap_angle: conv(pulleyForces.belt_wrap.wrap_angle, 'angle'),
      axial_belt_force: conv(pulleyForces.belt_wrap.axial_belt_force, 'force'),
    },
    net: conv(pulleyForces.net, 'force'),
  };
}

function convertEngineBreakdown(
  breakdown: EngineTorqueBreakdownModel,
  config: UnitConfiguration
): EngineTorqueBreakdownModel {
  const conv = convFactory(config);
  return {
    engine_torque: conv(breakdown.engine_torque, 'torque'),
    engine_speed: conv(breakdown.engine_speed, 'angular_velocity'),
    engine_power: conv(breakdown.engine_power, 'power'),
  };
}

function convertExternalLoadBreakdown(
  breakdown: ExternalLoadForceBreakdownModel,
  config: UnitConfiguration
): ExternalLoadForceBreakdownModel {
  const conv = convFactory(config);
  return {
    rolling_resistance_force: conv(breakdown.rolling_resistance_force, 'force'),
    incline_force: conv(breakdown.incline_force, 'force'),
    drag_force: conv(breakdown.drag_force, 'force'),
    net_force_at_car: conv(breakdown.net_force_at_car, 'force'),
    rolling_resistance_torque_at_secondary: conv(
      breakdown.rolling_resistance_torque_at_secondary,
      'torque'
    ),
    incline_torque_at_secondary: conv(breakdown.incline_torque_at_secondary, 'torque'),
    drag_torque_at_secondary: conv(breakdown.drag_torque_at_secondary, 'torque'),
    net_torque_at_secondary: conv(breakdown.net_torque_at_secondary, 'torque'),
  };
}

function convertNoSlipBreakdown(
  breakdown: NoSlipBreakdownModel,
  config: UnitConfiguration
): NoSlipBreakdownModel {
  const conv = convFactory(config);
  return {
    r_p: conv(breakdown.r_p, 'distance'),
    r_s: conv(breakdown.r_s, 'distance'),
    r_p_dot: conv(breakdown.r_p_dot, 'distance'),
    r_s_dot: conv(breakdown.r_s_dot, 'distance'),
    tau_engine_over_r_p: conv(breakdown.tau_engine_over_r_p, 'force'),
    tau_load_over_r_s: conv(breakdown.tau_load_over_r_s, 'force'),
    primary_inertia_term: conv(breakdown.primary_inertia_term, 'force'),
    secondary_inertia_term: conv(breakdown.secondary_inertia_term, 'force'),
    numerator: conv(breakdown.numerator, 'force'),
    denominator: breakdown.denominator,
  };
}

function convertPrimaryTorqueAdmissibilityBreakdown(
  breakdown: PrimaryTorqueAdmissibilityBreakdownModel,
  config: UnitConfiguration
): PrimaryTorqueAdmissibilityBreakdownModel {
  const conv = convFactory(config);
  return {
    shift_distance: conv(breakdown.shift_distance, 'distance'),
    wrap_angle: conv(breakdown.wrap_angle, 'angle'),
    effective_radius: conv(breakdown.effective_radius, 'distance'),
    centroid_radius: conv(breakdown.centroid_radius, 'distance'),
    centroid_radius_rate: conv(breakdown.centroid_radius_rate, 'velocity'),
    axial_clamping_force: conv(breakdown.axial_clamping_force, 'force'),
    belt_centripetal_term: conv(breakdown.belt_centripetal_term, 'force'),
    friction_coefficient: breakdown.friction_coefficient,
    sheave_half_angle: conv(breakdown.sheave_half_angle, 'angle'),
    tau_p_stick_limit: conv(breakdown.tau_p_stick_limit, 'torque'),
    tau_p_stick_upper: conv(breakdown.tau_p_stick_upper, 'torque'),
    tau_p_stick_lower: conv(breakdown.tau_p_stick_lower, 'torque'),
  };
}

function convertSecondaryTorqueAdmissibilityBreakdown(
  breakdown: SecondaryTorqueAdmissibilityBreakdownModel,
  config: UnitConfiguration
): SecondaryTorqueAdmissibilityBreakdownModel {
  const conv = convFactory(config);
  return {
    shift_distance: conv(breakdown.shift_distance, 'distance'),
    wrap_angle: conv(breakdown.wrap_angle, 'angle'),
    effective_radius: conv(breakdown.effective_radius, 'distance'),
    centroid_radius: conv(breakdown.centroid_radius, 'distance'),
    centroid_radius_rate: conv(breakdown.centroid_radius_rate, 'velocity'),
    helix_rotation: conv(breakdown.helix_rotation, 'angle'),
    helix_rotation_rate: conv(breakdown.helix_rotation_rate, 'angle'),
    spring_torsion_term: conv(breakdown.spring_torsion_term, 'torque'),
    spring_comp_term: conv(breakdown.spring_comp_term, 'force'),
    belt_centripetal_term: conv(breakdown.belt_centripetal_term, 'force'),
    friction_coefficient: breakdown.friction_coefficient,
    sheave_half_angle: conv(breakdown.sheave_half_angle, 'angle'),
    denominator_upper: breakdown.denominator_upper,
    denominator_lower: breakdown.denominator_lower,
    tau_stick_upper: conv(breakdown.tau_stick_upper, 'torque'),
    tau_stick_lower: conv(breakdown.tau_stick_lower, 'torque'),
  };
}

function convertTorqueAdmissibilityResult(
  admissibility: TorqueAdmissibilityResultModel,
  config: UnitConfiguration
): TorqueAdmissibilityResultModel {
  return {
    primary: convertPrimaryTorqueAdmissibilityBreakdown(admissibility.primary, config),
    secondary: convertSecondaryTorqueAdmissibilityBreakdown(admissibility.secondary, config),
    primary_tau_p_stick_upper: convFactory(config)(admissibility.primary_tau_p_stick_upper, 'torque'),
    primary_tau_p_stick_lower: convFactory(config)(admissibility.primary_tau_p_stick_lower, 'torque'),
    secondary_tau_stick_upper: convFactory(config)(admissibility.secondary_tau_stick_upper, 'torque'),
    secondary_tau_stick_lower: convFactory(config)(admissibility.secondary_tau_stick_lower, 'torque'),
  };
}

function convertSlipMetricsResult(
  slipMetrics: SlipMetricsResultModel,
  config: UnitConfiguration
): SlipMetricsResultModel {
  const conv = convFactory(config);
  return {
    primary_relative_speed: conv(slipMetrics.primary_relative_speed, 'velocity'),
    secondary_relative_speed: conv(slipMetrics.secondary_relative_speed, 'velocity'),
    primary_slip_direction: slipMetrics.primary_slip_direction,
    secondary_slip_direction: slipMetrics.secondary_slip_direction,
    admissibility: convertTorqueAdmissibilityResult(slipMetrics.admissibility, config),
    no_slip: convertNoSlipResult(slipMetrics.no_slip, config),
  };
}

function convertNoSlipResult(
  noSlip: NoSlipResultModel,
  config: UnitConfiguration
): NoSlipResultModel {
  const conv = convFactory(config);
  return {
    v_b_dot_ns: conv(noSlip.v_b_dot_ns, 'acceleration'),
    tau_p_ns: conv(noSlip.tau_p_ns, 'torque'),
    tau_s_ns: conv(noSlip.tau_s_ns, 'torque'),
    breakdown: convertNoSlipBreakdown(noSlip.breakdown, config),
  };
}

function convertContactTorqueResult(
  contact: ContactTorqueResultModel,
  config: UnitConfiguration
): ContactTorqueResultModel {
  const conv = convFactory(config);
  return {
    tau_p: conv(contact.tau_p, 'torque'),
    tau_s: conv(contact.tau_s, 'torque'),
    branch: contact.branch,
    slip_metrics: convertSlipMetricsResult(contact.slip_metrics, config),
    branch_result: {
      tau_p: conv(contact.branch_result.tau_p, 'torque'),
      tau_s: conv(contact.branch_result.tau_s, 'torque'),
    },
  };
}

function convertDrivetrainAccelerationBreakdown(
  drivetrain: DrivetrainAccelerationBreakdownModel,
  config: UnitConfiguration
): DrivetrainAccelerationBreakdownModel {
  const conv = convFactory(config);
  return {
    ω_p_dot: conv(drivetrain.ω_p_dot, 'angular_acceleration'),
    ω_s_dot: conv(drivetrain.ω_s_dot, 'angular_acceleration'),
    v_b_dot: conv(drivetrain.v_b_dot, 'acceleration'),
    engine_breakdown: convertEngineBreakdown(drivetrain.engine_breakdown, config),
    external_load_breakdown: convertExternalLoadBreakdown(drivetrain.external_load_breakdown, config),
    tau_p: conv(drivetrain.tau_p, 'torque'),
    tau_s: conv(drivetrain.tau_s, 'torque'),
  };
}

function convertCvtDynamicsBreakdown(
  shift: CvtDynamicsBreakdownModel,
  config: UnitConfiguration
): CvtDynamicsBreakdownModel {
  const conv = convFactory(config);
  return {
    primaryPulleyState: convertPulleyForces(shift.primaryPulleyState, config),
    secondaryPulleyState: convertPulleyForces(shift.secondaryPulleyState, config),
    friction: conv(shift.friction, 'force'),
    acceleration: conv(shift.acceleration, 'acceleration'),
    net: conv(shift.net, 'force'),
  };
}

function convertContactBreakdown(
  contactBreakdown: ContactDynamicsBreakdownModel,
  config: UnitConfiguration
): ContactDynamicsBreakdownModel {
  return {
    contact: convertContactTorqueResult(contactBreakdown.contact, config),
    drivetrain: convertDrivetrainAccelerationBreakdown(contactBreakdown.drivetrain, config),
    shift: convertCvtDynamicsBreakdown(contactBreakdown.shift, config),
    geometry: convertGeometryResult(contactBreakdown.geometry, config),
  };
}

function convertGeometryResult(
  geometry: CVTGeometryResultModel,
  config: UnitConfiguration
): CVTGeometryResultModel {
  const conv = convFactory(config);
  return {
    effective_cvt_ratio: conv(geometry.effective_cvt_ratio, 'dimensionless'),
    effective_cvt_ratio_rate_of_change: conv(
      geometry.effective_cvt_ratio_rate_of_change,
      'dimensionless_rate'
    ),
    primary_outer_radius: conv(geometry.primary_outer_radius, 'distance'),
    primary_effective_radius: conv(geometry.primary_effective_radius, 'distance'),
    primary_centroid_radius: conv(geometry.primary_centroid_radius, 'distance'),
    primary_radius_rate_of_change: conv(geometry.primary_radius_rate_of_change, 'velocity'),
    secondary_outer_radius: conv(geometry.secondary_outer_radius, 'distance'),
    secondary_effective_radius: conv(geometry.secondary_effective_radius, 'distance'),
    secondary_centroid_radius: conv(geometry.secondary_centroid_radius, 'distance'),
    secondary_radius_rate_of_change: conv(geometry.secondary_radius_rate_of_change, 'velocity'),
    primary_wrap_angle: conv(geometry.primary_wrap_angle, 'angle'),
    secondary_wrap_angle: conv(geometry.secondary_wrap_angle, 'angle'),
  };
}

function convertDerivedState(
  derivedState: AnalysisStepDataModel['derived_state'],
  config: UnitConfiguration
): AnalysisStepDataModel['derived_state'] {
  const conv = convFactory(config);
  return {
    car_velocity: conv(derivedState.car_velocity, 'velocity'),
    car_position: conv(derivedState.car_position, 'distance'),
    belt_position: conv(derivedState.belt_position, 'distance'),
    engine_angular_velocity: conv(derivedState.engine_angular_velocity, 'angular_velocity'),
    engine_angular_position: conv(derivedState.engine_angular_position, 'angle'),
    secondary_angular_position: conv(derivedState.secondary_angular_position, 'angle'),
  };
}

// Convert a single time step's data
function convertTimeStepData(
  timeStep: AnalysisStepDataModel,
  config: UnitConfiguration
): AnalysisStepDataModel {
  const conv = convFactory(config);

  return {
    time: conv(timeStep.time, 'time'),
    mode: timeStep.mode,
    shift_mode: timeStep.shift_mode,
    slip_mode: timeStep.slip_mode,
    state: {
      s: conv(timeStep.state.s, 'distance'),
      s_dot: conv(timeStep.state.s_dot, 'velocity'),
      ω_p: conv(timeStep.state.ω_p, 'angular_velocity'),
      ω_s: conv(timeStep.state.ω_s, 'angular_velocity'),
      v_b: conv(timeStep.state.v_b, 'velocity'),
    },
    derived_state: convertDerivedState(timeStep.derived_state, config),
    contact_breakdown: convertContactBreakdown(timeStep.contact_breakdown, config),
  };
}

// Main conversion function for simulation results
export function convertSimulationData(
  data: SimulationAnalysisResultModel,
  config: UnitConfiguration = DEFAULT_UNIT_CONFIG
): SimulationAnalysisResultModel {
  const conv = convFactory(config);

  return {
    data: data.data.map((timeStep) => convertTimeStepData(timeStep, config)),
    termination: {
      ...data.termination,
      final_time: conv(data.termination.final_time, 'time'),
      event_time:
        data.termination.event_time == null
          ? null
          : conv(data.termination.event_time, 'time'),
    },
  };
}
