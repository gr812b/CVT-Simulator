import type { SimulationCaseDocument } from '@api/client';

export type ChannelRole = 'comparison' | 'boundary_input' | 'diagnostic' | 'unused';
export type UncertaintyStatus = 'pending' | 'known' | 'not_applicable';

export interface MeasurementUncertainty {
  status: UncertaintyStatus;
  absolute?: number;
  unit?: string;
  source?: string;
  notes?: string;
}

export interface ChannelConfig {
  key: string;
  label: string;
  unit: string;
  enabled: boolean;
  role: ChannelRole;
  mapping: 'primary_speed' | 'secondary_speed' | 'shift_position' | 'none';
  initializeState: boolean;
  uncertainty: MeasurementUncertainty;
}

export interface ParsedDynoData {
  filename: string;
  rawCsv: string;
  timeS: number[];
  columns: Record<string, number[]>;
}

export interface MeasurementMetadata {
  uncertainty: MeasurementUncertainty;
  method?: string;
  instrument?: string;
  date?: string;
}

export interface ValidationWorkflowDefaults {
  primaryMode?: 'physical' | 'track_measured_speed';
  secondaryMode?: 'physical' | 'track_measured_speed';
  axialMode?: 'physical' | 'track_measured_position';
  speedTracking?: {
    proportionalGainNmSPerRad: number | null;
    torqueLimitNm: number | null;
    equivalentInertiaKgM2: number | null;
    feedforwardInertiaKgM2: number | null;
  };
  axialTracking?: {
    positionGainNPerM: number | null;
    speedGainNSPerM: number | null;
    forceLimitN: number | null;
  };
  manualInitialState?: {
    primaryAngularSpeedRadPerS: number;
    secondaryAngularSpeedRadPerS: number;
    beltSpeedMPerS: number;
    shiftPositionM: number;
    shiftSpeedMPerS: number;
  };
}

export interface ValidationWorkspaceModel {
  id: string;
  accountId: string;
  setupDocument: SimulationCaseDocument;
  metrology: Record<string, MeasurementMetadata>;
  controllerTemplates: Array<Record<string, unknown>>;
  workflowDefaults: ValidationWorkflowDefaults;
  updatedAt: string;
}

export interface CropWindow {
  startS: number;
  endS: number;
}

export interface SignalMetric {
  bias: number;
  mae: number;
  rmse: number;
  maxAbs: number;
  count: number;
}
