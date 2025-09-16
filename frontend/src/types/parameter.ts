
type ParameterValue = string | number | boolean
type ParameterType = 'string' | 'number' | 'boolean'

export type ParameterGroup = 'primary' | 'secondary' | 'environment'

export type Parameter =
  | 'FlyweightMass'
  | 'PrimarySpringRate'
  | 'PrimarySpringPretension'
  | 'SecondaryTorsionSpringRate'
  | 'SecondaryCompressionSpringRate'
  | 'SecondaryRotationalSpringPretension'
  | 'SecondaryLinearSpringPretension'
  | 'VehicleWeight'
  | 'DriverWeight'
  | 'Traction'
  | 'AngleOfIncline'
  | 'TotalDistance'

interface BaseParameterConfig<T extends ParameterValue> {
    label: string;
    description: string;
    type: ParameterType;
    defaultValue: T;
    validation: (value: T) => boolean;
    units: string;
    group: ParameterGroup;
}

type StringParameter = BaseParameterConfig<string> & { type: 'string' };
type NumberParameter = BaseParameterConfig<number> & { type: 'number' };

type ParameterConfig = StringParameter | NumberParameter;

export const GROUP_TITLES: Record<ParameterGroup, string> = {
    primary: 'Primary Pulley',
    secondary: 'Secondary Pulley',
    environment: 'Environment',
};

export const PARAMETERS: Record<Parameter, ParameterConfig> = {
  FlyweightMass: {
    label: 'Flyweight Mass',
    description: 'Weight of the primary pulley flyweight',
    type: 'number',
    defaultValue: 0.8,
    validation: (value) => typeof value === 'number' && value > 0,
    units: 'kg',
    group: 'primary',
  },
  PrimarySpringRate: {
    label: 'Primary Spring Rate',
    description: 'Spring rate of the primary pulley',
    type: 'number',
    defaultValue: 1000,
    validation: (value) => typeof value === 'number' && value > 0,
    units: 'N/m',
    group: 'primary',
  },
  PrimarySpringPretension: {
    label: 'Primary Spring Pretension',
    description: 'Spring pretension of the primary pulley',
    type: 'number',
    defaultValue: 0,
    validation: (value) => typeof value === 'number' && value >= 0,
    units: 'm',
    group: 'primary',
  },
  SecondaryTorsionSpringRate: {
    label: 'Secondary Torsion Spring Rate',
    description: 'Spring rate of the secondary torsional spring',
    type: 'number',
    defaultValue: 30,
    validation: (value) => typeof value === 'number' && value > 0,
    units: 'Nm/rad',
    group: 'secondary',
  },
  SecondaryCompressionSpringRate: {
    label: 'Secondary Compression Spring Rate',
    description: 'Spring rate of the secondary compression spring',
    type: 'number',
    defaultValue: 1,
    validation: (value) => typeof value === 'number' && value > 0,
    units: 'N/m',
    group: 'secondary',
  },
  SecondaryRotationalSpringPretension: {
    label: 'Secondary Rotational Spring Pretension',
    description: 'Pretension of the secondary rotational spring',
    type: 'number',
    defaultValue: 45,
    validation: (value) => typeof value === 'number' && value >= 0,
    units: 'degrees',
    group: 'secondary',
  },
  SecondaryLinearSpringPretension: {
    label: 'Secondary Linear Spring Pretension',
    description: 'Pretension of the secondary linear spring',
    type: 'number',
    defaultValue: 0.1,
    validation: (value) => typeof value === 'number' && value >= 0,
    units: 'm',
    group: 'secondary',
  },
  VehicleWeight: {
    label: 'Vehicle Weight',
    description: 'Weight of the vehicle',
    type: 'number',
    defaultValue: 225,
    validation: (value) => typeof value === 'number' && value > 0,
    units: 'kg',
    group: 'environment',
  },
  DriverWeight: {
    label: 'Driver Weight',
    description: 'Weight of the driver',
    type: 'number',
    defaultValue: 75,
    validation: (value) => typeof value === 'number' && value > 0,
    units: 'kg',
    group: 'environment',
  },
  Traction: {
    label: 'Traction',
    description: 'Available traction force as a percentage',
    type: 'number',
    defaultValue: 100,
    validation: (value) =>
      typeof value === 'number' && value >= 0 && value <= 100,
    units: '%',
    group: 'environment',
  },
  AngleOfIncline: {
    label: 'Angle of Incline',
    description: 'Incline angle of the surface',
    type: 'number',
    defaultValue: 0,
    validation: (value) => typeof value === 'number',
    units: 'degrees',
    group: 'environment',
  },
  TotalDistance: {
    label: 'Total Distance',
    description: 'Total simulation distance',
    type: 'number',
    defaultValue: 200,
    validation: (value) => typeof value === 'number' && value > 0,
    units: 'm',
    group: 'environment',
  },
}