/**
 * Display-only SI conversion. This module does not know CVT field names;
 * CINDER owns those meanings and emits the dimension metadata.
 */
export type QuantityDimension =
  | 'length'
  | 'angle'
  | 'angular_speed'
  | 'speed'
  | 'force'
  | 'torque'
  | 'mass'
  | 'time'
  | 'dimensionless';

export type DisplayUnit =
  | 'm' | 'mm' | 'rad' | 'deg' | 'rad/s' | 'rpm' | 'm/s' | 'km/h'
  | 'N' | 'N·m' | 'kg' | 's' | '';

const DEFAULT_UNITS: Readonly<Record<QuantityDimension, DisplayUnit>> = {
  length: 'mm',
  angle: 'deg',
  angular_speed: 'rpm',
  speed: 'km/h',
  force: 'N',
  torque: 'N·m',
  mass: 'kg',
  time: 's',
  dimensionless: '',
};

const SI_TO_DISPLAY: Readonly<Record<DisplayUnit, number>> = {
  m: 1,
  mm: 1000,
  rad: 1,
  deg: 180 / Math.PI,
  'rad/s': 1,
  rpm: 30 / Math.PI,
  'm/s': 1,
  'km/h': 3.6,
  N: 1,
  'N·m': 1,
  kg: 1,
  s: 1,
  '': 1,
};

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
  const displayed = siToDisplay(valueSi, displayUnit);
  const text = new Intl.NumberFormat(undefined, { maximumFractionDigits }).format(displayed);
  return displayUnit ? `${text} ${displayUnit}` : text;
}

/** Format any projected CINDER dimension without inventing a conversion rule. */
export function formatProjectedQuantity(
  valueSi: number,
  dimension: string,
  canonicalUnit: string,
  maximumFractionDigits = 4,
): string {
  if (Object.prototype.hasOwnProperty.call(DEFAULT_UNITS, dimension)) {
    return formatQuantity(valueSi, dimension as QuantityDimension, undefined, maximumFractionDigits);
  }
  const text = new Intl.NumberFormat(undefined, { maximumFractionDigits }).format(valueSi);
  return canonicalUnit ? `${text} ${canonicalUnit}` : text;
}
