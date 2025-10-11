import type { components } from '@types';

type FormattedSimulationResultModel = components['schemas']['FormattedSimulationResultModel'];
type TimeStepDataModel = components['schemas']['TimeStepDataModel'];

// Base unit types that the API provides (all SI units)
export type BaseUnitType = 
  | 'angular_velocity'    // rad/s
  | 'mass'               // kg
  | 'force'              // N
  | 'torque'             // Nm
  | 'power'              // W
  | 'velocity'           // m/s
  | 'distance'           // m
  | 'acceleration'       // m/s²
  | 'angle'              // rad
  | 'time';              // s

// Available unit options for each base type
export type UnitOptions = {
  angular_velocity: 'rad/s' | 'rpm' | 'deg/s';
  mass: 'kg' | 'lb' | 'g';
  force: 'N' | 'lbf' | 'kN';
  torque: 'Nm' | 'lb·ft' | 'kNm';
  power: 'W' | 'hp' | 'kW';
  velocity: 'm/s' | 'mph' | 'km/h' | 'ft/s';
  distance: 'm' | 'ft' | 'km' | 'mi';
  acceleration: 'm/s²' | 'ft/s²' | 'g';
  angle: 'rad' | 'deg';
  time: 's' | 'min' | 'hr';
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
// TODO: Define via UnitOptions
const CONVERSION_FACTORS = {
  angular_velocity: {
    'rad/s': 1,
    'rpm': 30 / Math.PI,
    'deg/s': 180 / Math.PI,
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
} as const;

// Default configuration (all SI units)
export const DEFAULT_UNIT_CONFIG: UnitConfiguration = {};

// Common preset configurations
export const UNIT_PRESETS = {
  SI: {} as UnitConfiguration,
  
  IMPERIAL: {
    angular_velocity: 'rpm',
    mass: 'lb',
    force: 'lbf',
    torque: 'lb·ft',
    power: 'hp',
    velocity: 'mph',
    distance: 'ft',
    acceleration: 'ft/s²',
    angle: 'deg',
  } as UnitConfiguration,
  
  BAJA: {
    angular_velocity: 'rpm',
    power: 'hp',
    velocity: 'km/h',
    distance: 'm',
    torque: 'lb·ft',
    angle: 'deg',
  } as UnitConfiguration,
};

// Helper function to get the target unit for a specific type
function getTargetUnit<T extends BaseUnitType>(
  baseType: T,
  config: UnitConfiguration
): UnitOptions[T] {
  // Check configuration for this type
  const configuredUnit = config[baseType] as UnitOptions[T] | undefined;
  if (configuredUnit) return configuredUnit;
  
  // Default to SI unit
  const siUnits = {
    angular_velocity: 'rad/s',
    mass: 'kg',
    force: 'N',
    torque: 'Nm',
    power: 'W',
    velocity: 'm/s',
    distance: 'm',
    acceleration: 'm/s²',
    angle: 'rad',
    time: 's',
  } as const;
  
  return siUnits[baseType] as UnitOptions[T];
}

// TODO: Use UnitOptions for targetUnit
// Convert a value from SI base unit to target unit
function convertValue(
  value: number,
  baseType: BaseUnitType,
  targetUnit: string
): number {
  const conversionTable = CONVERSION_FACTORS[baseType] as Record<string, number>;
  const factor = conversionTable[targetUnit] ?? 1;
  return value * factor;
}

// TODO: Look into primary / secondary radial force
// Convert a single time step's data
function convertTimeStepData(
  timeStep: TimeStepDataModel,
  config: UnitConfiguration
): TimeStepDataModel {
  // Helper to convert values with the simplified config
  const conv = (value: number, type: BaseUnitType) => 
    convertValue(value, type, getTargetUnit(type, config));

  return {
    time: conv(timeStep.time, 'time'),
    
    state: {
      car_velocity: conv(timeStep.state.car_velocity, 'velocity'),
      car_position: conv(timeStep.state.car_position, 'distance'),
      shift_velocity: conv(timeStep.state.shift_velocity, 'velocity'),
      shift_distance: conv(timeStep.state.shift_distance, 'distance'),
    },
    
    car_state: {
      external_forces: {
        incline_force: conv(timeStep.car_state.external_forces.incline_force, 'force'),
        drag_force: conv(timeStep.car_state.external_forces.drag_force, 'force'),
        net: conv(timeStep.car_state.external_forces.net, 'force'),
      },
      engine_forces: {
        torque: conv(timeStep.car_state.engine_forces.torque, 'torque'),
        power: conv(timeStep.car_state.engine_forces.power, 'power'),
        angular_velocity: conv(timeStep.car_state.engine_forces.angular_velocity, 'angular_velocity'),
      },
      acceleration: conv(timeStep.car_state.acceleration, 'acceleration'),
    },
    
    cvt_state: {
      primaryRadialForce: {
        pulleyForce: convertAnyObject(timeStep.cvt_state.primaryRadialForce.pulleyForce, config) as TimeStepDataModel['cvt_state']['primaryRadialForce']['pulleyForce'],
        beltCentrifugalForce: {
          mass: conv(timeStep.cvt_state.primaryRadialForce.beltCentrifugalForce.mass, 'mass'),
          radius: conv(timeStep.cvt_state.primaryRadialForce.beltCentrifugalForce.radius, 'distance'),
          wrap_angle: conv(timeStep.cvt_state.primaryRadialForce.beltCentrifugalForce.wrap_angle, 'angle'),
          angular_velocity: conv(timeStep.cvt_state.primaryRadialForce.beltCentrifugalForce.angular_velocity, 'angular_velocity'),
          net: conv(timeStep.cvt_state.primaryRadialForce.beltCentrifugalForce.net, 'force'),
        },
        radialPulleyForce: conv(timeStep.cvt_state.primaryRadialForce.radialPulleyForce, 'force'),
        net: conv(timeStep.cvt_state.primaryRadialForce.net, 'force'),
      },
      secondaryRadialForce: {
        pulleyForce: convertAnyObject(timeStep.cvt_state.secondaryRadialForce.pulleyForce, config) as TimeStepDataModel['cvt_state']['secondaryRadialForce']['pulleyForce'],
        beltCentrifugalForce: {
          mass: conv(timeStep.cvt_state.secondaryRadialForce.beltCentrifugalForce.mass, 'mass'),
          radius: conv(timeStep.cvt_state.secondaryRadialForce.beltCentrifugalForce.radius, 'distance'),
          wrap_angle: conv(timeStep.cvt_state.secondaryRadialForce.beltCentrifugalForce.wrap_angle, 'angle'),
          angular_velocity: conv(timeStep.cvt_state.secondaryRadialForce.beltCentrifugalForce.angular_velocity, 'angular_velocity'),
          net: conv(timeStep.cvt_state.secondaryRadialForce.beltCentrifugalForce.net, 'force'),
        },
        radialPulleyForce: conv(timeStep.cvt_state.secondaryRadialForce.radialPulleyForce, 'force'),
        net: conv(timeStep.cvt_state.secondaryRadialForce.net, 'force'),
      },
      friction: conv(timeStep.cvt_state.friction, 'force'),
      acceleration: conv(timeStep.cvt_state.acceleration, 'acceleration'),
      cvt_ratio: timeStep.cvt_state.cvt_ratio, // Dimensionless
      net: conv(timeStep.cvt_state.net, 'force'),
    },
  };
}

// TODO: Try to remove these two methods
// Simple recursive object converter - handles any nested structure
function convertAnyObject(obj: unknown, config: UnitConfiguration): unknown {
  if (typeof obj === 'number') {
    // We can't know the unit type without context, so just return the number
    return obj;
  }
  
  if (Array.isArray(obj)) {
    return obj.map(item => convertAnyObject(item, config));
  }
  
  if (obj && typeof obj === 'object') {
    const result: Record<string, unknown> = {};
    for (const [key, value] of Object.entries(obj)) {
      if (typeof value === 'number') {
        // Map common field names to unit types
        const unitType = getUnitTypeFromFieldName(key);
        if (unitType) {
          result[key] = convertValue(value, unitType, getTargetUnit(unitType, config));
        } else {
          result[key] = value; // Keep as-is if we can't determine unit type
        }
      } else {
        result[key] = convertAnyObject(value, config);
      }
    }
    return result;
  }
  
  return obj;
}

// Helper to guess unit type from field names
function getUnitTypeFromFieldName(fieldName: string): BaseUnitType | null {
  const fieldMappings: Record<string, BaseUnitType> = {
    // Forces
    'net': 'force',
    'force': 'force',
    'centrifugal_force': 'force',
    
    // Torques
    'torque': 'torque',
    'feedbackTorque': 'torque',
    
    // Angular velocity
    'angular_velocity': 'angular_velocity',
    
    // Distances
    'radius': 'distance',
    'compression': 'distance',
    
    // Angles
    'angle': 'angle',
    'wrap_angle': 'angle',
    'rotation': 'angle',
    
    // Mass
    'mass': 'mass',
    
    // Power
    'power': 'power',
    
    // Velocity
    'velocity': 'velocity',
    
    // Acceleration
    'acceleration': 'acceleration',
    
    // Time
    'time': 'time',
  };
  
  return fieldMappings[fieldName] || null;
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
