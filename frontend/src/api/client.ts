import createClient from 'openapi-fetch';
import type { components, paths } from './generated/backend';
import type { CINDERSimulationCaseDocument } from './generated/simulationCase';

/**
 * The only frontend module that names backend routes or consumes OpenAPI
 * transport envelopes. Everything else works with these small application
 * types and CINDER's versioned simulation document.
 */

export type SimulationCaseDocument = CINDERSimulationCaseDocument;
export type PresetSummary = components['schemas']['PresetSummary'];

export type RunLifecycleStatus = 'queued' | 'validating' | 'running' | 'completed' | 'failed' | 'timed_out';

export interface RunStatus {
  id: string;
  status: RunLifecycleStatus;
  submittedAt: string;
  startedAt: string | null;
  completedAt: string | null;
  error: ApiProblem | null;
}

export interface ApiProblem {
  code: string;
  message: string;
  details?: unknown;
}

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

export type EditableValueKind = 'number' | 'integer' | 'boolean' | 'string' | 'enum' | 'object' | 'array';
export type FieldExposure = 'design' | 'scenario' | 'advanced_execution';

export interface EditableFieldDescriptor {
  pathTemplate: string;
  label: string;
  description: string;
  valueKind: EditableValueKind;
  section: string;
  dimension?: string;
  canonicalUnit?: string;
  required: boolean;
  minimum?: number;
  maximum?: number;
  enumValues: string[];
  when?: Record<string, string>;
  exposure: FieldExposure;
}

export interface ComponentParameterDescriptor {
  key: string;
  label: string;
  canonicalUnit: string;
  dimension?: string;
  valueKind: 'number' | 'object';
  required: boolean;
  description: string;
  minimum?: number;
  maximum?: number;
}

export interface ComponentDescriptor {
  kind: string;
  label: string;
  description: string;
  supportedMounts: string[];
  parameters: ComponentParameterDescriptor[];
}

export interface EditorSchema {
  fields: EditableFieldDescriptor[];
  supportedDiscriminators: Record<string, string[]>;
  components: ComponentDescriptor[];
}

export interface ReportColumn {
  key: string;
  label: string;
  description: string;
  group: string;
  dimension: string;
  canonicalUnit: string;
  values: Array<number | null>;
}

export interface ReportSegmentRange {
  segmentIndex: number;
  startIndex: number;
  endIndex: number;
  mode: Record<string, string | null>;
}

export interface ReportTable {
  axisKey: string;
  rowCount: number;
  columns: ReportColumn[];
  segmentRanges: ReportSegmentRange[];
  preservesDuplicateTransitionTimes: boolean;
}

export interface SimulationTransition {
  timeS: number;
  previousMode: Record<string, string | null>;
  firedEventNames: string[];
  reason: string;
  terminates: boolean;
  metadata: unknown;
  postTransitionState: Record<string, number>;
}

export interface SimulationResult {
  contractVersion: number;
  kind: 'simulation_result';
  conventions: Record<string, unknown>;
  metrics: Record<string, unknown>;
  summary: Record<string, unknown>;
  warnings: string[];
  reportTable: ReportTable;
  transitions: SimulationTransition[];
}

export interface CompletedSimulationRun {
  run: RunStatus;
  inputDocumentSnapshot: SimulationCaseDocument;
  result: SimulationResult;
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
    findings: Array<{ severity: 'error' | 'warning'; code: string; message: string; shiftM: number | null }>;
  };
}

export type GeometryEndpointRadiiRequest = components['schemas']['EndpointRadiiGeometryStudyRequest'];

export type LibraryResource = 'engines' | 'cvt-designs' | 'output-systems' | 'vehicle-assemblies';

export interface LibraryObjectSummary {
  id: string;
  resource: LibraryResource;
  name: string;
  description: string | null;
  lifecycleStatus: string;
  catalogStatus: string;
  catalogPriority: number;
  isDefault: boolean;
  sourceLabel: string | null;
  releasedVersionId: string | null;
}

export interface TuneSummary {
  id: string;
  name: string;
  notes: string | null;
  values: Record<string, unknown>;
  vehicleAssemblyId: string;
  cvtDesignId: string;
}

export interface LoadCaseSummary {
  id: string;
  name: string;
  kind: string;
  visibility: string;
}

export interface ExecutionPresetSummary {
  id: string;
  name: string;
  kind: string;
  isSystemDefault: boolean;
}

export type TuneParameterGroup = 'primary' | 'ramp' | 'secondary' | 'helix';
export type TuneParameterKind = 'number' | 'ramp';

export interface TuneParameter {
  key: string;
  label: string;
  description: string;
  group: TuneParameterGroup;
  kind: TuneParameterKind;
  canonicalUnit: string;
  dimension?: string;
  minimum?: number;
  maximum?: number;
  defaultValue?: unknown;
}

export interface CvtDesignVersionSummary {
  id: string;
  objectId: string;
  payload: Record<string, unknown>;
  tuningSchema: { parameters: TuneParameter[] };
}

export interface VehicleAssemblyVersionSummary {
  id: string;
  objectId: string;
  assemblyPayload: {
    engineVersionId: string;
    cvtDesignVersionId: string;
    outputSystemVersionId: string;
  };
}

export interface LibraryRunSelection {
  accountId: string;
  createdByUserId: string | null;
  vehicleAssemblyVersionId: string;
  tuneId: string | null;
  loadCaseId: string | null;
  executionPresetId: string | null;
}

export interface DefaultRunSetup {
  accountId: string;
  createdByUserId: string | null;
  vehicleAssemblies: LibraryObjectSummary[];
  selectedVehicleAssembly: LibraryObjectSummary;
  tunes: TuneSummary[];
  selectedTune: TuneSummary | null;
  loadCases: LoadCaseSummary[];
  selectedLoadCase: LoadCaseSummary | null;
  executionPresets: ExecutionPresetSummary[];
  selectedExecutionPreset: ExecutionPresetSummary | null;
  vehicleAssemblyVersion: VehicleAssemblyVersionSummary;
  cvtDesignVersion: CvtDesignVersionSummary;
  tuningParameters: TuneParameter[];
  selection: LibraryRunSelection;
}

export interface RunPreview {
  profileName: string;
  profileVersion: number;
  originalRowCount: number;
  rowCount: number;
  columns: Record<string, Array<number | null>>;
}

type JsonObject = Record<string, unknown>;

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

export class SimulationRunError extends ApiClientError {
  public constructor(public readonly run: RunStatus) {
    super(run.error?.message ?? `Simulation run ${run.status}.`, undefined, run.error);
    this.name = 'SimulationRunError';
  }
}

const baseUrl = (import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000').replace(/\/+$/, '');
const client = createClient<paths>({ baseUrl });

/**
 * Local-development/demo IDs seeded by the backend database initializer.
 * These are explicitly test/demo defaults; real auth should replace only this
 * configuration boundary instead of leaking account/user IDs across the UI.
 */
export const DEMO_ACCOUNT_ID = import.meta.env.VITE_DEMO_ACCOUNT_ID ?? '00000000-0000-4000-8000-000000000002';
export const DEMO_USER_ID = import.meta.env.VITE_DEMO_USER_ID ?? '00000000-0000-4000-8000-000000000001';

function object(value: unknown, name: string): JsonObject {
  if (typeof value !== 'object' || value === null || Array.isArray(value)) {
    throw new ApiClientError(`Expected ${name} to be an object in the backend response.`);
  }
  return value as JsonObject;
}

function array(value: unknown, name: string): unknown[] {
  if (!Array.isArray(value)) throw new ApiClientError(`Expected ${name} to be an array.`);
  return value;
}

function string(value: unknown, name: string): string {
  if (typeof value !== 'string') throw new ApiClientError(`Expected ${name} to be a string.`);
  return value;
}

function number(value: unknown, name: string): number {
  if (typeof value !== 'number' || !Number.isFinite(value)) {
    throw new ApiClientError(`Expected ${name} to be a finite number.`);
  }
  return value;
}

function numberOrNull(value: unknown, name: string): number | null {
  return value === null ? null : number(value, name);
}

function boolean(value: unknown, name: string): boolean {
  if (typeof value !== 'boolean') throw new ApiClientError(`Expected ${name} to be a boolean.`);
  return value;
}

function optionalNumber(value: unknown, name: string): number | undefined {
  return value === undefined ? undefined : number(value, name);
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

async function apiJson<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  if (init.body !== undefined && !headers.has('Content-Type')) {
    headers.set('Content-Type', 'application/json');
  }
  const response = await fetch(`${baseUrl}${path}`, { ...init, headers });
  const text = await response.text();
  const payload = text.length > 0 ? JSON.parse(text) as unknown : null;
  if (!response.ok) {
    throw new ApiClientError(failMessage(payload), response.status, payload);
  }
  return payload as T;
}

function wireDocument(document: SimulationCaseDocument): JsonObject {
  return document as unknown as JsonObject;
}

function parseProblem(raw: unknown): ApiProblem | null {
  if (raw === null || raw === undefined) return null;
  const problem = object(raw, 'run error');
  return {
    code: string(problem.code, 'run error.code'),
    message: string(problem.message, 'run error.message'),
    ...(problem.details === undefined ? {} : { details: problem.details }),
  };
}

function parseRunStatus(raw: unknown): RunStatus {
  const value = object(raw, 'run status');
  const status = string(value.status, 'run status.status') as RunLifecycleStatus;
  if (!['queued', 'validating', 'running', 'completed', 'failed', 'timed_out'].includes(status)) {
    throw new ApiClientError(`Unexpected run status '${status}'.`);
  }
  return {
    id: string(value.id, 'run status.id'),
    status,
    submittedAt: string(value.submitted_at, 'run status.submitted_at'),
    startedAt: value.started_at === null ? null : string(value.started_at, 'run status.started_at'),
    completedAt: value.completed_at === null ? null : string(value.completed_at, 'run status.completed_at'),
    error: parseProblem(value.error),
  };
}


function parseLibraryObject(raw: unknown): LibraryObjectSummary {
  const item = object(raw, 'library object');
  const resource = string(item.resource, 'library object.resource') as LibraryResource;
  if (!['engines', 'cvt-designs', 'output-systems', 'vehicle-assemblies'].includes(resource)) {
    throw new ApiClientError(`Unexpected library resource '${resource}'.`);
  }
  return {
    id: string(item.id, 'library object.id'),
    resource,
    name: string(item.name, 'library object.name'),
    description: item.description === null ? null : string(item.description, 'library object.description'),
    lifecycleStatus: string(item.lifecycle_status, 'library object.lifecycle_status'),
    catalogStatus: string(item.catalog_status, 'library object.catalog_status'),
    catalogPriority: number(item.catalog_priority, 'library object.catalog_priority'),
    isDefault: boolean(item.is_default, 'library object.is_default'),
    sourceLabel: item.source_label === null ? null : string(item.source_label, 'library object.source_label'),
    releasedVersionId: item.released_version_id === null ? null : string(item.released_version_id, 'library object.released_version_id'),
  };
}

function parseTune(raw: unknown): TuneSummary {
  const item = object(raw, 'tune');
  return {
    id: string(item.id, 'tune.id'),
    name: string(item.name, 'tune.name'),
    notes: item.notes === null ? null : string(item.notes, 'tune.notes'),
    values: object(item.values, 'tune.values'),
    vehicleAssemblyId: string(item.vehicle_assembly_id, 'tune.vehicle_assembly_id'),
    cvtDesignId: string(item.cvt_design_id, 'tune.cvt_design_id'),
  };
}

function parseLoadCase(raw: unknown): LoadCaseSummary {
  const item = object(raw, 'load case');
  return {
    id: string(item.id, 'load case.id'),
    name: string(item.name, 'load case.name'),
    kind: string(item.kind, 'load case.kind'),
    visibility: string(item.visibility, 'load case.visibility'),
  };
}

function parseExecutionPreset(raw: unknown): ExecutionPresetSummary {
  const item = object(raw, 'execution preset');
  return {
    id: string(item.id, 'execution preset.id'),
    name: string(item.name, 'execution preset.name'),
    kind: string(item.kind, 'execution preset.kind'),
    isSystemDefault: boolean(item.is_system_default, 'execution preset.is_system_default'),
  };
}

function parseTuneParameter(raw: unknown): TuneParameter {
  const item = object(raw, 'tuning parameter');
  const group = string(item.group ?? 'primary', 'tuning parameter.group') as TuneParameterGroup;
  const kind = string(item.kind ?? 'number', 'tuning parameter.kind') as TuneParameterKind;
  if (!['primary', 'ramp', 'secondary', 'helix'].includes(group)) {
    throw new ApiClientError(`Unexpected tuning parameter group '${group}'.`);
  }
  if (!['number', 'ramp'].includes(kind)) {
    throw new ApiClientError(`Unexpected tuning parameter kind '${kind}'.`);
  }
  return {
    key: string(item.key, 'tuning parameter.key'),
    label: string(item.label, 'tuning parameter.label'),
    description: typeof item.description === 'string' ? item.description : '',
    group,
    kind,
    canonicalUnit: typeof item.unit === 'string' ? item.unit : '1',
    dimension: typeof item.dimension === 'string' ? item.dimension : undefined,
    minimum: optionalNumber(item.min, 'tuning parameter.min'),
    maximum: optionalNumber(item.max, 'tuning parameter.max'),
    defaultValue: item.default,
  };
}

function parseVehicleAssemblyVersion(raw: unknown): VehicleAssemblyVersionSummary {
  const item = object(raw, 'vehicle assembly version');
  const payload = object(item.assembly_payload ?? item.payload ?? {}, 'vehicle assembly version.assembly_payload');

  // Vehicle-assembly versions pin engine/CVT/output versions as first-class
  // columns. Older/forked payloads may also echo those IDs inside the payload,
  // so accept both shapes but prefer the canonical top-level API fields.
  const engineVersionId = item.engine_version_id ?? payload.engine_version_id;
  const cvtDesignVersionId = item.cvt_design_version_id ?? payload.cvt_design_version_id;
  const outputSystemVersionId = item.output_system_version_id ?? payload.output_system_version_id;

  return {
    id: string(item.id, 'vehicle assembly version.id'),
    objectId: string(item.object_id, 'vehicle assembly version.object_id'),
    assemblyPayload: {
      engineVersionId: string(engineVersionId, 'vehicle assembly version.engine_version_id'),
      cvtDesignVersionId: string(cvtDesignVersionId, 'vehicle assembly version.cvt_design_version_id'),
      outputSystemVersionId: string(outputSystemVersionId, 'vehicle assembly version.output_system_version_id'),
    },
  };
}

function parseCvtDesignVersion(raw: unknown): CvtDesignVersionSummary {
  const item = object(raw, 'CVT design version');
  const tuningSchema = object(item.tuning_schema ?? {}, 'CVT design version.tuning_schema');
  return {
    id: string(item.id, 'CVT design version.id'),
    objectId: string(item.object_id, 'CVT design version.object_id'),
    payload: object(item.cinder_assembly ?? item.payload, 'CVT design version.cinder_assembly'),
    tuningSchema: {
      parameters: array(tuningSchema.parameters ?? [], 'CVT tuning_schema.parameters').map(parseTuneParameter),
    },
  };
}

function pickPreferred<T extends { isDefault?: boolean; isSystemDefault?: boolean; name: string }>(items: T[]): T | null {
  return items.find((item) => item.isDefault === true || item.isSystemDefault === true)
    ?? items.find((item) => /flat launch|baseline|default/i.test(item.name))
    ?? items[0]
    ?? null;
}

function buildDefaultSelection(args: {
  accountId: string;
  createdByUserId: string | null;
  vehicleAssembly: LibraryObjectSummary;
  tune: TuneSummary | null;
  loadCase: LoadCaseSummary | null;
  executionPreset: ExecutionPresetSummary | null;
}): LibraryRunSelection {
  if (args.vehicleAssembly.releasedVersionId === null) {
    throw new ApiClientError(`Vehicle assembly '${args.vehicleAssembly.name}' has no released version.`);
  }
  return {
    accountId: args.accountId,
    createdByUserId: args.createdByUserId,
    vehicleAssemblyVersionId: args.vehicleAssembly.releasedVersionId,
    tuneId: args.tune?.id ?? null,
    loadCaseId: args.loadCase?.id ?? null,
    executionPresetId: args.executionPreset?.id ?? null,
  };
}

function parseValidation(raw: unknown): SimulationCaseValidation {
  const report = object(raw, 'validation');
  return {
    isValid: boolean(report.is_valid, 'validation.is_valid'),
    findings: array(report.findings, 'validation.findings').map((item) => {
      const finding = object(item, 'validation finding');
      const severity = string(finding.severity, 'finding.severity');
      if (severity !== 'error' && severity !== 'warning') throw new ApiClientError('Unexpected finding severity.');
      return {
        severity,
        code: string(finding.code, 'finding.code'),
        message: string(finding.message, 'finding.message'),
        location: string(finding.location, 'finding.location'),
        ...(typeof finding.document_path === 'string' ? { documentPath: finding.document_path } : {}),
      };
    }),
  };
}

function parseField(raw: unknown): ProjectedField {
  const value = object(raw, 'projected field');
  return {
    key: string(value.key, 'field.key'),
    label: string(value.label, 'field.label'),
    dimension: string(value.dimension, 'field.dimension'),
    canonicalUnit: string(value.canonical_unit ?? value.unit, 'field.canonical_unit'),
    values: value.values,
  };
}

function parseScalar(raw: unknown): ProjectedScalar {
  const value = object(raw, 'projected scalar');
  return {
    key: string(value.key, 'scalar.key'),
    label: string(value.label, 'scalar.label'),
    dimension: string(value.dimension, 'scalar.dimension'),
    canonicalUnit: string(value.canonical_unit ?? value.unit, 'scalar.canonical_unit'),
    value: numberOrNull(value.value, 'scalar.value'),
  };
}

function parseGeometryStudy(raw: unknown): GeometryStudyResult {
  const study = object(raw, 'study');
  if (study.kind !== 'geometry_design_response') throw new ApiClientError('Unexpected geometry study kind.');
  const summary = object(study.summary, 'study.summary');
  const path = object(study.path, 'study.path');
  const feasibility = object(study.feasibility, 'study.feasibility');
  return {
    kind: 'geometry_design_response',
    summary: {
      kind: 'geometry_summary',
      scalars: array(summary.scalars, 'study.summary.scalars').map(parseScalar),
    },
    path: {
      kind: 'geometry_path',
      shape: array(path.shape, 'study.path.shape').map((entry) => number(entry, 'study.path.shape value')),
      axisKeys: array(path.axis_keys, 'study.path.axis_keys').map((entry) => string(entry, 'study.path.axis key')),
      columns: array(path.columns, 'study.path.columns').map(parseField),
    },
    feasibility: {
      isFeasible: boolean(feasibility.is_feasible, 'study.feasibility.is_feasible'),
      findings: array(feasibility.findings, 'study.feasibility.findings').map((item) => {
        const finding = object(item, 'geometry finding');
        const severity = string(finding.severity, 'geometry finding.severity');
        if (severity !== 'error' && severity !== 'warning') throw new ApiClientError('Unexpected geometry finding severity.');
        return {
          severity,
          code: string(finding.code, 'geometry finding.code'),
          message: string(finding.message, 'geometry finding.message'),
          shiftM: numberOrNull(finding.shift_m, 'geometry finding.shift_m'),
        };
      }),
    },
  };
}

function parseEditorSchema(raw: unknown): EditorSchema {
  const document = object(raw, 'editor schema');
  const componentsDocument = object(document.component_catalog, 'editor schema.component_catalog');
  return {
    fields: array(document.fields, 'editor schema.fields').map((item) => {
      const field = object(item, 'editor field');
      const exposure = typeof field.exposure === 'string' ? field.exposure : 'design';
      if (!['design', 'scenario', 'advanced_execution'].includes(exposure)) {
        throw new ApiClientError(`Unexpected editable-field exposure '${exposure}'.`);
      }
      return {
        pathTemplate: string(field.path_template, 'editor field.path_template'),
        label: string(field.label, 'editor field.label'),
        description: typeof field.description === 'string' ? field.description : '',
        valueKind: string(field.value_kind, 'editor field.value_kind') as EditableValueKind,
        section: string(field.section, 'editor field.section'),
        dimension: typeof field.dimension === 'string' ? field.dimension : undefined,
        canonicalUnit: typeof field.canonical_unit === 'string' ? field.canonical_unit : undefined,
        required: boolean(field.required, 'editor field.required'),
        minimum: optionalNumber(field.minimum, 'editor field.minimum'),
        maximum: optionalNumber(field.maximum, 'editor field.maximum'),
        enumValues: Array.isArray(field.enum_values) ? field.enum_values.map((value) => string(value, 'editor field enum')) : [],
        when: typeof field.when === 'object' && field.when !== null && !Array.isArray(field.when)
          ? field.when as Record<string, string>
          : undefined,
        exposure: exposure as FieldExposure,
      };
    }),
    supportedDiscriminators: object(document.supported_discriminators, 'editor schema.supported_discriminators') as Record<string, string[]>,
    components: array(componentsDocument.components, 'component catalog.components').map((item) => {
      const component = object(item, 'component catalog entry');
      return {
        kind: string(component.kind, 'component.kind'),
        label: string(component.label, 'component.label'),
        description: string(component.description, 'component.description'),
        supportedMounts: array(component.supported_mounts, 'component.supported_mounts').map((value) => string(value, 'supported mount')),
        parameters: array(component.parameters, 'component.parameters').map((parameterRaw) => {
          const parameter = object(parameterRaw, 'component parameter');
          return {
            key: string(parameter.key, 'component parameter.key'),
            label: string(parameter.label, 'component parameter.label'),
            canonicalUnit: string(parameter.canonical_unit ?? parameter.unit, 'component parameter.canonical_unit'),
            ...(typeof parameter.dimension === 'string' ? { dimension: parameter.dimension } : {}),
            valueKind: (typeof parameter.value_kind === 'string' ? parameter.value_kind : 'number') as 'number' | 'object',
            required: boolean(parameter.required, 'component parameter.required'),
            description: string(parameter.description, 'component parameter.description'),
            minimum: optionalNumber(parameter.minimum, 'component parameter.minimum'),
            maximum: optionalNumber(parameter.maximum, 'component parameter.maximum'),
          };
        }),
      };
    }),
  };
}

function parseReportColumn(raw: unknown): ReportColumn {
  const column = object(raw, 'report column');
  return {
    key: string(column.key, 'report column.key'),
    label: string(column.label, 'report column.label'),
    description: typeof column.description === 'string' ? column.description : '',
    group: string(column.group, 'report column.group'),
    dimension: string(column.dimension, 'report column.dimension'),
    canonicalUnit: string(column.canonical_unit ?? column.unit, 'report column.canonical_unit'),
    values: array(column.values, 'report column.values').map((value) => numberOrNull(value, 'report column value')),
  };
}

function parseSimulationResult(raw: unknown): SimulationResult {
  const value = object(raw, 'simulation result');
  if (value.kind !== 'simulation_result') throw new ApiClientError('Unexpected result kind.');
  const table = object(value.report_table, 'simulation result.report_table');
  return {
    contractVersion: number(value.contract_version, 'simulation result.contract_version'),
    kind: 'simulation_result',
    conventions: object(value.conventions, 'simulation result.conventions'),
    metrics: object(value.metrics, 'simulation result.metrics'),
    summary: object(value.summary, 'simulation result.summary'),
    warnings: array(value.warnings, 'simulation result.warnings').map((warning) => string(warning, 'simulation warning')),
    reportTable: {
      axisKey: string(table.axis_key, 'report table.axis_key'),
      rowCount: number(table.row_count, 'report table.row_count'),
      columns: array(table.columns, 'report table.columns').map(parseReportColumn),
      segmentRanges: array(table.segment_ranges, 'report table.segment_ranges').map((item) => {
        const range = object(item, 'report segment range');
        return {
          segmentIndex: number(range.segment_index, 'report segment range.segment_index'),
          startIndex: number(range.start_index, 'report segment range.start_index'),
          endIndex: number(range.end_index, 'report segment range.end_index'),
          mode: object(range.mode, 'report segment range.mode') as Record<string, string | null>,
        };
      }),
      preservesDuplicateTransitionTimes: boolean(table.preserves_duplicate_transition_times, 'report table.preserves_duplicate_transition_times'),
    },
    transitions: array(value.transitions, 'simulation result.transitions').map((item) => {
      const transition = object(item, 'simulation transition');
      return {
        timeS: number(transition.time_s, 'simulation transition.time_s'),
        previousMode: object(transition.previous_mode, 'simulation transition.previous_mode') as Record<string, string | null>,
        firedEventNames: array(transition.fired_event_names, 'simulation transition.fired_event_names').map((name) => string(name, 'transition event name')),
        reason: string(transition.reason, 'simulation transition.reason'),
        terminates: boolean(transition.terminates, 'simulation transition.terminates'),
        metadata: transition.metadata,
        postTransitionState: object(transition.post_transition_state, 'simulation transition.post_transition_state') as Record<string, number>,
      };
    }),
  };
}


export async function listVehicleAssemblies(options: { publicOnly?: boolean } = {}): Promise<LibraryObjectSummary[]> {
  const params = new URLSearchParams();
  if (options.publicOnly ?? true) params.set('public_only', 'true');
  const data = await apiJson<{ items: unknown[] }>(`/api/v1/library/vehicle-assemblies?${params.toString()}`);
  return array(data.items, 'vehicle assemblies').map(parseLibraryObject)
    .filter((item) => item.releasedVersionId !== null);
}

export async function listTunes(options: { accountId?: string; vehicleAssemblyId?: string } = {}): Promise<TuneSummary[]> {
  const params = new URLSearchParams();
  if (options.accountId) params.set('account_id', options.accountId);
  if (options.vehicleAssemblyId) params.set('vehicle_assembly_id', options.vehicleAssemblyId);
  const query = params.toString();
  const data = await apiJson<{ items: unknown[] }>(`/api/v1/library/tunes${query ? `?${query}` : ''}`);
  return array(data.items, 'tunes').map(parseTune);
}

export async function listLoadCases(options: { accountId?: string } = {}): Promise<LoadCaseSummary[]> {
  const params = new URLSearchParams();
  if (options.accountId) params.set('account_id', options.accountId);
  const query = params.toString();
  const data = await apiJson<{ items: unknown[] }>(`/api/v1/library/load-cases${query ? `?${query}` : ''}`);
  return array(data.items, 'load cases').map(parseLoadCase);
}

export async function listExecutionPresets(options: { accountId?: string; includeSystem?: boolean } = {}): Promise<ExecutionPresetSummary[]> {
  const params = new URLSearchParams();
  if (options.accountId) params.set('account_id', options.accountId);
  if (options.includeSystem !== undefined) params.set('include_system', String(options.includeSystem));
  const query = params.toString();
  const data = await apiJson<{ items: unknown[] }>(`/api/v1/library/execution-presets${query ? `?${query}` : ''}`);
  return array(data.items, 'execution presets').map(parseExecutionPreset);
}

export async function getVehicleAssemblyVersion(versionId: string): Promise<VehicleAssemblyVersionSummary> {
  const data = await apiJson<unknown>(`/api/v1/library/vehicle-assemblies/versions/${encodeURIComponent(versionId)}`);
  return parseVehicleAssemblyVersion(data);
}

export async function getCvtDesignVersion(versionId: string): Promise<CvtDesignVersionSummary> {
  const data = await apiJson<unknown>(`/api/v1/library/cvt-designs/versions/${encodeURIComponent(versionId)}`);
  return parseCvtDesignVersion(data);
}

export async function updateTuneValues(tuneId: string, values: Record<string, unknown>): Promise<TuneSummary> {
  const data = await apiJson<unknown>(`/api/v1/library/tunes/${encodeURIComponent(tuneId)}`, {
    method: 'PATCH',
    body: JSON.stringify({ values }),
  });
  return parseTune(data);
}

export async function getDefaultRunSetup(): Promise<DefaultRunSetup> {
  const accountId = DEMO_ACCOUNT_ID;
  const createdByUserId = DEMO_USER_ID;
  const vehicleAssemblies = await listVehicleAssemblies({ publicOnly: true });
  const selectedVehicleAssembly = pickPreferred(vehicleAssemblies);
  if (selectedVehicleAssembly === null) {
    throw new ApiClientError('No released public vehicle assembly is available. Seed the database first.');
  }
  return buildRunSetupForVehicle(vehicleAssemblies, selectedVehicleAssembly.id, accountId, createdByUserId);
}

export async function buildRunSetupForVehicle(
  vehicleAssemblies: LibraryObjectSummary[],
  vehicleAssemblyId: string,
  accountId = DEMO_ACCOUNT_ID,
  createdByUserId: string | null = DEMO_USER_ID,
): Promise<DefaultRunSetup> {
  const selectedVehicleAssembly = vehicleAssemblies.find((assembly) => assembly.id === vehicleAssemblyId) ?? null;
  if (selectedVehicleAssembly === null) {
    throw new ApiClientError('Selected vehicle assembly is not available.');
  }
  if (selectedVehicleAssembly.releasedVersionId === null) {
    throw new ApiClientError(`Vehicle assembly '${selectedVehicleAssembly.name}' has no released version.`);
  }

  const vehicleAssemblyVersion = await getVehicleAssemblyVersion(selectedVehicleAssembly.releasedVersionId);
  const cvtDesignVersion = await getCvtDesignVersion(vehicleAssemblyVersion.assemblyPayload.cvtDesignVersionId);

  const [assemblyTunes, allTunes, loadCases, executionPresets] = await Promise.all([
    listTunes({ accountId, vehicleAssemblyId: selectedVehicleAssembly.id }),
    listTunes({ accountId }),
    listLoadCases({ accountId }),
    listExecutionPresets({ accountId, includeSystem: true }),
  ]);

  const tunes = assemblyTunes.length > 0 ? assemblyTunes : allTunes;
  const selectedTune = pickPreferred(tunes);
  const selectedLoadCase = pickPreferred(loadCases);
  const selectedExecutionPreset = pickPreferred(executionPresets);

  return {
    accountId,
    createdByUserId,
    vehicleAssemblies,
    selectedVehicleAssembly,
    tunes,
    selectedTune,
    loadCases,
    selectedLoadCase,
    executionPresets,
    selectedExecutionPreset,
    vehicleAssemblyVersion,
    cvtDesignVersion,
    tuningParameters: cvtDesignVersion.tuningSchema.parameters,
    selection: buildDefaultSelection({
      accountId,
      createdByUserId,
      vehicleAssembly: selectedVehicleAssembly,
      tune: selectedTune,
      loadCase: selectedLoadCase,
      executionPreset: selectedExecutionPreset,
    }),
  };
}

export function buildLibraryRunSelection(
  setup: DefaultRunSetup,
  overrides: {
    vehicleAssemblyId?: string;
    tuneId?: string | null;
    loadCaseId?: string | null;
    executionPresetId?: string | null;
  } = {},
): LibraryRunSelection {
  const vehicleAssembly = setup.vehicleAssemblies.find((item) => item.id === (overrides.vehicleAssemblyId ?? setup.selectedVehicleAssembly.id));
  if (vehicleAssembly === undefined) throw new ApiClientError('Selected vehicle assembly is not available.');
  const tune = overrides.tuneId === null ? null : setup.tunes.find((item) => item.id === (overrides.tuneId ?? setup.selectedTune?.id));
  const loadCase = overrides.loadCaseId === null ? null : setup.loadCases.find((item) => item.id === (overrides.loadCaseId ?? setup.selectedLoadCase?.id));
  const executionPreset = overrides.executionPresetId === null ? null : setup.executionPresets.find((item) => item.id === (overrides.executionPresetId ?? setup.selectedExecutionPreset?.id));
  return buildDefaultSelection({
    accountId: setup.accountId,
    createdByUserId: setup.createdByUserId,
    vehicleAssembly,
    tune: tune ?? null,
    loadCase: loadCase ?? null,
    executionPreset: executionPreset ?? null,
  });
}

export async function submitLibraryRun(selection: LibraryRunSelection): Promise<RunStatus> {
  const data = await apiJson<unknown>('/api/v1/runs/from-library', {
    method: 'POST',
    body: JSON.stringify({
      account_id: selection.accountId,
      created_by_user_id: selection.createdByUserId,
      vehicle_assembly_version_id: selection.vehicleAssemblyVersionId,
      tune_id: selection.tuneId,
      load_case_id: selection.loadCaseId,
      execution_preset_id: selection.executionPresetId,
      include_raw_trace: false,
      include_reported_segments: false,
    }),
  });
  return parseRunStatus(data);
}

export async function rerunSimulationRun(runId: string): Promise<RunStatus> {
  const data = await apiJson<unknown>(`/api/v1/runs/${encodeURIComponent(runId)}/rerun`, {
    method: 'POST',
    body: JSON.stringify({ created_by_user_id: DEMO_USER_ID }),
  });
  return parseRunStatus(data);
}

export async function getRunPreview(runId: string): Promise<RunPreview> {
  const data = await apiJson<unknown>(`/api/v1/runs/${encodeURIComponent(runId)}/preview`);
  const envelope = object(data, 'run preview response');
  const preview = object(envelope.preview, 'run preview');
  return {
    profileName: string(preview.profile_name, 'preview.profile_name'),
    profileVersion: number(preview.profile_version, 'preview.profile_version'),
    originalRowCount: number(preview.original_row_count, 'preview.original_row_count'),
    rowCount: number(preview.row_count, 'preview.row_count'),
    columns: object(preview.columns, 'preview.columns') as Record<string, Array<number | null>>,
  };
}

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

export async function getEditorSchema(): Promise<EditorSchema> {
  const data = dataOrThrow(await client.GET('/api/v1/metadata/editor-schema'));
  return parseEditorSchema(data.document);
}

export async function validateSimulationCase(document: SimulationCaseDocument): Promise<SimulationCaseValidation> {
  const data = dataOrThrow(await client.POST('/api/v1/simulation-cases/validate', {
    body: { simulation_case: wireDocument(document) },
  }));
  return parseValidation(data.validation);
}

export async function resolveSimulationCaseFromLibrarySelection(selection: LibraryRunSelection): Promise<SimulationCaseDocument> {
  const data = await apiJson<unknown>('/api/v1/simulation-cases/resolve-from-library', {
    method: 'POST',
    body: JSON.stringify({
      vehicle_assembly_version_id: selection.vehicleAssemblyVersionId,
      tune_id: selection.tuneId,
      load_case_id: selection.loadCaseId,
      execution_preset_id: selection.executionPresetId,
    }),
  });
  const envelope = object(data, 'resolved simulation-case response');
  return object(envelope.simulation_case, 'resolved simulation_case') as unknown as SimulationCaseDocument;
}

export async function runEndpointRadiiGeometryStudy(request: GeometryEndpointRadiiRequest): Promise<GeometryStudyResult> {
  const data = dataOrThrow(await client.POST('/api/v1/studies/geometry/endpoint-radii', { body: request }));
  return parseGeometryStudy(data.study);
}

export async function submitSimulationRun(document: SimulationCaseDocument): Promise<RunStatus> {
  const data = dataOrThrow(await client.POST('/api/v1/runs', {
    body: {
      simulation_case: wireDocument(document),
      include_raw_trace: false,
      include_reported_segments: false,
    },
  }));
  return parseRunStatus(data);
}

export async function getSimulationRun(runId: string): Promise<RunStatus> {
  return parseRunStatus(dataOrThrow(await client.GET('/api/v1/runs/{run_id}', {
    params: { path: { run_id: runId } },
  })));
}

export async function getSimulationResult(runId: string): Promise<CompletedSimulationRun> {
  const data = dataOrThrow(await client.GET('/api/v1/runs/{run_id}/result', {
    params: { path: { run_id: runId } },
  }));
  return {
    run: parseRunStatus(data.run),
    inputDocumentSnapshot: data.input_document_snapshot as unknown as SimulationCaseDocument,
    result: parseSimulationResult(data.result),
  };
}

function sleep(milliseconds: number, signal?: AbortSignal): Promise<void> {
  return new Promise((resolve, reject) => {
    const timeout = window.setTimeout(resolve, milliseconds);
    signal?.addEventListener('abort', () => {
      window.clearTimeout(timeout);
      reject(new DOMException('The simulation wait was cancelled.', 'AbortError'));
    }, { once: true });
  });
}

/** Poll only honest run lifecycle states; the backend intentionally has no percentage estimate. */
export async function waitForSimulationRun(
  runId: string,
  options: { pollIntervalMs?: number; signal?: AbortSignal } = {},
): Promise<RunStatus> {
  const pollIntervalMs = options.pollIntervalMs ?? 350;
  while (true) {
    const run = await getSimulationRun(runId);
    if (run.status === 'completed') return run;
    if (run.status === 'failed' || run.status === 'timed_out') throw new SimulationRunError(run);
    await sleep(pollIntervalMs, options.signal);
  }
}
