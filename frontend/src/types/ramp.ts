import type { components } from './api';

type RampSegment = components['schemas']['PiecewiseRampConfigModel']['segments'][number];
type SegmentType = RampSegment['type'];

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