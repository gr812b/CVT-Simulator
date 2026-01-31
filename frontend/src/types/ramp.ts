import type { components } from './api';

export type RampSegment = components['schemas']['PiecewiseRampConfigModel']['segments'][number];
export type PiecewiseRampConfig = components['schemas']['PiecewiseRampConfigModel'];
export type SegmentType = RampSegment['type'];

// Default values for creating new segments
export const SEGMENT_DEFAULTS: Record<SegmentType, Partial<RampSegment>> = {
    linear: { type: 'linear', length: 0.05, angle: -15 },
    circular: { type: 'circular', length: 0.05, angle_start: 45, angle_end: 15, quadrant: 3 },
};

type FieldMetadata = {
    label: string;
    units: string;
};

// Field metadata for display purposes (labels and units)
export const FIELD_METADATA: Record<string, FieldMetadata> = {
    length: { label: 'Length', units: 'm' },
    angle: { label: 'Angle', units: '°' },
    angle_start: { label: 'Start Angle', units: '°' },
    angle_end: { label: 'End Angle', units: '°' },
    quadrant: { label: 'Quadrant', units: '-' },
};