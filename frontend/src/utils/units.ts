/**
 * Display-only conversion. CINDER documents and results remain canonical SI;
 * this module knows units/dimensions, never CVT paths or equations.
 */
export type QuantityDimension =
  | 'length'
  | 'area'
  | 'volume'
  | 'angle'
  | 'angular_speed'
  | 'angular_acceleration'
  | 'speed'
  | 'acceleration'
  | 'force'
  | 'torque'
  | 'mass'
  | 'density'
  | 'inertia'
  | 'stiffness'
  | 'time'
  | 'power'
  | 'length_rate'
  | 'ratio_rate'
  | 'dimensionless';

export type DisplayUnit =
  | 'm' | 'mm' | 'm²' | 'm³' | 'rad' | 'deg' | 'rad/s' | 'rpm' | 'rad/s²'
  | 'm/s' | 'km/h' | 'm/s²' | 'N' | 'N·m' | 'kg' | 'kg/m³'
  | 'kg·m²' | 'N/m' | 'N·m/rad' | 's' | 'W' | 'kW' | 'mm/s' | '1/s' | '';

const DEFAULT_UNITS: Readonly<Record<QuantityDimension, DisplayUnit>> = {
  length: 'mm',
  area: 'm²',
  volume: 'm³',
  angle: 'deg',
  angular_speed: 'rpm',
  angular_acceleration: 'rad/s²',
  speed: 'km/h',
  acceleration: 'm/s²',
  force: 'N',
  torque: 'N·m',
  mass: 'kg',
  density: 'kg/m³',
  inertia: 'kg·m²',
  stiffness: 'N/m',
  time: 's',
  power: 'kW',
  length_rate: 'mm/s',
  ratio_rate: '1/s',
  dimensionless: '',
};

const SI_TO_DISPLAY: Readonly<Record<DisplayUnit, number>> = {
  m: 1,
  mm: 1000,
  'm²': 1,
  'm³': 1,
  rad: 1,
  deg: 180 / Math.PI,
  'rad/s': 1,
  rpm: 30 / Math.PI,
  'rad/s²': 1,
  'm/s': 1,
  'km/h': 3.6,
  'm/s²': 1,
  N: 1,
  'N·m': 1,
  kg: 1,
  'kg/m³': 1,
  'kg·m²': 1,
  'N/m': 1,
  'N·m/rad': 1,
  s: 1,
  W: 1,
  kW: 0.001,
  'mm/s': 1000,
  '1/s': 1,
  '': 1,
};

export function isQuantityDimension(value: string | undefined): value is QuantityDimension {
  return value !== undefined && Object.prototype.hasOwnProperty.call(DEFAULT_UNITS, value);
}

export function defaultDisplayUnit(dimension: QuantityDimension): DisplayUnit {
  return DEFAULT_UNITS[dimension];
}

export function siToDisplay(valueSi: number, unit: DisplayUnit): number {
  return valueSi * SI_TO_DISPLAY[unit];
}

export function displayToSi(value: number, unit: DisplayUnit): number {
  return value / SI_TO_DISPLAY[unit];
}

export function formatQuantity(
  valueSi: number,
  dimension: QuantityDimension,
  displayUnit = defaultDisplayUnit(dimension),
  maximumFractionDigits = 4,
): string {
  const displayValue = siToDisplay(valueSi, displayUnit);
  const text = new Intl.NumberFormat(undefined, { maximumFractionDigits }).format(displayValue);
  return displayUnit ? `${text} ${displayUnit}` : text;
}

export function formatProjectedQuantity(
  valueSi: number,
  dimension: string,
  canonicalUnit: string,
  maximumFractionDigits = 4,
): string {
  if (isQuantityDimension(dimension)) {
    return formatQuantity(valueSi, dimension, undefined, maximumFractionDigits);
  }
  const text = new Intl.NumberFormat(undefined, { maximumFractionDigits }).format(valueSi);
  return canonicalUnit ? `${text} ${canonicalUnit}` : text;
}

/** Used only when the catalog gives a unit but no explicit CINDER dimension. */
export function dimensionForUnit(unit: string): QuantityDimension | undefined {
  const normalized = unit.replace(/\s/g, '').replace('Nm', 'N·m');
  const map: Record<string, QuantityDimension> = {
    m: 'length',
    rad: 'angle',
    'rad/s': 'angular_speed',
    'rad/s²': 'angular_acceleration',
    'm/s': 'speed',
    'm/s²': 'acceleration',
    N: 'force',
    'N·m': 'torque',
    kg: 'mass',
    'kg/m³': 'density',
    'kg·m²': 'inertia',
    'N/m': 'stiffness',
    s: 'time',
    '1': 'dimensionless',
  };
  return map[normalized];
}

export function displayUnitForCanonical(canonicalUnit: string, dimension?: string): DisplayUnit {
  if (isQuantityDimension(dimension)) return defaultDisplayUnit(dimension);
  const known = canonicalUnit as DisplayUnit;
  return Object.prototype.hasOwnProperty.call(SI_TO_DISPLAY, known) ? known : '';
}
