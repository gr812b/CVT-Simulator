export type HardwareMeasurementKey =
  | 'shaft-radius'
  | 'secondary-radius'
  | 'sheave-angle'
  | 'groove-width'
  | 'deadzone-travel'
  | 'belt-contact-travel'
  | 'pivot-radius'
  | 'arm-length'
  | 'roller-radius';

export function hardwareMeasurementKey(
  path: string | null,
): HardwareMeasurementKey | null {
  if (!path) return null;
  const geometry: Record<string, HardwareMeasurementKey> = {
    '@primary-shaft-radius': 'shaft-radius',
    '@primary-groove-width': 'groove-width',
    '@primary-free-travel': 'deadzone-travel',
    '@primary-belt-contact-travel': 'belt-contact-travel',
    '/geometry/secondary_outer_radius_at_zero_shift_m': 'secondary-radius',
    '/geometry/sheave_half_angle_rad': 'sheave-angle',
    '/geometry/max_shift_m': 'groove-width',
    '/geometry/deadzone_shift_m': 'deadzone-travel',
  };
  if (Object.prototype.hasOwnProperty.call(geometry, path))
    return geometry[path];
  const field = path.match(
    /^\/pulleys\/primary\/components\/\d+\/geometry\/(pivot_radius_m|arm_length_m|roller_radius_m)$/,
  )?.[1];
  return field === 'pivot_radius_m'
    ? 'pivot-radius'
    : field === 'arm_length_m'
      ? 'arm-length'
      : field === 'roller_radius_m'
        ? 'roller-radius'
        : null;
}

export function isPrimaryMeasurement(
  key: HardwareMeasurementKey | null,
): boolean {
  return key === 'pivot-radius' || key === 'arm-length' || key === 'roller-radius';
}
