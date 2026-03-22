import { validators } from "@utils/validation"
import primaryCVT from "@assets/images/primary_cvt.png"
import secondaryCVT from "@assets/images/secondary_cvt.png"
import environment from "@assets/images/environment.png"

import type { components } from './api';
import type { PiecewiseRampConfig } from "./ramp";

// TODO: Pass defaults and parameters from backend when API supports it

export type ParameterValue = string | number | boolean | PiecewiseRampConfig | null
type ParameterType = 'string' | 'number' | 'boolean' | 'ramp'

export type ParameterGroup = 'primary' | 'ramp' | 'secondary' | 'helix' | 'environment'

export type Parameter =
  | 'FlyweightMass'
  | 'PrimaryRampConfig'
  | 'PrimarySpringRate'
  | 'PrimarySpringPretension'
  | 'SecondaryRampConfig'
  | 'SecondaryTorsionSpringRate'
  | 'SecondaryCompressionSpringRate'
  | 'SecondaryRotationalSpringPretension'
  | 'SecondaryLinearSpringPretension'
  | 'VehicleWeight'
  | 'DriverWeight'
  | 'Traction'
  | 'AngleOfIncline'
  | 'TotalDistance'

interface BaseParameterConfig<T extends ParameterValue, K extends ParameterType> {
    label: string;
    description: string;
    type: K;
    defaultValue: T;
    validate?: (value: string) => string | null;
    units: string;
    group: ParameterGroup;
    img?: string;
}

type StringParameter = BaseParameterConfig<string, 'string'>;
type NumberParameter = BaseParameterConfig<number, 'number'>;
type BooleanParameter = BaseParameterConfig<boolean, 'boolean'>;
type RampParameter = BaseParameterConfig<components['schemas']['PiecewiseRampConfigModel'] | null, 'ramp'>;

type ParameterConfig = StringParameter | NumberParameter | BooleanParameter | RampParameter;

export const GROUP_TITLES: Record<ParameterGroup, string> = {
    primary: 'Primary Pulley',
    ramp: 'Ramp Geometry',
    secondary: 'Secondary Pulley',
    helix: 'Helix Geometry',
    environment: 'Environment',
};

const PARAMETERS_IMPL = {
  FlyweightMass: {
    label: 'Flyweight Mass',
    description:
      'The total mass of the flyweight arm system in the primary pulley. This includes all flyweights (typically three in most designs) and the full assembly that rotates to generate centrifugal force. The flyweight mass is responsible for producing the main clamping force in the CVT system, as it determines how strongly the pulley can grip the belt as RPM increases. Enter the combined mass of all spinning components that contribute to centrifugal clamping.',
    type: 'number',
    defaultValue: 0.5,
    validate: validators.gtZero,
    units: 'kg',
    group: 'primary',
    img: primaryCVT,
  },
  PrimarySpringRate: {
    label: 'Primary Spring Rate',
      description:
        'The spring rate of the compressional spring in the primary pulley. This value sets how much force is needed to shift the pulley as the spring is compressed, affecting the entire shifting process. In the spring force equation (y = mx + b), the spring rate is the "m" (slope), controlling how quickly force increases with compression. A higher spring rate means more force is required for shifting at all points. Enter the spring rate value to set the overall resistance to shifting.',
    type: 'number',
    defaultValue: 12784,
    validate: validators.gtZero,
    units: 'N/m',
    group: 'primary',
    img: primaryCVT,
  },
  PrimarySpringPretension: {
    label: 'Primary Spring Pretension',
    description:
      'The initial compression (pretension) applied to the primary pulley spring before any movement occurs. This sets the starting force that must be overcome for the CVT to begin engaging. Pretension acts as an offset in the spring force equation (y = mx + b), shifting the engagement point. Note: The maximum pretension is limited by the physical design of each CVT. Adjust this value to control when the belt starts to be clamped, but be aware of hardware constraints.',
    type: 'number',
    defaultValue: 0.1,
    validate: validators.gteZero,
    units: 'm',
    group: 'primary',
    img: primaryCVT,
  },
  PrimaryRampConfig: {
    label: 'Ramp Geometry',
    description:
      'Design a custom flyweight ramp profile by combining different segment types. The ramp profile controls how the flyweight force changes as the pulley shifts. Use linear segments for constant slopes, circular arcs for smooth transitions, and spiral segments for advanced tuning. Leave null to use the default ramp.',
    type: 'ramp',
    defaultValue: {
      segments: [
        {
          type: 'circular' as const,
          length: 0.024,
          angle_start: 40,
          angle_end: 15,
          quadrant: 2,
        },
      ],
    } as components['schemas']['PiecewiseRampConfigModel'],
    units: '-',
    group: 'ramp',
  },
  SecondaryTorsionSpringRate: {
    label: 'Secondary Torsion Spring Rate',
    description:
      'The spring rate of the torsional aspect of the secondary pulley spring. This is the main force component, applying torque through the helix mechanism to resist shifting. In the spring force equation (y = mx + b), this rate is the "m" (slope), controlling how much torque increases as the spring is twisted. The secondary spring has both torsional and compressional effects, but torsional is much larger. For more on how the helix geometry affects this, see the helix geometry documentation.',
    type: 'number',
    defaultValue: 3.476,
    validate: validators.gtZero,
    units: 'Nm/rad',
    group: 'secondary',
    img: secondaryCVT,
  },
  SecondaryCompressionSpringRate: {
    label: 'Secondary Compression Spring Rate',
    description:
      'The spring rate of the compressional aspect of the secondary pulley spring. This is a smaller force component compared to the torsional aspect, but it still contributes to shifting. In the spring force equation (y = mx + b), this rate is the "m" (slope), controlling how quickly force decreases as the spring is decompressed. The secondary spring is primarily torsional, but the compressional effect is non-negligible and helps the pulley shift.',
    type: 'number',
    defaultValue: 3532,
    validate: validators.gtZero,
    units: 'N/m',
    group: 'secondary',
    img: secondaryCVT,
  },
  SecondaryRotationalSpringPretension: {
    label: 'Secondary Rotational Spring Pretension',
    description:
      'The initial pretension (offset) of the torsional component of the secondary pulley spring, measured in degrees. This sets the starting torque that resists shifting before any movement occurs, acting as the "b" in y = mx + b. Adjusting this value changes the baseline resistance to shifting, and is a key factor in how the helix mechanism responds to belt movement.',
    type: 'number',
    defaultValue: 200,
    validate: validators.gteZero,
    units: 'degrees',
    group: 'secondary',
    img: secondaryCVT,
  },
  SecondaryLinearSpringPretension: {
    label: 'Secondary Linear Spring Pretension',
    description:
      'The initial pretension (offset) of the compressional component of the secondary pulley spring, measured in meters. This sets the starting force that encourages shifting before any movement occurs, acting as the "b" in y = mx + b. Adjusting this value changes the baseline force helping the secndary pulley shift.',
    type: 'number',
    defaultValue: 0.1,
    validate: validators.gteZero,
    units: 'm',
    group: 'secondary', 
    img: secondaryCVT,
  },
    SecondaryRampConfig: {
    label: 'Helix Geometry',
    description:
      'Design a custom helix ramp profile for the secondary pulley by combining different segment types. The ramp profile controls how the torque-reactive mechanism responds as the pulley shifts. Use linear segments for constant slopes, circular arcs for smooth transitions, and spiral segments for advanced tuning. Leave null to use the default ramp.',
    type: 'ramp',
    defaultValue: {
      segments: [
        {
          type: 'linear' as const,
          length: 1,
          angle: 50,
        },
      ],
    } as components['schemas']['PiecewiseRampConfigModel'],
    units: '-',
    group: 'helix',
  },
  VehicleWeight: {
    label: 'Vehicle Weight',
  description: 'The mass of the vehicle itself. This is the "m" in F=ma, determining how much force is required to accelerate the vehicle as a whole.',
    type: 'number',
    defaultValue: 225,
    validate: validators.gtZero,
    units: 'kg',
    group: 'environment',
    img: environment,
  },
  DriverWeight: {
    label: 'Driver Weight',
  description: 'The mass of the driver. This is added to the vehicle mass as part of the "m" in F=ma, affecting the total force needed for acceleration.',
    type: 'number',
    defaultValue: 75,
    validate: validators.gtZero,
    units: 'kg',
    group: 'environment',
    img: environment,
  },
  Traction: {
    label: 'Traction',
  description: 'The available traction force as a percentage. This limits how much of the engine\'s force can be used for acceleration before wheel slip occurs. TODO: Make this value a force slip value rather than a percentage.',
    type: 'number',
    defaultValue: 100,
    validate: validators.percent,
    units: '%',
    group: 'environment',
    img: environment,
  },
  AngleOfIncline: {
    label: 'Angle of Incline',
  description: 'The angle of the surface the vehicle is driving on, in degrees. A higher angle means the vehicle must overcome more gravitational force to climb, reducing acceleration.',
    type: 'number',
    defaultValue: 0,
    validate: validators.gteZero,
    units: 'degrees',
    group: 'environment',
    img: environment,
  },
  TotalDistance: {
    label: 'Total Distance',
  description: 'The total distance the simulation will run before stopping. This is one way to set the simulation end condition (the other is a set amount of time).',
    type: 'number',
    defaultValue: 200,
    validate: validators.gtZero,
    units: 'm',
    group: 'environment',
    img: environment,
  },
} as const;

// Export with proper typing but preserve literal types
export const PARAMETERS: Record<Parameter, ParameterConfig> = PARAMETERS_IMPL;

// Create parameter state type using the const-asserted implementation
type TypeFromLiteral<T extends string> = T extends 'string' ? string : T extends 'number' ? number : T extends 'boolean' ? boolean : never;

export type ParameterState = {
  [K in Parameter]: TypeFromLiteral<(typeof PARAMETERS_IMPL)[K]['type']>;
};