/**
 * Core unit conversion utilities.
 * All API values come in SI base units.
 */

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
  | 'inertia'            // kg*m²
  | 'area'               // m²
  | 'dimensionless'      // unitless ratios
  | 'dimensionless_rate'; // rate of change of dimensionless values (1/s)

// Available unit options for each base type
export type UnitOptions = {
  angular_velocity: 'rad/s' | 'rpm' | 'deg/s';
  angular_acceleration: 'rad/s²' | 'rpm/s' | 'deg/s²';
  mass: 'kg' | 'lb' | 'g';
  force: 'N' | 'lbf' | 'kN';
  torque: 'Nm' | 'lb·ft' | 'kNm';
  power: 'W' | 'hp' | 'kW';
  velocity: 'm/s' | 'mph' | 'km/h' | 'ft/s';
  distance: 'm' | 'ft' | 'km' | 'mi' | 'in' | 'cm';
  acceleration: 'm/s²' | 'ft/s²' | 'g';
  angle: 'rad' | 'deg';
  time: 's' | 'min' | 'hr';
  inertia: 'kg·m²' | 'lb·ft²' | 'g·cm²';
  area: 'm²' | 'ft²' | 'in²' | 'cm²';
  // Dimensionless set to empty for a ratio
  dimensionless: '' | '%'; 
  // Rate of change of dimensionless values
  dimensionless_rate: '1/s' | '1/min' | '%/s';
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
export const CONVERSION_FACTORS: { [K in BaseUnitType]: Record<UnitOptions[K], number> } = {
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
    'in': 39.3701,
    'cm': 100,
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
  inertia: {
    'kg·m²': 1,
    'lb·ft²': 23.7303, // 1 kg·m² = 23.7303 lb·ft²
    'g·cm²': 10000000, // 1 kg·m² = 10^7 g·cm²
  },
  area: {
    'm²': 1,
    'ft²': 10.7639,
    'in²': 1550.0031,
    'cm²': 10000,
  },
  dimensionless: {
    '': 1,
    '%': 100,
  },
  dimensionless_rate: {
    '1/s': 1,
    '1/min': 60,
    '%/s': 100,
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
    inertia: 'kg·m²',
    area: 'm²',
    dimensionless: '',
    dimensionless_rate: '1/s',
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
    inertia: 'lb·ft²',
    area: 'ft²',
    dimensionless: '%',
    dimensionless_rate: '1/s',
  } as UnitConfiguration,
  
  BAJA: {
    angular_velocity: 'rpm',
    angular_acceleration: 'rpm/s',
    power: 'hp',
    velocity: 'km/h',
    distance: 'm',
    torque: 'lb·ft',
    angle: 'deg',
    dimensionless_rate: '1/s',
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
export function convertValue<T extends BaseUnitType>(
  value: number,
  baseType: T,
  targetUnit: UnitOptions[T]
): number {
  const conversionTable = CONVERSION_FACTORS[baseType];
  const factor = conversionTable[targetUnit];
  return value * factor;
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
