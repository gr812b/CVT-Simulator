import type { ParameterState } from '@types';
import type { RunBody } from '@utils/api';

/**
 * Maps the parameter state from the frontend to the API schema format.
 * The API expects snake_case field names while the frontend uses PascalCase.
 */
export const mapParametersToApiBody = (parameters: ParameterState): RunBody => {
  return {
    flyweight_mass: parameters.FlyweightMass,
    primary_ramp_config: parameters.PrimaryRampConfig || undefined,
    primary_spring_rate: parameters.PrimarySpringRate,
    primary_spring_pretension: parameters.PrimarySpringPretension,
    secondary_torsion_spring_rate: parameters.SecondaryTorsionSpringRate,
    secondary_compression_spring_rate: parameters.SecondaryCompressionSpringRate,
    secondary_rotational_spring_pretension: parameters.SecondaryRotationalSpringPretension,
    secondary_linear_spring_pretension: parameters.SecondaryLinearSpringPretension,
    vehicle_weight: parameters.VehicleWeight,
    driver_weight: parameters.DriverWeight,
    traction: parameters.Traction,
    angle_of_incline: parameters.AngleOfIncline,
    total_distance: parameters.TotalDistance,
  };
};