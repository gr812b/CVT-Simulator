import createClient from 'openapi-fetch';
import type { components, paths } from './generated/backend';
import type { CINDERSimulationCaseDocument } from './generated/simulationCase';

/** The nested CINDER document is generated from CINDER's public JSON Schema. */
export type SimulationCaseDocument = CINDERSimulationCaseDocument;
export type PresetSummary = components['schemas']['PresetSummary'];
export type RunStatus = components['schemas']['RunStatusResponse'];
export type RunResult = components['schemas']['RunResultResponse'];
export type GeometryEndpointRadiiRequest = components['schemas']['EndpointRadiiGeometryStudyRequest'];

type JsonObject = Record<string, unknown>;

export interface LoadedPreset {
  id: string;
  name: string;
  description: string;
  simulationCase: SimulationCaseDocument;
}

export interface ValidationFinding {
  severity: 'error' | 'warning';
  code: string;
  message: string;
  location: string;
  documentPath?: string;
}

export interface SimulationCaseValidation {
  isValid: boolean;
  findings: ValidationFinding[];
}

export interface ProjectedField {
  key: string;
  label: string;
  dimension: string;
  canonicalUnit: string;
  values: unknown;
}

export interface ProjectedScalar {
  key: string;
  label: string;
  dimension: string;
  canonicalUnit: string;
  value: number | null;
}

export interface GeometryStudyResult {
  kind: 'geometry_design_response';
  summary: { kind: 'geometry_summary'; scalars: ProjectedScalar[] };
  path: { kind: 'geometry_path'; shape: number[]; axisKeys: string[]; columns: ProjectedField[] };
  feasibility: {
    isFeasible: boolean;
    findings: Array<{
      severity: 'error' | 'warning';
      code: string;
      message: string;
      shiftM: number | null;
    }>;
  };
}

export class ApiClientError extends Error {
  public constructor(
    message: string,
    public readonly status?: number,
    public readonly details?: unknown,
  ) {
    super(message);
    this.name = 'ApiClientError';
  }
}

const baseUrl = (import.meta.env.VITE_API_BASE_URL ?? '').replace(/\/+$/, '');
const client = createClient<paths>({ baseUrl });

function wireDocument(document: SimulationCaseDocument): JsonObject {
  // FastAPI deliberately treats the nested CINDER payload as JSON. The precise
  // frontend type comes from CINDER's schema; this cast remains only here.
  return document as unknown as JsonObject;
}

function failMessage(error: unknown): string {
  if (typeof error === 'object' && error !== null && 'error' in error) {
    const nested = (error as { error?: unknown }).error;
    if (typeof nested === 'object' && nested !== null && 'message' in nested) {
      const message = (nested as { message?: unknown }).message;
      if (typeof message === 'string') return message;
    }
  }
  return 'The backend rejected the request.';
}

function dataOrThrow<T>(response: { data?: T; error?: unknown; response: Response }): T {
  if (response.error || response.data === undefined) {
    throw new ApiClientError(failMessage(response.error), response.response.status, response.error);
  }
  return response.data;
}

function object(value: unknown, name: string): JsonObject {
  if (typeof value !== 'object' || value === null || Array.isArray(value)) {
    throw new ApiClientError(`Expected ${name} to be an object in the backend response.`);
  }
  return value as JsonObject;
}

function string(value: unknown, name: string): string {
  if (typeof value !== 'string') throw new ApiClientError(`Expected ${name} to be a string.`);
  return value;
}

function array(value: unknown, name: string): unknown[] {
  if (!Array.isArray(value)) throw new ApiClientError(`Expected ${name} to be an array.`);
  return value;
}

function numberOrNull(value: unknown, name: string): number | null {
  if (value === null) return null;
  if (typeof value !== 'number') throw new ApiClientError(`Expected ${name} to be a number or null.`);
  return value;
}

function parseValidation(value: unknown): SimulationCaseValidation {
  const report = object(value, 'validation');
  if (typeof report.is_valid !== 'boolean') throw new ApiClientError('Expected validation.is_valid.');
  return {
    isValid: report.is_valid,
    findings: array(report.findings, 'validation.findings').map((raw) => {
      const finding = object(raw, 'validation finding');
      const severity = string(finding.severity, 'finding.severity');
      if (severity !== 'error' && severity !== 'warning') throw new ApiClientError('Unexpected finding severity.');
      const documentPath = finding.document_path;
      return {
        severity,
        code: string(finding.code, 'finding.code'),
        message: string(finding.message, 'finding.message'),
        location: string(finding.location, 'finding.location'),
        ...(typeof documentPath === 'string' ? { documentPath } : {}),
      };
    }),
  };
}

function field(raw: unknown): ProjectedField {
  const value = object(raw, 'projected field');
  return {
    key: string(value.key, 'field.key'),
    label: string(value.label, 'field.label'),
    dimension: string(value.dimension, 'field.dimension'),
    canonicalUnit: string(value.canonical_unit, 'field.canonical_unit'),
    values: value.values,
  };
}

function scalar(raw: unknown): ProjectedScalar {
  const value = object(raw, 'projected scalar');
  return {
    key: string(value.key, 'scalar.key'),
    label: string(value.label, 'scalar.label'),
    dimension: string(value.dimension, 'scalar.dimension'),
    canonicalUnit: string(value.canonical_unit, 'scalar.canonical_unit'),
    value: numberOrNull(value.value, 'scalar.value'),
  };
}

function parseGeometryStudy(raw: unknown): GeometryStudyResult {
  const study = object(raw, 'study');
  if (study.kind !== 'geometry_design_response') {
    throw new ApiClientError("Expected CINDER study kind 'geometry_design_response'.");
  }
  const summary = object(study.summary, 'study.summary');
  const path = object(study.path, 'study.path');
  const feasibility = object(study.feasibility, 'study.feasibility');
  if (summary.kind !== 'geometry_summary' || path.kind !== 'geometry_path') {
    throw new ApiClientError('Geometry study projection has an unexpected shape.');
  }
  if (typeof feasibility.is_feasible !== 'boolean') {
    throw new ApiClientError('Expected study.feasibility.is_feasible.');
  }
  return {
    kind: 'geometry_design_response',
    summary: {
      kind: 'geometry_summary',
      scalars: array(summary.scalars, 'study.summary.scalars').map(scalar),
    },
    path: {
      kind: 'geometry_path',
      shape: array(path.shape, 'study.path.shape').map((value) => {
        if (typeof value !== 'number') throw new ApiClientError('Path shape must contain numbers.');
        return value;
      }),
      axisKeys: array(path.axis_keys, 'study.path.axis_keys').map((value) => string(value, 'axis key')),
      columns: array(path.columns, 'study.path.columns').map(field),
    },
    feasibility: {
      isFeasible: feasibility.is_feasible,
      findings: array(feasibility.findings, 'study.feasibility.findings').map((rawFinding) => {
        const finding = object(rawFinding, 'geometry feasibility finding');
        const severity = string(finding.severity, 'geometry finding severity');
        if (severity !== 'error' && severity !== 'warning') throw new ApiClientError('Unexpected feasibility severity.');
        return {
          severity,
          code: string(finding.code, 'geometry finding code'),
          message: string(finding.message, 'geometry finding message'),
          shiftM: numberOrNull(finding.shift_m, 'geometry finding shift_m'),
        };
      }),
    },
  };
}

/** The only Phase-3 frontend module that names backend endpoints. */
export async function listPresets(): Promise<PresetSummary[]> {
  return dataOrThrow(await client.GET('/api/v1/presets')).presets;
}

export async function loadPreset(presetId: string): Promise<LoadedPreset> {
  const data = dataOrThrow(await client.GET('/api/v1/presets/{preset_id}', {
    params: { path: { preset_id: presetId } },
  }));
  return {
    id: data.id,
    name: data.name,
    description: data.description,
    simulationCase: data.simulation_case as unknown as SimulationCaseDocument,
  };
}

export async function validateSimulationCase(document: SimulationCaseDocument): Promise<SimulationCaseValidation> {
  const data = dataOrThrow(await client.POST('/api/v1/simulation-cases/validate', {
    body: { simulation_case: wireDocument(document) },
  }));
  return parseValidation(data.validation);
}

export async function runEndpointRadiiGeometryStudy(
  request: GeometryEndpointRadiiRequest,
): Promise<GeometryStudyResult> {
  const data = dataOrThrow(await client.POST('/api/v1/studies/geometry/endpoint-radii', { body: request }));
  return parseGeometryStudy(data.study);
}

// These are prepared for the Phase-4 transport migration; no legacy UI calls them yet.
export async function submitSimulationRun(
  document: SimulationCaseDocument,
  options: Pick<components['schemas']['CreateRunRequest'], 'include_raw_trace' | 'include_reported_segments'> = {
    include_raw_trace: false,
    include_reported_segments: false,
  },
): Promise<RunStatus> {
  return dataOrThrow(await client.POST('/api/v1/runs', {
    body: { simulation_case: wireDocument(document), ...options },
  }));
}

export async function getSimulationRun(runId: string): Promise<RunStatus> {
  return dataOrThrow(await client.GET('/api/v1/runs/{run_id}', { params: { path: { run_id: runId } } }));
}

export async function getSimulationResult(runId: string): Promise<RunResult> {
  return dataOrThrow(await client.GET('/api/v1/runs/{run_id}/result', { params: { path: { run_id: runId } } }));
}
