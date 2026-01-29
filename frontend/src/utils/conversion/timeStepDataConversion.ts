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
    car_velocity: conv(timeStep.state.car_velocity, 'velocity'),
    car_position: conv(timeStep.state.car_position, 'distance'),
    shift_velocity: conv(timeStep.state.shift_velocity, 'velocity'),
    shift_distance: conv(timeStep.state.shift_distance, 'distance'),
    engine_angular_velocity: conv(timeStep.state.engine_angular_velocity, 'angular_velocity'),
    engine_angular_position: conv(timeStep.state.engine_angular_position, 'angle'),
  },
  system: {
    slip: {
      coupling_torque: conv(timeStep.system.slip.coupling_torque, 'torque'),
      torque_demand: conv(timeStep.system.slip.torque_demand, 'torque'),
      t_max_prim: conv(timeStep.system.slip.t_max_prim, 'torque'),
      t_max_sec: conv(timeStep.system.slip.t_max_sec, 'torque'),
      cvt_ratio_derivative: conv(timeStep.system.slip.cvt_ratio_derivative, 'dimensionless_rate'),
      is_slipping: timeStep.system.slip.is_slipping
    },
    engine: {
      torque: conv(timeStep.system.engine.torque, 'torque'),
      power: conv(timeStep.system.engine.power, 'power'),
      angular_velocity: conv(timeStep.system.engine.angular_velocity, 'angular_velocity'),
      angular_acceleration: conv(timeStep.system.engine.angular_acceleration, 'angular_acceleration')
    },
    car: {
      external_forces: {
        incline_force: conv(timeStep.system.car.external_forces.incline_force, 'force'),
        drag_force: conv(timeStep.system.car.external_forces.drag_force, 'force'),
        net: conv(timeStep.system.car.external_forces.net, 'force')
      },
      acceleration: conv(timeStep.system.car.acceleration, 'acceleration')
    },
    cvt: {
      primaryPulleyState: {
        forces: {
          radial_force: conv(timeStep.system.cvt.primaryPulleyState.forces.radial_force, 'force'),
          clamping_force: conv(timeStep.system.cvt.primaryPulleyState.forces.clamping_force, 'force'),
          max_torque: conv(timeStep.system.cvt.primaryPulleyState.forces.max_torque, 'torque'),
        },
        wrap_angle: conv(timeStep.system.cvt.primaryPulleyState.wrap_angle, 'angle'),
        radius: conv(timeStep.system.cvt.primaryPulleyState.radius, 'distance'),
        angular_velocity: conv(timeStep.system.cvt.primaryPulleyState.angular_velocity, 'angular_velocity'),
        angular_position: conv(timeStep.system.cvt.primaryPulleyState.angular_position, 'angle'),
        radial_from_centrifugal: conv(timeStep.system.cvt.primaryPulleyState.radial_from_centrifugal, 'force'),
        radial_from_clamping: conv(timeStep.system.cvt.primaryPulleyState.radial_from_clamping, 'force'),
        breakdown: {
          ...convertPulleyForce(timeStep.system.cvt.primaryPulleyState.breakdown, config)
        }
      },
      secondaryPulleyState: {
        forces: {
          radial_force: conv(timeStep.system.cvt.secondaryPulleyState.forces.radial_force, 'force'),
          clamping_force: conv(timeStep.system.cvt.secondaryPulleyState.forces.clamping_force, 'force'),
          max_torque: conv(timeStep.system.cvt.secondaryPulleyState.forces.max_torque, 'torque'),
        },
        wrap_angle: conv(timeStep.system.cvt.secondaryPulleyState.wrap_angle, 'angle'),
        radius: conv(timeStep.system.cvt.secondaryPulleyState.radius, 'distance'),
        angular_velocity: conv(timeStep.system.cvt.secondaryPulleyState.angular_velocity, 'angular_velocity'),
        angular_position: conv(timeStep.system.cvt.secondaryPulleyState.angular_position, 'angle'),
        radial_from_centrifugal: conv(timeStep.system.cvt.secondaryPulleyState.radial_from_centrifugal, 'force'),
        radial_from_clamping: conv(timeStep.system.cvt.secondaryPulleyState.radial_from_clamping, 'force'),
        breakdown: {
          ...convertPulleyForce(timeStep.system.cvt.secondaryPulleyState.breakdown, config)
        }
      },
      friction: conv(timeStep.system.cvt.friction, 'dimensionless'),
      acceleration: conv(timeStep.system.cvt.acceleration, 'acceleration'),
      cvt_ratio: conv(timeStep.system.cvt.cvt_ratio, 'dimensionless'),
      net: conv(timeStep.system.cvt.net, 'force')
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
