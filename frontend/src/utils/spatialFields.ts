import type { ReportTable, SimulationResult } from '@api/client';

export type FieldExpression = SimulationResult['domains'][number]['regions'][number]['length'];
export type SpatialDomainDefinition = SimulationResult['domains'][number];
export type SpatialFieldDefinition = SimulationResult['fields'][number];

export interface SpatialDomainSample {
  coordinate: number[];
  localCoordinate: number[];
  regionKeys: string[];
  position: Array<[number, number]>;
}

export interface SpatialFieldSample {
  fieldKey: string;
  unit: string;
  domain: SpatialDomainSample;
  values: number[];
}

export interface NumericRange {
  minimum: number;
  maximum: number;
}

type ExpressionValue = number | boolean;
type SignalFrame = ReadonlyMap<string, number>;

function numeric(value: ExpressionValue): number {
  return typeof value === 'boolean' ? (value ? 1 : 0) : value;
}

function condition(value: ExpressionValue): boolean {
  return typeof value === 'boolean' ? value : Number.isFinite(value) && value !== 0;
}

/** Evaluate CINDER's portable scalar field-expression language at one coordinate. */
export function evaluateFieldExpression(
  expression: FieldExpression,
  coordinate: number,
  signals: SignalFrame,
): ExpressionValue {
  switch (expression.op) {
    case 'literal':
      return expression.value;
    case 'coordinate':
      return coordinate;
    case 'signal':
      return signals.get(expression.key) ?? Number.NaN;
    case 'where': {
      // Deliberately short-circuit. This keeps inactive singular branches such
      // as the z=0 wrap expression from evaluating 0/0 in scalar playback.
      const selected = condition(evaluateFieldExpression(expression.args[0], coordinate, signals))
        ? expression.args[1]
        : expression.args[2];
      return evaluateFieldExpression(selected, coordinate, signals);
    }
    case 'neg':
      return -numeric(evaluateFieldExpression(expression.args[0], coordinate, signals));
    case 'abs':
      return Math.abs(numeric(evaluateFieldExpression(expression.args[0], coordinate, signals)));
    case 'exp':
      return Math.exp(numeric(evaluateFieldExpression(expression.args[0], coordinate, signals)));
    case 'expm1':
      return Math.expm1(numeric(evaluateFieldExpression(expression.args[0], coordinate, signals)));
    case 'sin':
      return Math.sin(numeric(evaluateFieldExpression(expression.args[0], coordinate, signals)));
    case 'cos':
      return Math.cos(numeric(evaluateFieldExpression(expression.args[0], coordinate, signals)));
    case 'sqrt':
      return Math.sqrt(numeric(evaluateFieldExpression(expression.args[0], coordinate, signals)));
    case 'add':
      return numeric(evaluateFieldExpression(expression.args[0], coordinate, signals))
        + numeric(evaluateFieldExpression(expression.args[1], coordinate, signals));
    case 'sub':
      return numeric(evaluateFieldExpression(expression.args[0], coordinate, signals))
        - numeric(evaluateFieldExpression(expression.args[1], coordinate, signals));
    case 'mul':
      return numeric(evaluateFieldExpression(expression.args[0], coordinate, signals))
        * numeric(evaluateFieldExpression(expression.args[1], coordinate, signals));
    case 'div':
      return numeric(evaluateFieldExpression(expression.args[0], coordinate, signals))
        / numeric(evaluateFieldExpression(expression.args[1], coordinate, signals));
    case 'lt':
      return numeric(evaluateFieldExpression(expression.args[0], coordinate, signals))
        < numeric(evaluateFieldExpression(expression.args[1], coordinate, signals));
    default: {
      const exhaustive: never = expression;
      throw new Error(`Unsupported CINDER field-expression operator: ${String((exhaustive as { op?: unknown }).op)}`);
    }
  }
}

export function findSpatialDomain(
  result: SimulationResult,
  key: string,
): SpatialDomainDefinition | undefined {
  return result.domains.find((domain) => domain.key === key);
}

export function findSpatialField(
  result: SimulationResult,
  key: string,
): SpatialFieldDefinition | undefined {
  return result.fields.find((field) => field.key === key);
}

function signalFrame(table: ReportTable, frameIndex: number): SignalFrame {
  const signals = new Map<string, number>();
  table.columns.forEach((column) => {
    const value = column.values[frameIndex];
    signals.set(column.key, typeof value === 'number' && Number.isFinite(value) ? value : Number.NaN);
  });
  return signals;
}

/**
 * Sample a CINDER spatial domain exactly like BoundSpatialDomain.sample():
 * lengths at u=0, uniform physical-distance spacing, and no duplicate endpoint
 * for periodic domains.
 */
export function sampleSpatialDomain(
  definition: SpatialDomainDefinition,
  table: ReportTable,
  frameIndex: number,
  count = 200,
): SpatialDomainSample {
  if (!Number.isInteger(count) || count < 4) {
    throw new Error('Spatial sample count must be an integer of at least 4.');
  }
  if (frameIndex < 0 || frameIndex >= table.row_count) {
    throw new Error(`Spatial frame index ${frameIndex} is outside [0, ${table.row_count}).`);
  }

  const signals = signalFrame(table, frameIndex);
  const lengths = definition.regions.map((region) => numeric(
    evaluateFieldExpression(region.length, 0, signals),
  ));
  if (lengths.some((length) => !Number.isFinite(length) || length <= 0)) {
    throw new Error(`Spatial domain '${definition.key}' contains a non-positive or non-finite region length.`);
  }

  const cumulative = [0];
  lengths.forEach((length) => cumulative.push(cumulative[cumulative.length - 1] + length));
  const totalLength = cumulative[cumulative.length - 1];
  const denominator = definition.periodic ? count : count - 1;

  const coordinate: number[] = [];
  const localCoordinate: number[] = [];
  const regionKeys: string[] = [];
  const position: Array<[number, number]> = [];

  for (let sampleIndex = 0; sampleIndex < count; sampleIndex += 1) {
    const distance = totalLength * sampleIndex / denominator;
    let regionIndex = 0;
    while (
      regionIndex < definition.regions.length - 1
      && distance >= cumulative[regionIndex + 1]
    ) {
      regionIndex += 1;
    }

    const region = definition.regions[regionIndex];
    const unclampedLocal = (distance - cumulative[regionIndex]) / lengths[regionIndex];
    const local = Math.min(1, Math.max(0, unclampedLocal));
    const x = numeric(evaluateFieldExpression(region.position.x, local, signals));
    const y = numeric(evaluateFieldExpression(region.position.y, local, signals));
    if (!Number.isFinite(x) || !Number.isFinite(y)) {
      throw new Error(`Spatial domain '${definition.key}' produced a non-finite position in region '${region.key}'.`);
    }

    coordinate.push(distance / totalLength);
    localCoordinate.push(local);
    regionKeys.push(region.key);
    position.push([x, y]);
  }

  return { coordinate, localCoordinate, regionKeys, position };
}

/** Evaluate one field lazily on an already-sampled domain at the same frame. */
export function sampleSpatialField(
  definition: SpatialFieldDefinition,
  domain: SpatialDomainSample,
  table: ReportTable,
  frameIndex: number,
): SpatialFieldSample {
  const signals = signalFrame(table, frameIndex);
  const expressions = new Map(definition.regions.map((region) => [region.key, region.expression]));
  const values = domain.regionKeys.map((regionKey, index) => {
    const expression = expressions.get(regionKey);
    if (expression === undefined) return Number.NaN;
    const value = numeric(evaluateFieldExpression(expression, domain.localCoordinate[index], signals));
    return Number.isFinite(value) ? value : Number.NaN;
  });
  return {
    fieldKey: definition.key,
    unit: definition.canonical_unit,
    domain,
    values,
  };
}

/** Scan selected ordinary report columns once to obtain a fixed whole-run scale. */
export function reportSignalRange(table: ReportTable, keys: readonly string[]): NumericRange | null {
  const selected = new Set(keys);
  let minimum = Number.POSITIVE_INFINITY;
  let maximum = Number.NEGATIVE_INFINITY;

  table.columns.forEach((column) => {
    if (!selected.has(column.key)) return;
    column.values.forEach((value) => {
      if (typeof value !== 'number' || !Number.isFinite(value)) return;
      minimum = Math.min(minimum, value);
      maximum = Math.max(maximum, value);
    });
  });

  return Number.isFinite(minimum) && Number.isFinite(maximum)
    ? { minimum, maximum }
    : null;
}
