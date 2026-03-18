/**
 * Unit conversion utilities for simulation time step data.
 */

import type { components } from '@types';
import { convertValue, getTargetUnit, type UnitConfiguration, DEFAULT_UNIT_CONFIG } from './unitConversion';

type FormattedSimulationResultModel = components['schemas']['FormattedSimulationResultModel'];
type TimeStepDataModel = components['schemas']['TimeStepDataModel'];

// Convert a single time step's data
function convertTimeStepData(
  timeStep: TimeStepDataModel,
  config: UnitConfiguration
): TimeStepDataModel {
  // Helper to convert values with the simplified config
  const conv = <T extends import('./unitConversion').BaseUnitType>(value: number, type: T) => 
    convertValue(value, type, getTargetUnit(type, config));

  return {
  time: conv(timeStep.time, 'time'),

  state: {
    shift_distance: conv(timeStep.state.shift_distance, 'distance'),
    shift_velocity: conv(timeStep.state.shift_velocity, 'velocity'),
    primary_pulley_angular_velocity: conv(timeStep.state.primary_pulley_angular_velocity, 'angular_velocity'),
    secondary_pulley_angular_velocity: conv(timeStep.state.secondary_pulley_angular_velocity, 'angular_velocity'),
  },
  derived_state: {
    car_velocity: conv(timeStep.derived_state.car_velocity, 'velocity'),
    car_position: conv(timeStep.derived_state.car_position, 'distance'),
    engine_angular_velocity: conv(timeStep.derived_state.engine_angular_velocity, 'angular_velocity'),
    engine_angular_position: conv(timeStep.derived_state.engine_angular_position, 'angle'),
  },
  drivetrain: {
    belt_slip: {
      coupling_torque: conv(timeStep.drivetrain.belt_slip.coupling_torque, 'torque'),
      torque_demand: conv(timeStep.drivetrain.belt_slip.torque_demand, 'torque'),
      t_max_prim: conv(timeStep.drivetrain.belt_slip.t_max_prim, 'torque'),
      t_max_sec: conv(timeStep.drivetrain.belt_slip.t_max_sec, 'torque'),
      effective_cvt_ratio_time_derivative: conv(timeStep.drivetrain.belt_slip.effective_cvt_ratio_time_derivative, 'dimensionless_rate'),
      is_slipping: timeStep.drivetrain.belt_slip.is_slipping
    },
    primary_pulley: {
      primary_pulley_drive_torque: conv(timeStep.drivetrain.primary_pulley.primary_pulley_drive_torque, 'torque'),
      coupling_torque_at_primary_pulley: conv(timeStep.drivetrain.primary_pulley.coupling_torque_at_primary_pulley, 'torque'),
      power: conv(timeStep.drivetrain.primary_pulley.power, 'power'),
      primary_pulley_angular_velocity: conv(timeStep.drivetrain.primary_pulley.primary_pulley_angular_velocity, 'angular_velocity'),
      primary_pulley_angular_acceleration: conv(timeStep.drivetrain.primary_pulley.primary_pulley_angular_acceleration, 'angular_acceleration')
    },
    secondary_pulley: {
      coupling_torque_at_secondary_pulley: conv(timeStep.drivetrain.secondary_pulley.coupling_torque_at_secondary_pulley, 'torque'),
      external_load_torque_at_secondary_pulley: conv(timeStep.drivetrain.secondary_pulley.external_load_torque_at_secondary_pulley, 'torque'),
      external_forces: {
        rolling_resistance_force: conv(timeStep.drivetrain.secondary_pulley.external_forces.rolling_resistance_force, 'force'),
        incline_force: conv(timeStep.drivetrain.secondary_pulley.external_forces.incline_force, 'force'),
        drag_force: conv(timeStep.drivetrain.secondary_pulley.external_forces.drag_force, 'force'),
        net: conv(timeStep.drivetrain.secondary_pulley.external_forces.net, 'force')
      },
      secondary_pulley_angular_acceleration: conv(timeStep.drivetrain.secondary_pulley.secondary_pulley_angular_acceleration, 'angular_acceleration')
    },
    cvt_dynamics: {
      primaryPulleyState: {
        forces: {
          axial_clamping_force: conv(timeStep.drivetrain.cvt_dynamics.primaryPulleyState.forces.axial_clamping_force, 'force'),
          axial_centrifugal_from_belt: conv(timeStep.drivetrain.cvt_dynamics.primaryPulleyState.forces.axial_centrifugal_from_belt, 'force'),
          axial_force_total: conv(timeStep.drivetrain.cvt_dynamics.primaryPulleyState.forces.axial_force_total, 'force'),
          max_torque: conv(timeStep.drivetrain.cvt_dynamics.primaryPulleyState.forces.max_torque, 'torque'),
        },
        wrap_angle: conv(timeStep.drivetrain.cvt_dynamics.primaryPulleyState.wrap_angle, 'angle'),
        radius: conv(timeStep.drivetrain.cvt_dynamics.primaryPulleyState.radius, 'distance'),
        angular_velocity: conv(timeStep.drivetrain.cvt_dynamics.primaryPulleyState.angular_velocity, 'angular_velocity'),
        angular_position: conv(timeStep.drivetrain.cvt_dynamics.primaryPulleyState.angular_position, 'angle'),
        breakdown: {
          ...convertPulleyForce(timeStep.drivetrain.cvt_dynamics.primaryPulleyState.breakdown, config)
        }
      },
      secondaryPulleyState: {
        forces: {
          axial_clamping_force: conv(timeStep.drivetrain.cvt_dynamics.secondaryPulleyState.forces.axial_clamping_force, 'force'),
          axial_centrifugal_from_belt: conv(timeStep.drivetrain.cvt_dynamics.secondaryPulleyState.forces.axial_centrifugal_from_belt, 'force'),
          axial_force_total: conv(timeStep.drivetrain.cvt_dynamics.secondaryPulleyState.forces.axial_force_total, 'force'),
          max_torque: conv(timeStep.drivetrain.cvt_dynamics.secondaryPulleyState.forces.max_torque, 'torque'),
        },
        wrap_angle: conv(timeStep.drivetrain.cvt_dynamics.secondaryPulleyState.wrap_angle, 'angle'),
        radius: conv(timeStep.drivetrain.cvt_dynamics.secondaryPulleyState.radius, 'distance'),
        angular_velocity: conv(timeStep.drivetrain.cvt_dynamics.secondaryPulleyState.angular_velocity, 'angular_velocity'),
        angular_position: conv(timeStep.drivetrain.cvt_dynamics.secondaryPulleyState.angular_position, 'angle'),
        breakdown: {
          ...convertPulleyForce(timeStep.drivetrain.cvt_dynamics.secondaryPulleyState.breakdown, config)
        }
      },
      friction: conv(timeStep.drivetrain.cvt_dynamics.friction, 'dimensionless'),
      acceleration: conv(timeStep.drivetrain.cvt_dynamics.acceleration, 'acceleration'),
      cvt_ratio: conv(timeStep.drivetrain.cvt_dynamics.cvt_ratio, 'dimensionless'),
      net: conv(timeStep.drivetrain.cvt_dynamics.net, 'force')
    }
  }
};
}

// Convert primary or secondary pulley force (needed to handle the union type)
function convertPulleyForce(
  pulleyForce: components['schemas']['PrimaryForceBreakdownModel'] | components['schemas']['SecondaryForceBreakdownModel'],
  config: UnitConfiguration
): components['schemas']['PrimaryForceBreakdownModel'] | components['schemas']['SecondaryForceBreakdownModel'] {
  const conv = <T extends import('./unitConversion').BaseUnitType>(value: number, type: T) => 
    convertValue(value, type, getTargetUnit(type, config));

  // Type guard: check if it's PrimaryForceBreakdownModel
  if ('flyweightForce' in pulleyForce) {
    return {
      flyweightForce: {
        radius: conv(pulleyForce.flyweightForce.radius, 'distance'),
        angular_velocity: conv(pulleyForce.flyweightForce.angular_velocity, 'angular_velocity'),
        angle: conv(pulleyForce.flyweightForce.angle, 'angle'),
        centrifugal_force: conv(pulleyForce.flyweightForce.centrifugal_force, 'force'),
        angle_multiplier: pulleyForce.flyweightForce.angle_multiplier, // dimensionless
        net: conv(pulleyForce.flyweightForce.net, 'force'),
      },
      springForce: {
        compression: conv(pulleyForce.springForce.compression, 'distance'),
        net: conv(pulleyForce.springForce.net, 'force'),
      },
      net: conv(pulleyForce.net, 'force'),
    };
  } else {
    // It's SecondaryForceBreakdownModel
    return {
      springCompForce: {
        compression: conv(pulleyForce.springCompForce.compression, 'distance'),
        net: conv(pulleyForce.springCompForce.net, 'force'),
      },
      helix_force: {
        feedbackTorque: conv(pulleyForce.helix_force.feedbackTorque, 'torque'),
        springTorque: {
          rotation: conv(pulleyForce.helix_force.springTorque.rotation, 'angle'),
          net: conv(pulleyForce.helix_force.springTorque.net, 'torque'),
        },
        angle: conv(pulleyForce.helix_force.angle, 'angle'),
        radius: conv(pulleyForce.helix_force.radius, 'distance'),
        angle_multiplier: pulleyForce.helix_force.angle_multiplier, // dimensionless
        net: conv(pulleyForce.helix_force.net, 'force'),
      },
      net: conv(pulleyForce.net, 'force'),
    };
  }
}

// Main conversion function for simulation results
export function convertSimulationData(
  data: FormattedSimulationResultModel,
  config: UnitConfiguration = DEFAULT_UNIT_CONFIG
): FormattedSimulationResultModel {
  return {
    data: data.data.map(timeStep => convertTimeStepData(timeStep, config)),
  };
}
