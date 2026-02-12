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
          { type: 'circular' as const, length: 0.024, angle_start: 60, angle_end: 40, quadrant: 3 },
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
    name: 'High Performance',
    parameters: {
      FlyweightMass: 0.45,
      PrimaryRampConfig: {
        segments: [
          { type: 'circular' as const, length: 0.015, angle_start: 65, angle_end: 50, quadrant: 3 },
          { type: 'circular' as const, length: 0.015, angle_start: 50, angle_end: 35, quadrant: 3 },
        ],
      } as RampConfig,
      PrimarySpringRate: 14000,
      PrimarySpringPretension: 0.12,
      SecondaryRampConfig: {
        segments: [
          { type: 'circular' as const, length: 0.012, angle_start: 65, angle_end: 45, quadrant: 3 },
          { type: 'circular' as const, length: 0.012, angle_start: 45, angle_end: 30, quadrant: 3 },
        ],
      } as RampConfig,
      SecondaryTorsionSpringRate: 3.8,
      SecondaryCompressionSpringRate: 3800,
      SecondaryRotationalSpringPretension: 220,
      SecondaryLinearSpringPretension: 0.12,
      VehicleWeight: 210,
      DriverWeight: 70,
      Traction: 100,
      AngleOfIncline: 0,
      TotalDistance: 250,
    },
  },
  {
    name: 'Hill Climb',
    parameters: {
      FlyweightMass: 0.55,
      PrimaryRampConfig: {
        segments: [
          { type: 'circular' as const, length: 0.020, angle_start: 55, angle_end: 45, quadrant: 3 },
          { type: 'circular' as const, length: 0.010, angle_start: 45, angle_end: 35, quadrant: 3 },
        ],
      } as RampConfig,
      PrimarySpringRate: 11500,
      PrimarySpringPretension: 0.15,
      SecondaryRampConfig: {
        segments: [
          { type: 'circular' as const, length: 0.018, angle_start: 55, angle_end: 40, quadrant: 3 },
        ],
      } as RampConfig,
      SecondaryTorsionSpringRate: 3.2,
      SecondaryCompressionSpringRate: 3200,
      SecondaryRotationalSpringPretension: 180,
      SecondaryLinearSpringPretension: 0.15,
      VehicleWeight: 230,
      DriverWeight: 80,
      Traction: 100,
      AngleOfIncline: 15,
      TotalDistance: 150,
    },
  },
  {
    name: 'Mud/Low Traction',
    parameters: {
      FlyweightMass: 0.52,
      PrimaryRampConfig: {
        segments: [
          { type: 'circular' as const, length: 0.022, angle_start: 58, angle_end: 42, quadrant: 3 },
        ],
      } as RampConfig,
      PrimarySpringRate: 12000,
      PrimarySpringPretension: 0.11,
      SecondaryRampConfig: {
        segments: [
          { type: 'circular' as const, length: 0.020, angle_start: 58, angle_end: 43, quadrant: 3 },
        ],
      } as RampConfig,
      SecondaryTorsionSpringRate: 3.3,
      SecondaryCompressionSpringRate: 3400,
      SecondaryRotationalSpringPretension: 190,
      SecondaryLinearSpringPretension: 0.11,
      VehicleWeight: 225,
      DriverWeight: 75,
      Traction: 65,
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
