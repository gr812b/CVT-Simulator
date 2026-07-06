import primaryImage from '@assets/images/primary_cvt.png';
import secondaryImage from '@assets/images/secondary_cvt.png';
import environmentImage from '@assets/images/environment.png';
import type { SimulationCaseDocument, EditorSchema, ComponentDescriptor, EditableFieldDescriptor } from '@api/client';
import { getValueAtJsonPointer } from '@utils/jsonPointer';

export type TuningGroup = 'primary' | 'ramp' | 'secondary' | 'helix' | 'environment';
export interface ResolvedTuningField { id: string; group: TuningGroup; path: string; kind: 'number' | 'ramp'; label: string; description: string; dimension?: string; canonicalUnit: string; minimum?: number; image?: string; }
type NumberSurface = { id: string; group: TuningGroup; kind: 'number'; label: string; fallbackDescription: string; path?: string; mount?: 'input' | 'output'; componentKind?: string; parameter?: string; dimension: string; canonicalUnit: string; image?: string; };
type RampSurface = { id: string; group: TuningGroup; kind: 'ramp'; label: string; fallbackDescription: string; mount: 'input' | 'output'; componentKind?: string; parameter?: string; path?: string; image?: string; };
type Surface = NumberSurface | RampSurface;

export const GROUP_TITLES: Record<TuningGroup, string> = { primary: 'Primary Pulley', ramp: 'Ramp Geometry', secondary: 'Secondary Pulley', helix: 'Helix Geometry', environment: 'Environment' };
export const GROUPS = Object.keys(GROUP_TITLES) as TuningGroup[];
export const SURFACE: readonly Surface[] = [
  { id: 'flyweight', group: 'primary', kind: 'number', label: 'Flyweight Mass', fallbackDescription: 'Mass of the input centrifugal-ramp actuator.', mount: 'input', componentKind: 'centrifugal_ramp', parameter: 'flyweight_mass_kg', dimension: 'mass', canonicalUnit: 'kg', image: primaryImage },
  { id: 'primary-stiffness', group: 'primary', kind: 'number', label: 'Primary Spring Rate', fallbackDescription: 'Stiffness of the input axial spring.', mount: 'input', componentKind: 'axial_spring', parameter: 'stiffness_N_per_m', dimension: 'stiffness', canonicalUnit: 'N/m', image: primaryImage },
  { id: 'primary-preload', group: 'primary', kind: 'number', label: 'Primary Spring Pretension', fallbackDescription: 'Initial compression of the input axial spring.', mount: 'input', componentKind: 'axial_spring', parameter: 'initial_compression_m', dimension: 'length', canonicalUnit: 'm', image: primaryImage },
  { id: 'primary-ramp', group: 'ramp', kind: 'ramp', label: 'Ramp Geometry', fallbackDescription: 'Input centrifugal-ramp profile.', mount: 'input', componentKind: 'centrifugal_ramp', parameter: 'radial_displacement_profile', image: primaryImage },
  { id: 'secondary-torsion', group: 'secondary', kind: 'number', label: 'Secondary Torsion Spring Rate', fallbackDescription: 'Torsional stiffness of the output torque-reaction component.', mount: 'output', componentKind: 'helical_torque_reaction', parameter: 'torsional_stiffness_Nm_per_rad', dimension: 'torque', canonicalUnit: 'N·m/rad', image: secondaryImage },
  { id: 'secondary-compression', group: 'secondary', kind: 'number', label: 'Secondary Compression Spring Rate', fallbackDescription: 'Stiffness of the output axial spring.', mount: 'output', componentKind: 'axial_spring', parameter: 'stiffness_N_per_m', dimension: 'stiffness', canonicalUnit: 'N/m', image: secondaryImage },
  { id: 'secondary-twist', group: 'secondary', kind: 'number', label: 'Secondary Rotational Spring Pretension', fallbackDescription: 'Initial twist of the output torque-reaction component.', mount: 'output', componentKind: 'helical_torque_reaction', parameter: 'initial_twist_rad', dimension: 'angle', canonicalUnit: 'rad', image: secondaryImage },
  { id: 'secondary-preload', group: 'secondary', kind: 'number', label: 'Secondary Linear Spring Pretension', fallbackDescription: 'Initial compression of the output axial spring.', mount: 'output', componentKind: 'axial_spring', parameter: 'initial_compression_m', dimension: 'length', canonicalUnit: 'm', image: secondaryImage },
  { id: 'helix-profile', group: 'helix', kind: 'ramp', label: 'Helix Geometry', fallbackDescription: 'Output helical coupling profile.', mount: 'output', path: '/assembly/pulleys/output/helical_coupling/profile/circumferential_profile', image: secondaryImage },
  { id: 'vehicle-mass', group: 'environment', kind: 'number', label: 'Vehicle Mass (incl. driver)', fallbackDescription: 'Combined vehicle and driver mass in the locked final-drive boundary.', path: '/output_boundary/vehicle/mass_kg', dimension: 'mass', canonicalUnit: 'kg', image: environmentImage },
  { id: 'incline', group: 'environment', kind: 'number', label: 'Angle of Incline', fallbackDescription: 'Constant grade angle in the road-profile boundary.', path: '/output_boundary/road_profile/grade_angle_rad', dimension: 'angle', canonicalUnit: 'rad', image: environmentImage },
];

const componentIndex = (document: SimulationCaseDocument, mount: 'input' | 'output', kind: string): number => {
  const components = document.assembly.pulleys[mount].components as unknown as Array<Record<string, unknown>>;
  return components.findIndex((component) => component.kind === kind);
};
const descriptor = (schema: EditorSchema | null, field: Surface): EditableFieldDescriptor | ComponentDescriptor['parameters'][number] | undefined => {
  if (!schema) return undefined;
  if (field.path) return schema.fields.find((candidate) => candidate.pathTemplate === field.path);
  const component = schema.components.find((candidate) => candidate.kind === field.componentKind);
  return component?.parameters.find((candidate) => candidate.key === field.parameter);
};

export function resolveSurface(document: SimulationCaseDocument, schema: EditorSchema | null): ResolvedTuningField[] {
  return SURFACE.flatMap((field) => {
    let path = field.path;
    if (!path && field.mount && field.componentKind && field.parameter) {
      const index = componentIndex(document, field.mount, field.componentKind);
      if (index < 0) return [];
      path = `/assembly/pulleys/${field.mount}/components/${index}/${field.parameter}`;
    }
    if (!path) return [];
    const value = getValueAtJsonPointer(document, path);
    if (field.kind === 'number' && typeof value !== 'number') return [];
    const meta = descriptor(schema, field);
    const componentMeta = 'key' in (meta ?? {}) ? meta : undefined;
    const scalarMeta = 'pathTemplate' in (meta ?? {}) ? meta : undefined;
    return [{ id: field.id, group: field.group, path, kind: field.kind, label: meta?.label ?? field.label, description: meta?.description ?? field.fallbackDescription, dimension: componentMeta?.dimension ?? scalarMeta?.dimension ?? (field.kind === 'number' ? field.dimension : undefined), canonicalUnit: componentMeta?.canonicalUnit ?? scalarMeta?.canonicalUnit ?? (field.kind === 'number' ? field.canonicalUnit : '1'), minimum: componentMeta?.minimum ?? scalarMeta?.minimum, image: field.image }];
  });
}
