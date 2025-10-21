import type { components } from '@types';

type FormattedSimulationResultModel = components['schemas']['FormattedSimulationResultModel'];
type TimeStepDataModel = components['schemas']['TimeStepDataModel'];

// Base unit types that the API provides (all SI units)
export type BaseUnitType = 
  | 'angular_velocity'    // rad/s
  | 'angular_acceleration' // rad/s²
  | 'mass'               // kg
  | 'force'              // N
  | 'torque'             // Nm
  | 'power'              // W
  | 'velocity'           // m/s
  | 'distance'           // m
  | 'acceleration'       // m/s²
  | 'angle'              // rad
  | 'time'               // s
  | 'dimensionless';     // unitless ratios

// Available unit options for each base type
export type UnitOptions = {
  angular_velocity: 'rad/s' | 'rpm' | 'deg/s';
  angular_acceleration: 'rad/s²' | 'rpm/s' | 'deg/s²';
  mass: 'kg' | 'lb' | 'g';
  force: 'N' | 'lbf' | 'kN';
  torque: 'Nm' | 'lb·ft' | 'kNm';
  power: 'W' | 'hp' | 'kW';
  velocity: 'm/s' | 'mph' | 'km/h' | 'ft/s';
  distance: 'm' | 'ft' | 'km' | 'mi';
  acceleration: 'm/s²' | 'ft/s²' | 'g';
  angle: 'rad' | 'deg';
  time: 's' | 'min' | 'hr';
  // Dimensionless set to empty for a ratio
  dimensionless: '' | '%'; 
};

// Core unit configuration - affects all values of that type
export type CoreUnits = {
  [K in BaseUnitType]?: UnitOptions[K];
};

// Simple unit configuration - just specify what units you want for each type
export type UnitConfiguration = {
  [K in BaseUnitType]?: UnitOptions[K];
};

// Conversion factors from SI base units
const CONVERSION_FACTORS: { [K in BaseUnitType]: Record<UnitOptions[K], number> } = {
  angular_velocity: {
    'rad/s': 1,
    'rpm': 30 / Math.PI,
    'deg/s': 180 / Math.PI,
  },
  angular_acceleration: {
    'rad/s²': 1,
    'rpm/s': 30 / Math.PI,
    'deg/s²': 180 / Math.PI,
  },
  mass: {
    'kg': 1,
    'lb': 2.20462,
    'g': 1000,
  },
  force: {
    'N': 1,
    'lbf': 0.224809,
    'kN': 0.001,
  },
  torque: {
    'Nm': 1,
    'lb·ft': 0.737562,
    'kNm': 0.001,
  },
  power: {
    'W': 1,
    'hp': 0.00134102,
    'kW': 0.001,
  },
  velocity: {
    'm/s': 1,
    'mph': 2.23694,
    'km/h': 3.6,
    'ft/s': 3.28084,
  },
  distance: {
    'm': 1,
    'ft': 3.28084,
    'km': 0.001,
    'mi': 0.000621371,
  },
  acceleration: {
    'm/s²': 1,
    'ft/s²': 3.28084,
    'g': 0.101972,
  },
  angle: {
    'rad': 1,
    'deg': 180 / Math.PI,
  },
  time: {
    's': 1,
    'min': 1 / 60,
    'hr': 1 / 3600,
  },
  dimensionless: {
    '': 1,
    '%': 100,
  },
} as const;

// Default configuration (all SI units)
export const DEFAULT_UNIT_CONFIG: UnitConfiguration = {};

// Common preset configurations
export const UNIT_PRESETS = {
  SI: {
    angular_velocity: 'rad/s',
    angular_acceleration: 'rad/s²',
    mass: 'kg',
    force: 'N',
    torque: 'Nm',
    power: 'W',
    velocity: 'm/s',
    distance: 'm',
    acceleration: 'm/s²',
    angle: 'rad',
    time: 's',
    dimensionless: '',
  } as UnitConfiguration,
  
  IMPERIAL: {
    angular_velocity: 'rpm',
    angular_acceleration: 'rpm/s',
    mass: 'lb',
    force: 'lbf',
    torque: 'lb·ft',
    power: 'hp',
    velocity: 'mph',
    distance: 'ft',
    acceleration: 'ft/s²',
    angle: 'deg',
    dimensionless: '%',
  } as UnitConfiguration,
  
  BAJA: {
    angular_velocity: 'rpm',
    angular_acceleration: 'rpm/s',
    power: 'hp',
    velocity: 'km/h',
    distance: 'm',
    torque: 'lb·ft',
    angle: 'deg',
  } as UnitConfiguration,
};

// Helper function to get the target unit for a specific type
export function getTargetUnit<T extends BaseUnitType>(
  baseType: T,
  config: UnitConfiguration
): UnitOptions[T] {
  // Check configuration for this type, could be empty
  const configuredUnit = config[baseType];
  if (configuredUnit) return configuredUnit;
  
  // Default to SI unit from preset
  const siUnit = UNIT_PRESETS.SI[baseType];
  return siUnit!; // We know SI preset has all units defined
}

// Convert a value from SI base unit to target unit
function convertValue<T extends BaseUnitType>(
  value: number,
  baseType: T,
  targetUnit: UnitOptions[T]
): number {
  const conversionTable = CONVERSION_FACTORS[baseType];
  const factor = conversionTable[targetUnit];
  return value * factor;
}

// Convert a single time step's data
function convertTimeStepData(
  timeStep: TimeStepDataModel,
  config: UnitConfiguration
): TimeStepDataModel {
  // Helper to convert values with the simplified config
  const conv = <T extends BaseUnitType>(value: number, type: T) => 
    convertValue(value, type, getTargetUnit(type, config));

  return {
  time: conv(timeStep.time, 'time'),

  state: {
    car_velocity: conv(timeStep.state.car_velocity, 'velocity'),
    car_position: conv(timeStep.state.car_position, 'distance'),
    shift_velocity: conv(timeStep.state.shift_velocity, 'velocity'),
    shift_distance: conv(timeStep.state.shift_distance, 'distance'),
    engine_angular_velocity: conv(timeStep.state.engine_angular_velocity, 'angular_velocity'),
  },
  system: {
    slip: {
      t_c: conv(timeStep.system.slip.t_c, 'torque'),
      cvt_ratio_derivative: conv(timeStep.system.slip.cvt_ratio_derivative, 'dimensionless')
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
      primaryRadialForce: {
        pulleyForce: convertPulleyForce(timeStep.system.cvt.primaryRadialForce.pulleyForce, config),
        beltCentrifugalForce: {
          mass: conv(timeStep.system.cvt.primaryRadialForce.beltCentrifugalForce.mass, 'mass'),
          radius: conv(timeStep.system.cvt.primaryRadialForce.beltCentrifugalForce.radius, 'distance'),
          wrap_angle: conv(timeStep.system.cvt.primaryRadialForce.beltCentrifugalForce.wrap_angle, 'angle'),
          angular_velocity: conv(timeStep.system.cvt.primaryRadialForce.beltCentrifugalForce.angular_velocity, 'angular_velocity'),
          net: conv(timeStep.system.cvt.primaryRadialForce.beltCentrifugalForce.net, 'force')
        },
        radialPulleyForce: conv(timeStep.system.cvt.primaryRadialForce.radialPulleyForce, 'force'),
        net: conv(timeStep.system.cvt.primaryRadialForce.net, 'force')
      },
      secondaryRadialForce: {
        pulleyForce: convertPulleyForce(timeStep.system.cvt.secondaryRadialForce.pulleyForce, config),
        beltCentrifugalForce: {
          mass: conv(timeStep.system.cvt.secondaryRadialForce.beltCentrifugalForce.mass, 'mass'),
          radius: conv(timeStep.system.cvt.secondaryRadialForce.beltCentrifugalForce.radius, 'distance'),
          wrap_angle: conv(timeStep.system.cvt.secondaryRadialForce.beltCentrifugalForce.wrap_angle, 'angle'),
          angular_velocity: conv(timeStep.system.cvt.secondaryRadialForce.beltCentrifugalForce.angular_velocity, 'angular_velocity'),
          net: conv(timeStep.system.cvt.secondaryRadialForce.beltCentrifugalForce.net, 'force')
        },
        radialPulleyForce: conv(timeStep.system.cvt.secondaryRadialForce.radialPulleyForce, 'force'),
        net: conv(timeStep.system.cvt.secondaryRadialForce.net, 'force')
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
  const conv = <T extends BaseUnitType>(value: number, type: T) => 
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

// Utility function to get unit label for display
export function getUnitLabel(
  baseType: BaseUnitType,
  config: UnitConfiguration
): string {
  return getTargetUnit(baseType, config);
}

// Helper to get available units for a specific base type
export function getAvailableUnits(baseType: BaseUnitType): readonly string[] {
  const conversionTable = CONVERSION_FACTORS[baseType] as Record<string, number>;
  return Object.keys(conversionTable);
}
