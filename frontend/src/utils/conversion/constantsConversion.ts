/**
 * Unit conversion utilities for simulator constants (CarSpecs).
 */

import type { components } from '@types';
import { convertValue, getTargetUnit, type UnitConfiguration, DEFAULT_UNIT_CONFIG } from './unitConversion';

type CarSpecs = components['schemas']['CarSpecs'];

/**
 * Convert CarSpecs constants from SI units to target units.
 * All values from the API come in SI units.
 */
export function convertConstants(
  constants: CarSpecs,
  config: UnitConfiguration = DEFAULT_UNIT_CONFIG
): CarSpecs {
  const conv = <T extends import('./unitConversion').BaseUnitType>(value: number, type: T) => 
    convertValue(value, type, getTargetUnit(type, config));

  return {
    // Inertia values
    engine_inertia: conv(constants.engine_inertia, 'inertia'),
    driveline_inertia: conv(constants.driveline_inertia, 'inertia'),
    
    // Drivetrain
    gearbox_ratio: conv(constants.gearbox_ratio, 'dimensionless'),
    wheel_radius: conv(constants.wheel_radius, 'distance'),
    
    // Aerodynamics
    frontal_area: conv(constants.frontal_area, 'area'),
    drag_coefficient: conv(constants.drag_coefficient, 'dimensionless'),
    
    // Pulley geometry
    sheave_angle: conv(constants.sheave_angle, 'angle'),
    initial_flyweight_radius: conv(constants.initial_flyweight_radius, 'distance'),
    helix_radius: conv(constants.helix_radius, 'distance'),
    
    // Belt specifications
    belt_angle: conv(constants.belt_angle, 'angle'),
    belt_height: conv(constants.belt_height, 'distance'),
    belt_length: conv(constants.belt_length, 'distance'),
    belt_width_top: conv(constants.belt_width_top, 'distance'),
    
    // Pulley radii
    min_prim_radius: conv(constants.min_prim_radius, 'distance'),
    max_sec_radius: conv(constants.max_sec_radius, 'distance'),
    initial_sheave_displacement: conv(constants.initial_sheave_displacement, 'distance'),
    
    // Computed fields (read-only)
    belt_width_bottom: conv(constants.belt_width_bottom, 'distance'),
    belt_cross_sectional_area: conv(constants.belt_cross_sectional_area, 'area'),
    max_shift: conv(constants.max_shift, 'distance'),
    center_to_center: conv(constants.center_to_center, 'distance'),
  };
}

/**
 * Helper to convert a single constant value.
 * Useful when you only need to convert one value at a time.
 */
export function convertConstantValue(
  value: number,
  baseType: import('./unitConversion').BaseUnitType,
  config: UnitConfiguration = DEFAULT_UNIT_CONFIG
): number {
  return convertValue(value, baseType, getTargetUnit(baseType, config));
}
