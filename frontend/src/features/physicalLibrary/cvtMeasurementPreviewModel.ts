export type CvtMeasurementKey =
  | 'shaft-radius'
  | 'primary-travel'
  | 'deadzone-travel'
  | 'pivot-axial'
  | 'pivot-radius'
  | 'arm-length'
  | 'roller-radius'
  | null;

export function cvtMeasurementKeyForPath(path: string | null): CvtMeasurementKey {
  if (!path) return null;
  if (path === '@primary-shaft-radius') return 'shaft-radius';
  if (path === '/geometry/max_shift_m') return 'primary-travel';
  if (path === '/geometry/deadzone_shift_m') return 'deadzone-travel';
  if (path.endsWith('/pivot_axial_position_m')) return 'pivot-axial';
  if (path.endsWith('/pivot_radius_m')) return 'pivot-radius';
  if (path.endsWith('/arm_length_m')) return 'arm-length';
  if (path.endsWith('/roller_radius_m')) return 'roller-radius';
  return null;
}

export const CVT_MEASUREMENT_LABELS: Record<Exclude<CvtMeasurementKey, null>, string> = {
  'shaft-radius': 'Primary shaft radius',
  'primary-travel': 'Available primary travel',
  'deadzone-travel': 'Primary free travel before belt contact',
  'pivot-axial': 'Flyweight pivot axial position',
  'pivot-radius': 'Flyweight pivot radius',
  'arm-length': 'Pivot-to-roller arm length',
  'roller-radius': 'Flyweight roller radius',
};
