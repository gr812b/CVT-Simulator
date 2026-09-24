import type { SimulationCaseDocument } from '@api/client';

export type ChannelRole = 'comparison' | 'boundary_input' | 'diagnostic' | 'unused';
export type UncertaintyStatus = 'pending' | 'known' | 'not_applicable';
export type UncertaintyModel = 'absolute' | 'rpm_tooth_timing';

export interface MeasurementUncertainty {
  status: UncertaintyStatus;
  model?: UncertaintyModel;
  absolute?: number;
  unit?: string;
  source?: string;
  notes?: string;
  /** Number of evenly spaced teeth or trigger edges per mechanical revolution. */
  teethPerRevolution?: number;
  /** Conservative ± timestamp uncertainty for one recorded tooth hit, in seconds. */
  timestampUncertaintyS?: number;
  /** Uniform spacing used when constructing a replay reference, in seconds. */
  replaySampleIntervalS?: number;
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
  /** Original acquisition layout. Wide is the historical validation CSV; per_tooth_raw is the RP2040 logger format. */
  sourceFormat?: 'wide' | 'per_tooth_raw';
  sourceMetadata?: {
    primaryTeethPerRevolution?: number;
    secondaryTeethPerRevolution?: number;
    timestampUncertaintyS?: number;
    edgeCountPresent?: boolean;
  };
}

export interface MeasurementMetadata {
  uncertainty: MeasurementUncertainty;
  method?: string;
  instrument?: string;
  date?: string;
}

export type ShaftValidationMode = 'physical' | 'replay_measured_speed';

export interface SavedValidationDataset {
  filename: string;
  rawCsv: string;
  cropStartS: number;
  cropEndS: number;
  channels: ChannelConfig[];
}

export interface ValidationWorkflowDefaults {
  /** `track_measured_speed` remains accepted as a legacy autosaved workspace value. */
  primaryMode?: ShaftValidationMode | 'track_measured_speed';
  /** `track_measured_speed` remains accepted as a legacy autosaved workspace value. */
  secondaryMode?: ShaftValidationMode | 'track_measured_speed';
  speedReplay?: {
    trackingGainNmSPerRad: number | null;
  };
  validationIntegrator?: {
    relativeTolerance: number;
    absoluteTolerance: number;
    maxStepS: number;
  };
  rpmMeasurementDefaults?: {
    primary?: MeasurementUncertainty;
    secondary?: MeasurementUncertainty;
  };
  activeDataset?: SavedValidationDataset;
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
