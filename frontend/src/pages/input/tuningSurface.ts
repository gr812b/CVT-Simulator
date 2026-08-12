import primaryImage from '@assets/images/primary_cvt.png';
import secondaryImage from '@assets/images/secondary_cvt.png';
import type { TuneParameter } from '@api/client';

export type TuningGroup = TuneParameter['group'];
export interface ResolvedTuningField extends TuneParameter { image?: string; }

export const GROUP_TITLES: Record<TuningGroup, string> = {
  primary: 'Primary Pulley',
  ramp: 'Ramp Geometry',
  secondary: 'Secondary Pulley',
  helix: 'Helix Geometry',
};

export const GROUPS = Object.keys(GROUP_TITLES) as TuningGroup[];

const IMAGE_BY_GROUP: Record<TuningGroup, string> = {
  primary: primaryImage,
  ramp: primaryImage,
  secondary: secondaryImage,
  helix: secondaryImage,
};

export function resolveTuneSurface(parameters: TuneParameter[]): ResolvedTuningField[] {
  return parameters
    .filter((parameter) => GROUPS.includes(parameter.group))
    .map((parameter) => ({ ...parameter, image: IMAGE_BY_GROUP[parameter.group] }));
}

export function valueForTuneField(field: TuneParameter, values: Record<string, unknown>): unknown {
  return values[field.key] ?? field.defaultValue;
}

export function setTuneFieldValue(
  values: Record<string, unknown>,
  field: TuneParameter,
  next: unknown,
): Record<string, unknown> {
  return { ...values, [field.key]: next };
}
