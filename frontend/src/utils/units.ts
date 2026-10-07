/** Display and parsing only. CINDER documents, snapshots and exports remain SI. */
/** Exact SI conversion factors where defined (international inch/foot/pound).
 * lbm denotes mass; lbf denotes force. No document values live in this module.
 */
const INCH = 0.0254;
const FOOT = 0.3048;
const POUND = 0.45359237;
const LBF = POUND * 9.80665;
const DEGREE = Math.PI / 180;

export const UNIT_CATALOG = {
  m: ['length', 1], cm: ['length', 0.01], mm: ['length', 0.001],
  in: ['length', INCH], ft: ['length', FOOT],
  'm²': ['area', 1], 'cm²': ['area', 1e-4], 'mm²': ['area', 1e-6],
  'in²': ['area', INCH ** 2], 'ft²': ['area', FOOT ** 2],
  'm³': ['volume', 1], 'cm³': ['volume', 1e-6], 'mm³': ['volume', 1e-9],
  'in³': ['volume', INCH ** 3], 'ft³': ['volume', FOOT ** 3],
  rad: ['angle', 1], deg: ['angle', DEGREE],
  'rad/s': ['angular_speed', 1], rpm: ['angular_speed', Math.PI / 30],
  'rad/s²': ['angular_acceleration', 1], 'rpm/s': ['angular_acceleration', Math.PI / 30],
  'm/s': ['speed', 1], 'mm/s': ['speed', 0.001], 'in/s': ['speed', INCH],
  'ft/s': ['speed', FOOT], 'km/h': ['speed', 1 / 3.6], mph: ['speed', 1609.344 / 3600],
  'm/s²': ['acceleration', 1], 'mm/s²': ['acceleration', 0.001],
  'in/s²': ['acceleration', INCH], 'ft/s²': ['acceleration', FOOT],
  N: ['force', 1], lbf: ['force', LBF],
  'N·m': ['torque', 1], 'N·mm': ['torque', 0.001],
  'lbf·in': ['torque', LBF * INCH], 'lbf·ft': ['torque', LBF * FOOT],
  'lb·ft': ['torque', LBF * FOOT], // Retain the old input/import spelling.
  kg: ['mass', 1], g: ['mass', 0.001], oz: ['mass', POUND / 16], lb: ['mass', POUND],
  'kg/m³': ['density', 1], 'g/cm³': ['density', 1000],
  'lbm/ft³': ['density', POUND / FOOT ** 3],
  'kg·m²': ['inertia', 1], 'kg·mm²': ['inertia', 1e-6],
  'g·mm²': ['inertia', 1e-9], 'lbm·in²': ['inertia', POUND * INCH ** 2],
  'kg·m': ['first_moment', 1], 'g·mm': ['first_moment', 1e-6],
  'lbm·in': ['first_moment', POUND * INCH],
  '1/m': ['inverse_length', 1], '1/mm': ['inverse_length', 1000], '1/in': ['inverse_length', 1 / INCH],
  '1/m²': ['inverse_area', 1], '1/mm²': ['inverse_area', 1e6], '1/in²': ['inverse_area', 1 / INCH ** 2],
  'N/m': ['stiffness', 1], 'N/mm': ['stiffness', 1000], 'lbf/in': ['stiffness', LBF / INCH],
  'N·m/rad': ['torsional_stiffness', 1], 'N·m/deg': ['torsional_stiffness', 1 / DEGREE],
  'lbf·in/deg': ['torsional_stiffness', LBF * INCH / DEGREE],
  'N·m·s/rad': ['rotational_damping', 1], 'lbf·in·s/rad': ['rotational_damping', LBF * INCH],
  s: ['time', 1], ms: ['time', 0.001],
  W: ['power', 1], kW: ['power', 1000], hp: ['power', 550 * LBF * FOOT],
  '1/s': ['ratio_rate', 1],
  // Existing helix percentage controls pass 0..100 percentage points, not 0..1.
  '%': ['dimensionless', 1], '': ['dimensionless', 1],
} as const;

export type DisplayUnit = keyof typeof UNIT_CATALOG;
export type QuantityDimension = (typeof UNIT_CATALOG)[DisplayUnit][0] | 'length_rate';
export type PreferenceScope = 'hardware' | 'vehicle' | 'course' | 'output';
export type UnitScope = PreferenceScope | 'default';
export type QuantityUnitOverrides = Partial<Record<PreferenceScope, Partial<Record<QuantityDimension, DisplayUnit>>>>;

export const DEFAULT_UNITS: Readonly<Record<QuantityDimension, DisplayUnit>> = {
  length: 'mm', area: 'm²', volume: 'm³', angle: 'deg', angular_speed: 'rpm',
  angular_acceleration: 'rad/s²', speed: 'km/h', acceleration: 'm/s²',
  force: 'N', torque: 'N·m', mass: 'kg', density: 'kg/m³', inertia: 'kg·m²',
  first_moment: 'kg·m', inverse_length: '1/m', inverse_area: '1/m²',
  stiffness: 'N/m', torsional_stiffness: 'N·m/rad', rotational_damping: 'N·m·s/rad',
  time: 's', power: 'kW', length_rate: 'mm/s', ratio_rate: '1/s', dimensionless: '',
};

export const QUANTITY_LABELS: Readonly<Record<QuantityDimension, string>> = {
  length: 'Length', area: 'Area', volume: 'Volume', angle: 'Angle', angular_speed: 'Rotational speed',
  angular_acceleration: 'Rotational acceleration', speed: 'Speed', acceleration: 'Acceleration',
  force: 'Force', torque: 'Torque', mass: 'Mass', density: 'Density', inertia: 'Rotational inertia',
  first_moment: 'First mass moment', inverse_length: 'Inverse length', inverse_area: 'Inverse area',
  stiffness: 'Linear spring stiffness', torsional_stiffness: 'Torsional spring stiffness',
  rotational_damping: 'Rotational damping / tracking gain', time: 'Time', power: 'Power',
  length_rate: 'Shift / length rate', ratio_rate: 'Ratio rate', dimensionless: 'Dimensionless',
};

export function unitsForDimension(dimension: QuantityDimension): DisplayUnit[] {
  const physical = dimension === 'length_rate' ? 'speed' : dimension;
  return (Object.keys(UNIT_CATALOG) as DisplayUnit[]).filter(
    unit => UNIT_CATALOG[unit][0] === physical && unit !== 'lb·ft',
  );
}

/** Fields already represented by the nine original preferences never have a
 * second override under quantity_units. This also keeps old clients compatible.
 */
export function extraPreferenceDimensions(scope: PreferenceScope): QuantityDimension[] {
  const common: Partial<Record<PreferenceScope, QuantityDimension[]>> = {
    hardware: ['length', 'mass', 'speed'], vehicle: ['length', 'mass', 'speed'],
    course: ['length', 'speed'], output: ['length', 'speed'],
  };
  return (Object.keys(DEFAULT_UNITS) as QuantityDimension[]).filter(
    dimension => !['dimensionless', 'time'].includes(dimension) && !common[scope]?.includes(dimension)
      && unitsForDimension(dimension).length > 1,
  );
}

export type UnitPreset = 'recommended' | 'metric' | 'si' | 'imperial';
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
  quantity_units: QuantityUnitOverrides;
}

export const RECOMMENDED_UNIT_PREFERENCES: UnitPreferences = {
  preset: 'recommended', hardware_length: 'in', component_mass: 'g', vehicle_length: 'm',
  vehicle_mass: 'kg', course_length: 'm', speed: 'km/h', output_length: 'm',
  output_speed: 'km/h', quantity_units: {},
};

const COMMON_OPTIONS = {
  hardware_length: ['in', 'mm', 'm'], component_mass: ['g', 'kg', 'oz'],
  vehicle_length: ['m', 'ft', 'in'], vehicle_mass: ['kg', 'lb'], course_length: ['m', 'ft'],
  speed: ['km/h', 'm/s', 'mph'], output_length: ['m', 'ft', 'mm', 'in'],
  output_speed: ['km/h', 'm/s', 'mph'],
} as const;
const SCOPES: PreferenceScope[] = ['hardware', 'vehicle', 'course', 'output'];
const record = (value: unknown): Record<string, unknown> =>
  value !== null && typeof value === 'object' && !Array.isArray(value)
    ? value as Record<string, unknown> : {};

export function presetUnitPreferences(preset: UnitPreset): UnitPreferences {
  const base = { ...RECOMMENDED_UNIT_PREFERENCES, preset, quantity_units: {} };
  if (preset === 'metric') return { ...base, hardware_length: 'mm' };
  if (preset === 'si') return {
    ...base, hardware_length: 'm', component_mass: 'kg', speed: 'm/s', output_speed: 'm/s',
    quantity_units: Object.fromEntries(SCOPES.map(scope => [scope, {
      angle: 'rad', angular_speed: 'rad/s', power: 'W', length_rate: 'm/s',
    }])),
  };
  if (preset === 'imperial') return {
    ...base, component_mass: 'oz', vehicle_length: 'ft', vehicle_mass: 'lb', course_length: 'ft',
    speed: 'mph', output_length: 'ft', output_speed: 'mph',
    quantity_units: Object.fromEntries(SCOPES.map(scope => [scope, {
      area: scope === 'hardware' ? 'in²' : 'ft²', volume: scope === 'hardware' ? 'in³' : 'ft³',
      inertia: 'lbm·in²', first_moment: 'lbm·in', force: 'lbf', torque: 'lbf·ft',
      stiffness: 'lbf/in', torsional_stiffness: 'lbf·in/deg', density: 'lbm/ft³',
      rotational_damping: 'lbf·in·s/rad', acceleration: 'ft/s²', power: 'hp', length_rate: 'in/s',
    }])),
  };
  return base;
}

/** Accept older sessions and partial settings without ever trusting invalid unit strings. */
export function normalizeUnitPreferences(value?: unknown): UnitPreferences {
  const source = record(value);
  const preset = ['recommended', 'metric', 'si', 'imperial'].includes(String(source.preset))
    ? source.preset as UnitPreset : 'recommended';
  const result = presetUnitPreferences(preset);
  for (const key of Object.keys(COMMON_OPTIONS) as (keyof typeof COMMON_OPTIONS)[]) {
    const unit = source[key];
    if (typeof unit === 'string' && (COMMON_OPTIONS[key] as readonly string[]).includes(unit))
      Object.assign(result, { [key]: unit });
  }
  // An explicit empty map resets extra overrides; a legacy missing map uses the preset.
  if ('quantity_units' in source) {
    result.quantity_units = {};
    const overrides = record(source.quantity_units);
    for (const scope of SCOPES) {
      const choices = record(overrides[scope]);
      for (const dimension of extraPreferenceDimensions(scope)) {
        const unit = choices[dimension];
        if (typeof unit === 'string' && unitsForDimension(dimension).includes(unit as DisplayUnit))
          result.quantity_units[scope] = { ...result.quantity_units[scope], [dimension]: unit };
      }
    }
  }
  return result;
}

export function preferredDisplayUnit(
  dimension: QuantityDimension, scope: UnitScope, preferences: UnitPreferences,
  fallback = defaultDisplayUnit(dimension),
): DisplayUnit {
  const section = scope === 'default' ? 'hardware' : scope;
  if (section === 'hardware') {
    if (dimension === 'length') return preferences.hardware_length;
    if (dimension === 'mass') return preferences.component_mass;
    if (dimension === 'speed') return preferences.speed;
  }
  if (section === 'vehicle') {
    if (dimension === 'length') return preferences.vehicle_length;
    if (dimension === 'mass') return preferences.vehicle_mass;
    if (dimension === 'speed') return preferences.speed;
  }
  if (section === 'course') {
    if (dimension === 'length') return preferences.course_length;
    if (dimension === 'speed') return preferences.speed;
  }
  if (section === 'output') {
    if (dimension === 'length') return preferences.output_length;
    if (dimension === 'speed') return preferences.output_speed;
  }
  return preferences.quantity_units?.[section]?.[dimension]
    ?? (dimension === 'dimensionless' ? fallback : defaultDisplayUnit(dimension));
}

export function isQuantityDimension(value: string | undefined): value is QuantityDimension {
  return value !== undefined && Object.prototype.hasOwnProperty.call(DEFAULT_UNITS, value);
}
export function defaultDisplayUnit(dimension: QuantityDimension): DisplayUnit { return DEFAULT_UNITS[dimension]; }
export function siToDisplay(valueSi: number, unit: DisplayUnit): number { return valueSi / UNIT_CATALOG[unit][1]; }
export function displayToSi(value: number, unit: DisplayUnit): number { return value * UNIT_CATALOG[unit][1]; }

const ALIASES: Readonly<Record<string, DisplayUnit>> = {
  metre: 'm', metres: 'm', meter: 'm', meters: 'm', millimetre: 'mm', millimetres: 'mm',
  millimeter: 'mm', millimeters: 'mm', centimetre: 'cm', centimetres: 'cm', centimeter: 'cm', centimeters: 'cm',
  inch: 'in', inches: 'in', foot: 'ft', feet: 'ft', degree: 'deg', degrees: 'deg', '°': 'deg',
  'rad/sec': 'rad/s', 'rads/s': 'rad/s', kmh: 'km/h', kph: 'km/h', mps: 'm/s',
  lbft: 'lbf·ft', 'lb-ft': 'lbf·ft', ftlb: 'lbf·ft', 'ft-lb': 'lbf·ft',
  'lb-in': 'lbf·in', 'lbf-in': 'lbf·in', 'lbf-ft': 'lbf·ft', nm: 'N·m', 'n-m': 'N·m',
  kgm: 'kg·m', kgm2: 'kg·m²', kgmm2: 'kg·mm²', gmm2: 'g·mm²',
  lbs: 'lb', lbm: 'lb', pound: 'lb', pounds: 'lb', ounce: 'oz', ounces: 'oz',
  '1': '',
};
const TOKENS = new Map<string, DisplayUnit>(
  (Object.keys(UNIT_CATALOG) as DisplayUnit[]).map(unit => [unit.toLowerCase(), unit]),
);
function normalizedUnitToken(raw: string): DisplayUnit | null {
  const token = raw.trim().replace(/\s+/g, '').replace(/[⋅*]/g, '·')
    .replace(/\^?2/g, '²').replace(/\^?3/g, '³').toLowerCase();
  return TOKENS.get(token) ?? ALIASES[token] ?? ALIASES[raw.trim().toLowerCase()] ?? null;
}
export function displayScale(unit: string): number {
  const recognized = normalizedUnitToken(unit);
  return recognized === null ? 1 : 1 / UNIT_CATALOG[recognized][1];
}
export function dimensionForUnit(unit: string): QuantityDimension | undefined {
  const recognized = normalizedUnitToken(unit);
  return recognized === null ? undefined : UNIT_CATALOG[recognized][0];
}
export function compatibleUnit(dimension: QuantityDimension, unit: DisplayUnit): boolean {
  return UNIT_CATALOG[unit][0] === (dimension === 'length_rate' ? 'speed' : dimension);
}
/** Older reporting metadata called both spring rates "stiffness". The unit disambiguates. */
export function projectedDimension(dimension: string, canonicalUnit: string): QuantityDimension | undefined {
  const fromUnit = dimensionForUnit(canonicalUnit);
  if (dimension === 'stiffness' && fromUnit === 'torsional_stiffness') return fromUnit;
  return isQuantityDimension(dimension) ? dimension : fromUnit;
}
export function displayUnitForCanonical(canonicalUnit: string, dimension?: string): DisplayUnit {
  const known = normalizedUnitToken(canonicalUnit);
  if (known !== null && (!isQuantityDimension(dimension) || compatibleUnit(dimension, known))) return known;
  return isQuantityDimension(dimension) ? defaultDisplayUnit(dimension) : '';
}

export type QuantityParseResult =
  | { valueSi: number; unit: DisplayUnit; error?: undefined }
  | { valueSi?: undefined; unit?: undefined; error: string };
export function parseQuantityText(raw: string, dimension: QuantityDimension, fallbackUnit: DisplayUnit): QuantityParseResult {
  const text = raw.trim().replace(/″|"/g, ' in').replace(/′|'/g, ' ft');
  if (!text) return { error: 'Enter a value.' };
  const match = text.match(/^([+-]?(?:\d+\s*(?:-\s*|\s+)\d+\s*\/\s*\d+|\d+\s*\/\s*\d+|(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?))\s*(.*)$/);
  if (!match) return { error: 'Enter a number, optionally followed by a unit.' };
  const expression = match[1];
  const mixed = expression.match(/^([+-]?\d+)\s*(?:-|\s)\s*(\d+)\s*\/\s*(\d+)$/);
  const fraction = expression.match(/^([+-]?)\s*(\d+)\s*\/\s*(\d+)$/);
  let number = Number(expression);
  if (mixed) number = Number(mixed[1]) + (mixed[1].startsWith('-') ? -1 : 1) * Number(mixed[2]) / Number(mixed[3]);
  else if (fraction) number = (fraction[1] === '-' ? -1 : 1) * Number(fraction[2]) / Number(fraction[3]);
  if (!Number.isFinite(number)) return { error: 'Enter a finite number or a fraction with a nonzero denominator.' };
  const unitText = match[2].trim();
  const unit = unitText ? normalizedUnitToken(unitText) : fallbackUnit;
  if (unit === null) return { error: `Unit “${unitText}” is not supported.` };
  if (!compatibleUnit(dimension, unit)) return { error: `Use a ${dimension.replace(/_/g, ' ')} unit for this field.` };
  const valueSi = displayToSi(number, unit);
  return Number.isFinite(valueSi) ? { valueSi, unit } : { error: 'This quantity is outside the finite numeric range.' };
}

/** Used only for avoiding round-trip noise, not for numerical/model tolerances. */
export function sameQuantity(a: number | null, b: number | null): boolean {
  return a === b || (a !== null && b !== null && Number.isFinite(a) && Number.isFinite(b)
    && Math.abs(a - b) <= 8 * Number.EPSILON * Math.max(Math.abs(a), Math.abs(b)));
}
export function formatEditableQuantity(valueSi: number, unit: DisplayUnit): string {
  const value = Number(siToDisplay(valueSi, unit).toPrecision(15));
  return unit ? `${value} ${unit}` : String(value);
}
/** Keep small nonzero dimensions visible even when a caller used a mm-era decimal budget. */
export function formatDisplayNumber(value: number, maximumFractionDigits = 4): string {
  if (!Number.isFinite(value)) return '—';
  const magnitude = Math.abs(value);
  if (magnitude > 0 && (magnitude < 1e-7 || magnitude >= 1e12))
    return value.toExponential(4).replace(/\.?0+e/, 'e');
  const digits = magnitude > 0 && magnitude < 1
    ? Math.max(maximumFractionDigits, 2 - Math.floor(Math.log10(magnitude))) : maximumFractionDigits;
  return new Intl.NumberFormat(undefined, { maximumFractionDigits: Math.min(12, digits) }).format(value);
}
export function formatQuantity(valueSi: number, dimension: QuantityDimension,
  displayUnit = defaultDisplayUnit(dimension), maximumFractionDigits = 4): string {
  const text = formatDisplayNumber(siToDisplay(valueSi, displayUnit), maximumFractionDigits);
  return displayUnit ? `${text} ${displayUnit}` : text;
}
export function formatPreferredQuantity(valueSi: number, dimension: QuantityDimension, scope: UnitScope,
  preferences: UnitPreferences, fallback = defaultDisplayUnit(dimension), maximumFractionDigits = 4): string {
  return formatQuantity(valueSi, dimension, preferredDisplayUnit(dimension, scope, preferences, fallback), maximumFractionDigits);
}
export function preferredProjectedDisplayUnit(dimension: string, canonicalUnit: string,
  scope: UnitScope, preferences: UnitPreferences): string {
  const resolved = projectedDimension(dimension, canonicalUnit);
  return resolved ? preferredDisplayUnit(resolved, scope, preferences, defaultDisplayUnit(resolved)) : canonicalUnit;
}
export function projectedDisplayValue(valueSi: number, dimension: string, canonicalUnit: string,
  scope: UnitScope, preferences: UnitPreferences): number {
  const resolved = projectedDimension(dimension, canonicalUnit);
  return resolved ? siToDisplay(valueSi, preferredDisplayUnit(resolved, scope, preferences)) : valueSi;
}
export function formatPreferredProjectedQuantity(valueSi: number, dimension: string, canonicalUnit: string,
  scope: UnitScope, preferences: UnitPreferences, maximumFractionDigits = 4): string {
  const unit = preferredProjectedDisplayUnit(dimension, canonicalUnit, scope, preferences);
  const text = formatDisplayNumber(projectedDisplayValue(valueSi, dimension, canonicalUnit, scope, preferences), maximumFractionDigits);
  return unit ? `${text} ${unit}` : text;
}
export function formatProjectedQuantity(valueSi: number, dimension: string, canonicalUnit: string, maximumFractionDigits = 4): string {
  return formatPreferredProjectedQuantity(valueSi, dimension, canonicalUnit, 'output', presetUnitPreferences('recommended'), maximumFractionDigits);
}
