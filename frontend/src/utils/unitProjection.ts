import { displayScale, projectedDisplayValue, type UnitPreferences, type UnitScope } from './units';

export interface ProjectedColumn {
  dimension: string;
  canonical_unit: string;
  values: readonly unknown[];
}
/** Projection never changes the retained report arrays or fills unavailable samples. */
export function displayColumn(column: ProjectedColumn, preferences: UnitPreferences, scope: UnitScope = 'output') {
  return column.values.map(value => typeof value === 'number' && Number.isFinite(value)
    ? projectedDisplayValue(value, column.dimension, column.canonical_unit, scope, preferences) : null);
}

/** Re-express absolute zoom bounds; percentage ranges are unitless and stay untouched. */
export function convertZoomUnits<T>(zoom: T, fromUnit: string, toUnit: string): T {
  if (!zoom || fromUnit === toUnit || !Array.isArray(zoom)) return zoom;
  const factor = displayScale(toUnit) / displayScale(fromUnit);
  return zoom.map((range, i) => {
    if (i !== 1 || typeof range !== 'object' || range === null) return range;
    return { ...range,
      ...(typeof range.startValue === 'number' ? { startValue: range.startValue * factor } : {}),
      ...(typeof range.endValue === 'number' ? { endValue: range.endValue * factor } : {}),
    };
  }) as T;
}
