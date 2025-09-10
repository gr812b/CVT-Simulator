
type ParameterValue = string | number | boolean
type ParameterType = 'string' | 'number' | 'boolean'

interface BaseParameterConfig<T extends ParameterValue> {
    key: string;
    label: string;
    description: string;
    type: ParameterType;
    defaultValue: T;
    validation: (value: T) => boolean;
}

type StringParameter = BaseParameterConfig<string> & { type: 'string' };
type NumberParameter = BaseParameterConfig<number> & { type: 'number' };
type BooleanParameter = BaseParameterConfig<number> & { type: 'number' };

type ParameterConfig = StringParameter | NumberParameter | BooleanParameter;

export const PARAMETERS: ParameterConfig[] = [
    {
        key: 'flyweightMass',
        label: 'flyweight mass',
        description: 'flyweight mass',
        type: 'number',
        validation: (value) => typeof value === 'number' && value > 0,
        defaultValue: 120,
    }
]