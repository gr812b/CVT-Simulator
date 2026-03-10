import type { SavedSimulation } from '@utils/localStorage';
import type { components, ParameterState } from '@types';

type RampConfig = components['schemas']['PiecewiseRampConfigModel'];

/**
 * Default parameter sets that are always available
 * These cannot be deleted and are separate from localStorage
 */
export const DEFAULT_SIMULATIONS = [
  {
    name: 'Default Configuration',
    parameters: {
      FlyweightMass: 0.5,
      PrimaryRampConfig: {
        segments: [
          { type: 'circular' as const, length: 0.024, angle_start: 60, angle_end: 40, quadrant: 3 },
        ],
      } as RampConfig,
      PrimarySpringRate: 12784,
      PrimarySpringPretension: 0.1,
      SecondaryRampConfig: {
        segments: [
          { type: 'linear' as const, length: 1, angle: -10 },
        ],
      } as RampConfig,
      SecondaryTorsionSpringRate: 3.476,
      SecondaryCompressionSpringRate: 3532,
      SecondaryRotationalSpringPretension: 200,
      SecondaryLinearSpringPretension: 0.1,
      VehicleWeight: 225,
      DriverWeight: 75,
      Traction: 100,
      AngleOfIncline: 0,
      TotalDistance: 200,
    },
  },
  {
    name: 'Hill Climb (25)',
    parameters: {
      FlyweightMass: 0.5,
      PrimaryRampConfig: {
        segments: [
          { type: 'circular' as const, length: 0.024, angle_start: 60, angle_end: 40, quadrant: 3 },
        ],
      } as RampConfig,
      PrimarySpringRate: 12784,
      PrimarySpringPretension: 0.1,
      SecondaryRampConfig: {
        segments: [
          { type: 'linear' as const, length: 1, angle: -10 },
        ],
      } as RampConfig,
      SecondaryTorsionSpringRate: 3.476,
      SecondaryCompressionSpringRate: 3532,
      SecondaryRotationalSpringPretension: 200,
      SecondaryLinearSpringPretension: 0.1,
      VehicleWeight: 225,
      DriverWeight: 75,
      Traction: 100,
      AngleOfIncline: 25,
      TotalDistance: 200,
    },
  },
  {
    name: 'Our Lightest Driver',
    parameters: {
      FlyweightMass: 0.5,
      PrimaryRampConfig: {
        segments: [
          { type: 'circular' as const, length: 0.024, angle_start: 60, angle_end: 40, quadrant: 3 },
        ],
      } as RampConfig,
      PrimarySpringRate: 12784,
      PrimarySpringPretension: 0.1,
      SecondaryRampConfig: {
        segments: [
          { type: 'linear' as const, length: 1, angle: -10 },
        ],
      } as RampConfig,
      SecondaryTorsionSpringRate: 3.476,
      SecondaryCompressionSpringRate: 3532,
      SecondaryRotationalSpringPretension: 200,
      SecondaryLinearSpringPretension: 0.1,
      VehicleWeight: 225,
      DriverWeight: 35,
      Traction: 100,
      AngleOfIncline: 0,
      TotalDistance: 200,
    },
  },
];

/**
 * Get all default simulations with proper ID and timestamp fields
 */
export const getDefaultSimulations = (): SavedSimulation[] => {
  // Use negative IDs to distinguish from user-created simulations
  return DEFAULT_SIMULATIONS.map((sim, index) => ({
    ...sim,
    id: `default_${index}`,
    parameters: sim.parameters as ParameterState,
    createdAt: new Date(0).toISOString(),
    updatedAt: new Date(0).toISOString(),
    schemaVersion: 1,
  }));
};

/**
 * Check if a simulation is a default (cannot be deleted)
 */
export const isDefaultSimulation = (id: string): boolean => {
  return id.startsWith('default_');
};
