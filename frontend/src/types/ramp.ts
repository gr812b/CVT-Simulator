export type SegmentType = 'linear' | 'circular' | 'cubic_spiral_zero_k1' | 'cubic_spiral_zero_zero' | 'euler_spiral' | 'pro_defined';

export const SEGMENT_LABELS: Record<SegmentType, string> = {
    linear: 'Linear',
    circular: 'Circular Arc',
    cubic_spiral_zero_k1: 'Cubic Spiral (Zero-K1)',
    cubic_spiral_zero_zero: 'Cubic Spiral (Zero-Zero)',
    euler_spiral: 'Euler Spiral',
    pro_defined: 'Pro Defined',
};

export const FIELD_KEY_MAP: Record<string, string> = {
    Length: 'length',
    Slope: 'slope',
    Radius: 'radius',
    'Theta Start': 'theta_start',
    'Theta End': 'theta_end',
    'Slope Start': 'slope_start',
    'Slope End': 'slope_end',
    'Target Curvature': 'target_curvature',
};

type SegmentFieldDef = {
    label: string;
    units: string;
    defaultValue: number;
};

export const SEGMENT_FIELD_CONFIGS = {
    linear: [
        { label: 'Length', units: 'm', defaultValue: 0.1 },
        { label: 'Slope', units: '-', defaultValue: 0.5 },
    ],
    circular: [
        { label: 'Length', units: 'm', defaultValue: 0.1 },
        { label: 'Radius', units: 'm', defaultValue: 0.05 },
        { label: 'Theta Start', units: 'rad', defaultValue: 0 },
        { label: 'Theta End', units: 'rad', defaultValue: 0.785 },
    ],
    cubic_spiral_zero_k1: [
        { label: 'Length', units: 'm', defaultValue: 0.1 },
        { label: 'Slope Start', units: 'rad', defaultValue: 0.3 },
        { label: 'Slope End', units: 'rad', defaultValue: 0.4 },
        { label: 'Target Curvature', units: '-', defaultValue: 10.0 },
    ],
    cubic_spiral_zero_zero: [],
    euler_spiral: [],
    pro_defined: [],
} as const satisfies Record<SegmentType, ReadonlyArray<SegmentFieldDef>>;

export type SegmentFieldConfigs = typeof SEGMENT_FIELD_CONFIGS;