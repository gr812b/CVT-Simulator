import type { components } from './api';

export type RampSegment = components['schemas']['PiecewiseRampConfigModel']['segments'][number];
export type PiecewiseRampConfig = components['schemas']['PiecewiseRampConfigModel'];
export type SegmentType = RampSegment['type'];

// Default values for creating new segments
// TODO: Pass defaults from backend when API supports it
export const SEGMENT_DEFAULTS: Record<SegmentType, Partial<RampSegment>> = {
    linear: { type: 'linear', length: 0.1, slope: 0.5 },
    circular: { type: 'circular', length: 0.1, radius: 0.05, theta_start: 0.01, theta_end: 0.785 },
    cubic_spiral_zero_k1: { type: 'cubic_spiral_zero_k1', length: 0.1, slope_start: 0.3, slope_end: 0.4, target_curvature: 10.0 },
    cubic_spiral_zero_zero: { type: 'cubic_spiral_zero_zero', length: 0.1, slope_start: 0.3, slope_end: 0.4 },
    euler_spiral: { type: 'euler_spiral', length: 0.1, slope_start: 0.3, slope_end: 0.4 },
    pro_defined: { type: 'pro_defined', length: 0.1, prev_seg_height: 0, end_length: 0.05, initial_slope: 0.5, r_initial: 0.05 },
};

type FieldMetadata = {
    label: string;
    units: string;
};

// Field metadata for display purposes (labels and units)
export const FIELD_METADATA: Record<string, FieldMetadata> = {
    length: { label: 'Length', units: 'm' },
    slope: { label: 'Slope', units: '-' },
    radius: { label: 'Radius', units: 'm' },
    theta_start: { label: 'Theta Start', units: 'rad' },
    theta_end: { label: 'Theta End', units: 'rad' },
    slope_start: { label: 'Slope Start', units: 'rad' },
    slope_end: { label: 'Slope End', units: 'rad' },
    target_curvature: { label: 'Target Curvature', units: '-' },
    prev_seg_height: { label: 'Previous Segment Height', units: 'm' },
    end_length: { label: 'End Length', units: 'm' },
    initial_slope: { label: 'Initial Slope', units: '-' },
    r_initial: { label: 'Initial Radius', units: 'm' },
};