
type ParameterValue = string | number | boolean
type ParameterType = 'string' | 'number' | 'boolean'

interface BaseParameterConfig<T extends ParameterValue> {
    key: string;
    label: string;
    description: string;
    type: ParameterType;
    defaultValue: T;
    validation: (value: T) => boolean;
    units: string;
}

type StringParameter = BaseParameterConfig<string> & { type: 'string' };
type NumberParameter = BaseParameterConfig<number> & { type: 'number' };

type ParameterConfig = StringParameter | NumberParameter;

export const PARAMETERS: ParameterConfig[] = [
    {
        key: 'flyweightMass',
        label: 'Flyweight Mass',
        description: 'Weight of the primary pulley flyweight',
        type: 'number',
        defaultValue: 0.8,
        validation: (value) => typeof value === 'number' && value > 0,
        units: 'kg',
    },
    {
        key: 'primaryRampGeometry',
        label: 'Primary Ramp Geometry',
        description: 'Ramp geometry of the primary pulley',
        type: 'number',
        defaultValue: 1,
        validation: (value) => typeof value === 'number' && value >= 0,
        units: 'ratio',
    },
    {
        key: 'primarySpringRate',
        label: 'Primary Spring Rate',
        description: 'Spring rate of the primary pulley',
        type: 'number',
        defaultValue: 1000,
        validation: (value) => typeof value === 'number' && value > 0,
        units: 'N/m',
    },
    {
        key: 'primarySpringPretension',
        label: 'Primary Spring Pretension',
        description: 'Spring pretension of the primary pulley',
        type: 'number',
        defaultValue: 0,
        validation: (value) => typeof value === 'number' && value >= 0,
        units: 'm',
    },
    {
        key: 'secondaryHelixGeometry',
        label: 'Secondary Helix Geometry',
        description: 'Helix geometry of the secondary pulley',
        type: 'number',
        defaultValue: 1,
        validation: (value) => typeof value === 'number' && value >= 0,
        units: 'ratio',
    },
    {
        key: 'secondaryTorsionSpringRate',
        label: 'Secondary Torsion Spring Rate',
        description: 'Spring rate of the secondary torsional spring',
        type: 'number',
        defaultValue: 30,
        validation: (value) => typeof value === 'number' && value > 0,
        units: 'Nm/rad',
    },
    {
        key: 'secondaryCompressionSpringRate',
        label: 'Secondary Compression Spring Rate',
        description: 'Spring rate of the secondary compression spring',
        type: 'number',
        defaultValue: 1,
        validation: (value) => typeof value === 'number' && value > 0,
        units: 'N/m',
    },
    {
        key: 'secondaryRotationalSpringPretension',
        label: 'Secondary Rotational Spring Pretension',
        description: 'Pretension of the secondary rotational spring',
        type: 'number',
        defaultValue: 45,
        validation: (value) => typeof value === 'number' && value >= 0,
        units: 'degrees',
    },
    {
        key: 'secondaryLinearSpringPretension',
        label: 'Secondary Linear Spring Pretension',
        description: 'Pretension of the secondary linear spring',
        type: 'number',
        defaultValue: 0.1,
        validation: (value) => typeof value === 'number' && value >= 0,
        units: 'm',
    },
    {
        key: 'vehicleWeight',
        label: 'Vehicle Weight',
        description: 'Weight of the vehicle',
        type: 'number',
        defaultValue: 225,
        validation: (value) => typeof value === 'number' && value > 0,
        units: 'kg',
    },
    {
        key: 'driverWeight',
        label: 'Driver Weight',
        description: 'Weight of the driver',
        type: 'number',
        defaultValue: 75,
        validation: (value) => typeof value === 'number' && value > 0,
        units: 'kg',
    },
    {
        key: 'traction',
        label: 'Traction',
        description: 'Available traction force as a percentage',
        type: 'number',
        defaultValue: 100,
        validation: (value) => typeof value === 'number' && value >= 0 && value <= 100,
        units: '%',
    },
    {
        key: 'angleOfIncline',
        label: 'Angle of Incline',
        description: 'Incline angle of the surface',
        type: 'number',
        defaultValue: 0,
        validation: (value) => typeof value === 'number',
        units: 'degrees',
    },
    {
        key: 'totalDistance',
        label: 'Total Distance',
        description: 'Total simulation distance',
        type: 'number',
        defaultValue: 200,
        validation: (value) => typeof value === 'number' && value > 0,
        units: 'm',
    },
];