/**
 * Display-only conversion. CINDER documents and results remain canonical SI;
 * this module knows units/dimensions and personal display preferences only.
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
  | 'm' | 'cm' | 'mm' | 'in' | 'ft'
  | 'm²' | 'm³'
  | 'rad' | 'deg' | 'rad/s' | 'rpm' | 'rad/s²'
  | 'm/s' | 'km/h' | 'mph' | 'm/s²'
  | 'N' | 'lbf' | 'N·m' | 'lb·ft'
  | 'kg' | 'g' | 'oz' | 'lb' | 'kg/m³'
  | 'kg·m²' | 'N/m' | 'N/mm' | 'N·m/rad'
  | 's' | 'W' | 'kW' | 'mm/s' | '1/s' | '%' | '';

export type UnitPreset = 'recommended' | 'metric' | 'si' | 'imperial';
export type UnitScope = 'default' | 'hardware' | 'vehicle' | 'course' | 'output';

export interface UnitPreferences {
  preset: UnitPreset;
  hardware_length: 'in' | 'mm' | 'm';
  component_mass: 'g' | 'kg' | 'oz';
  vehicle_length: 'm' | 'ft' | 'in';
  vehicle_mass: 'kg' | 'lb';
  course_length: 'm' | 'ft';
  speed: 'km/h' | 'm/s' | 'mph';
  output_length: 'm' | 'ft' | 'mm' | 'in';
  output_speed: 'km/h' | 'm/s' | 'mph';
}

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

/** Multipliers from canonical SI to the named display unit. */
const SI_TO_DISPLAY: Readonly<Record<DisplayUnit, number>> = {
  m: 1,
  cm: 100,
  mm: 1000,
  in: 39.37007874015748,
  ft: 3.280839895013123,
  'm²': 1,
  'm³': 1,
  rad: 1,
  deg: 180 / Math.PI,
  'rad/s': 1,
  rpm: 30 / Math.PI,
  'rad/s²': 1,
  'm/s': 1,
  'km/h': 3.6,
  mph: 2.2369362920544,
  'm/s²': 1,
  N: 1,
  lbf: 0.22480894387096,
  'N·m': 1,
  'lb·ft': 0.73756214927727,
  kg: 1,
  g: 1000,
  oz: 35.27396194958,
  lb: 2.2046226218488,
  'kg/m³': 1,
  'kg·m²': 1,
  'N/m': 1,
  'N/mm': 0.001,
  'N·m/rad': 1,
  s: 1,
  W: 1,
  kW: 0.001,
  'mm/s': 1000,
  '1/s': 1,
  '%': 1,
  '': 1,
};

const UNIT_DIMENSION: Readonly<Partial<Record<DisplayUnit, QuantityDimension>>> = {
  m: 'length', cm: 'length', mm: 'length', in: 'length', ft: 'length',
  'm²': 'area', 'm³': 'volume',
  rad: 'angle', deg: 'angle',
  'rad/s': 'angular_speed', rpm: 'angular_speed', 'rad/s²': 'angular_acceleration',
  'm/s': 'speed', 'km/h': 'speed', mph: 'speed', 'm/s²': 'acceleration',
  N: 'force', lbf: 'force', 'N·m': 'torque', 'lb·ft': 'torque',
  kg: 'mass', g: 'mass', oz: 'mass', lb: 'mass', 'kg/m³': 'density',
  'kg·m²': 'inertia', 'N/m': 'stiffness', 'N/mm': 'stiffness', 'N·m/rad': 'stiffness',
  s: 'time', W: 'power', kW: 'power', 'mm/s': 'length_rate', '1/s': 'ratio_rate',
  '%': 'dimensionless', '': 'dimensionless',
};

const UNIT_ALIASES: Readonly<Record<string, DisplayUnit>> = {
  m: 'm', cm: 'cm', mm: 'mm', in: 'in', ft: 'ft', rad: 'rad', deg: 'deg',
  rpm: 'rpm', 'm/s': 'm/s', 'km/h': 'km/h', mph: 'mph', kg: 'kg', g: 'g',
  oz: 'oz', lb: 'lb', n: 'N', lbf: 'lbf', s: 's', w: 'W', kw: 'kW', '%': '%',
  metre: 'm', metres: 'm', meter: 'm', meters: 'm',
  centimetre: 'cm', centimetres: 'cm', centimeter: 'cm', centimeters: 'cm',
  millimetre: 'mm', millimetres: 'mm', millimeter: 'mm', millimeters: 'mm',
  inch: 'in', inches: 'in',
  foot: 'ft', feet: 'ft',
  degree: 'deg', degrees: 'deg', '°': 'deg',
  'rad/sec': 'rad/s', 'rads/s': 'rad/s',
  'kmh': 'km/h', 'kph': 'km/h',
  'mps': 'm/s',
  'lbft': 'lb·ft', 'lb-ft': 'lb·ft', 'ftlb': 'lb·ft', 'ft-lb': 'lb·ft',
  'nm': 'N·m', 'n-m': 'N·m',
  'lbs': 'lb', 'pound': 'lb', 'pounds': 'lb',
  'ounce': 'oz', 'ounces': 'oz',
};

export const RECOMMENDED_UNIT_PREFERENCES: UnitPreferences = {
  preset: 'recommended',
  hardware_length: 'in',
  component_mass: 'g',
  vehicle_length: 'm',
  vehicle_mass: 'kg',
  course_length: 'm',
  speed: 'km/h',
  output_length: 'm',
  output_speed: 'km/h',
};

export function presetUnitPreferences(preset: UnitPreset): UnitPreferences {
  if (preset === 'metric') return {
    ...RECOMMENDED_UNIT_PREFERENCES,
    preset,
    hardware_length: 'mm',
  };
  if (preset === 'si') return {
    ...RECOMMENDED_UNIT_PREFERENCES,
    preset,
    hardware_length: 'm',
    component_mass: 'kg',
    speed: 'm/s',
    output_speed: 'm/s',
  };
  if (preset === 'imperial') return {
    ...RECOMMENDED_UNIT_PREFERENCES,
    preset,
    hardware_length: 'in',
    component_mass: 'oz',
    vehicle_length: 'ft',
    vehicle_mass: 'lb',
    course_length: 'ft',
    speed: 'mph',
    output_length: 'ft',
    output_speed: 'mph',
  };
  return { ...RECOMMENDED_UNIT_PREFERENCES };
}

export function normalizeUnitPreferences(
  value?: Partial<UnitPreferences> | null,
): UnitPreferences {
  const preset: UnitPreset = value?.preset ?? 'recommended';
  return { ...presetUnitPreferences(preset), ...value, preset };
}

export function preferredDisplayUnit(
  dimension: QuantityDimension,
  scope: UnitScope,
  preferences: UnitPreferences,
  fallback = defaultDisplayUnit(dimension),
): DisplayUnit {
  if (scope === 'hardware') {
    if (dimension === 'length') return preferences.hardware_length;
    if (dimension === 'mass') return preferences.component_mass;
  }
  if (scope === 'vehicle') {
    if (dimension === 'length') return preferences.vehicle_length;
    if (dimension === 'mass') return preferences.vehicle_mass;
    if (dimension === 'speed') return preferences.speed;
  }
  if (scope === 'course') {
    if (dimension === 'length') return preferences.course_length;
    if (dimension === 'speed') return preferences.speed;
  }
  if (scope === 'output') {
    if (dimension === 'length') return preferences.output_length;
    if (dimension === 'speed') return preferences.output_speed;
  }
  return fallback;
}

export function isQuantityDimension(value: string | undefined): value is QuantityDimension {
  return value !== undefined && Object.prototype.hasOwnProperty.call(DEFAULT_UNITS, value);
}

export function defaultDisplayUnit(dimension: QuantityDimension): DisplayUnit {
  return DEFAULT_UNITS[dimension];
}

export function siToDisplay(valueSi: number, unit: DisplayUnit): number {
  return valueSi * SI_TO_DISPLAY[unit];
}

/** Scale for ordinary quantity controls; backend hints can provide other units. */
export function displayScale(unit: string): number {
  return Object.prototype.hasOwnProperty.call(SI_TO_DISPLAY, unit)
    ? SI_TO_DISPLAY[unit as DisplayUnit]
    : 1;
}

export function displayToSi(value: number, unit: DisplayUnit): number {
  return value / SI_TO_DISPLAY[unit];
}

function normalizedUnitToken(raw: string): DisplayUnit | null {
  const compact = raw.trim().replace(/\s+/g, '').replace('⋅', '·');
  if (Object.prototype.hasOwnProperty.call(SI_TO_DISPLAY, compact))
    return compact as DisplayUnit;
  const lower = compact.toLowerCase();
  return UNIT_ALIASES[lower] ?? null;
}

function parseNumericExpression(raw: string): number | null {
  const text = raw.trim();
  const mixed = text.match(/^([+-]?\d+)\s*(?:-|\s)\s*(\d+)\s*\/\s*(\d+)$/);
  if (mixed) {
    const whole = Number(mixed[1]);
    const numerator = Number(mixed[2]);
    const denominator = Number(mixed[3]);
    if (!denominator) return null;
    const sign = whole < 0 || Object.is(whole, -0) ? -1 : 1;
    return whole + sign * numerator / denominator;
  }
  const fraction = text.match(/^([+-]?)\s*(\d+)\s*\/\s*(\d+)$/);
  if (fraction) {
    const denominator = Number(fraction[3]);
    if (!denominator) return null;
    const sign = fraction[1] === '-' ? -1 : 1;
    return sign * Number(fraction[2]) / denominator;
  }
  const value = Number(text);
  return Number.isFinite(value) ? value : null;
}

export type QuantityParseResult =
  | { valueSi: number; unit: DisplayUnit; error?: undefined }
  | { valueSi?: undefined; unit?: undefined; error: string };

/**
 * Parse a quantity without mutating the stored document. A missing unit uses
 * the field's current display unit; an explicit unit must match the dimension.
 */
export function parseQuantityText(
  raw: string,
  dimension: QuantityDimension,
  fallbackUnit: DisplayUnit,
): QuantityParseResult {
  let text = raw.trim();
  if (!text) return { error: 'Enter a value.' };
  text = text.replace(/″|"/g, ' in').replace(/′/g, ' ft');
  const numberAndUnit = text.match(
    /^([+-]?(?:\d+\s*(?:-\s*|\s+)\d+\s*\/\s*\d+|\d+\s*\/\s*\d+|(?:\d+(?:\.\d*)?|\.\d+)))\s*(.*)$/,
  );
  if (!numberAndUnit) return { error: 'Enter a number, optionally followed by a unit.' };
  const number = parseNumericExpression(numberAndUnit[1]);
  if (number === null) return { error: 'Enter a valid number or simple fraction.' };
  const unitText = numberAndUnit[2].trim();
  const unit = unitText ? normalizedUnitToken(unitText) : fallbackUnit;
  if (unit === null) return { error: `Unit “${unitText}” is not supported.` };
  if (UNIT_DIMENSION[unit] !== dimension) {
    return { error: `Use a ${dimension.replace(/_/g, ' ')} unit for this field.` };
  }
  return { valueSi: displayToSi(number, unit), unit };
}

export function formatEditableQuantity(valueSi: number, unit: DisplayUnit): string {
  const value = Number(siToDisplay(valueSi, unit).toPrecision(12));
  return unit ? `${value} ${unit}` : String(value);
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
  const normalized = normalizedUnitToken(unit);
  return normalized === null ? undefined : UNIT_DIMENSION[normalized];
}

export function displayUnitForCanonical(canonicalUnit: string, dimension?: string): DisplayUnit {
  const known = normalizedUnitToken(canonicalUnit);
  if (known !== null && (!isQuantityDimension(dimension) || UNIT_DIMENSION[known] === dimension))
    return known;
  if (isQuantityDimension(dimension)) return defaultDisplayUnit(dimension);
  return '';
}
