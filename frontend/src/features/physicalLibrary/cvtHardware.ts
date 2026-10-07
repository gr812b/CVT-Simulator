import type { BeltChoice, CvtData, PhysicalField } from './api';

type Assembly = CvtData['assembly'];
type PrimaryComponent = Assembly['pulleys']['primary']['components'][number];
type FixedPivotComponent = Extract<
  PrimaryComponent,
  { kind: 'fixed_pivot_roller_flyweight' }
>;

const EPS = 1e-10;
const RAMP_PLACEMENT_FIELDS = new Set([
  'ramp_reference_axial_position_m',
  'ramp_reference_radius_m',
]);
const REFERENCE_ONLY_FIELDS = new Set(['pivot_axial_position_m']);
const ADVANCED_MECHANICAL_FIELDS = new Set([
  'compression_per_axial_position',
  'ramp_axial_direction',
  'roller_side_sign',
  'movable_member_torque_fraction',
  'opening_per_axial_position',
  'opening_offset_m',
  'root_scan_points',
  'validation_positions',
  'root_residual_tolerance_m2',
  'coordinate_tolerance_m',
  'compilation_points',
  'axial_position_min_m',
  'axial_position_max_m',
]);

const FIELD_COPY: Record<
  string,
  { label: string; description: string }
> = {
  secondary_outer_radius_at_zero_shift_m: {
    label: 'Secondary belt radius',
    description:
      'With the primary fully open, measure from the secondary shaft centreline to the belt outer surface—not the sheave rim or belt cord line.',
  },
  deadzone_shift_m: {
    label: 'Free travel before belt contact',
    description:
      'Measure movable-primary travel from the fully open stop until the belt first contacts both sheave faces.',
  },
  max_shift_m: {
    label: 'Primary travel',
    description:
      'Measure the movable primary sheave from the fully open stop to the fully closed stop along the shaft. Fully open is 0.',
  },
  fixed_rotating_hardware_inertia_kg_m2: {
    label: 'Fixed rotating hardware inertia',
    description:
      'Rotational inertia about this shaft of CVT hardware that does not rotate relative to the shaft. Do not include the engine, flyweights, wheels, or other separately modelled inertia.',
  },
  movable_sheave_rotational_inertia_kg_m2: {
    label: 'Movable sheave rotational inertia',
    description:
      'Rotational inertia of the movable sheave about its shaft. This stays separate only when a relative-rotation coupling such as a helix requires it.',
  },
  moving_sheave_mass_kg: {
    label: 'Movable sheave translating mass',
    description:
      'Mass that translates with the movable sheave along the shaft. Do not include flyweights that are modelled separately.',
  },
  static_friction_coefficient: {
    label: 'Static belt–sheave friction coefficient',
    description: 'Static Coulomb coefficient at the belt sidewalls and sheave faces.',
  },
  kinetic_friction_coefficient: {
    label: 'Kinetic belt–sheave friction coefficient',
    description: 'Kinetic Coulomb coefficient used after gross sliding begins.',
  },
  pivot_axial_position_m: {
    label: 'Flyweight pivot axial position',
    description:
      'With the primary fully open, measure along the shaft from the primary axial datum to the centre of the fixed flyweight pivot.',
  },
  pivot_radius_m: {
    label: 'Pivot radius',
    description: 'Measure radially from the primary shaft centreline to the fixed pivot centre.',
  },
  arm_length_m: {
    label: 'Arm length',
    description: 'Centre-to-centre distance from the fixed flyweight pivot to the roller centre.',
  },
  roller_radius_m: {
    label: 'Roller radius',
    description: 'Measure from the roller centre to its running surface.',
  },
  radius_m: {
    label: 'Helix roller radius',
    description:
      'Measure radially from the secondary shaft centreline to the helix roller/contact-path centreline.',
  },
  compression_per_axial_position: {
    label: 'Spring compression-to-travel mapping',
    description:
      'Signed change in spring compression per metre of positive local sheave motion. It is normally +1 or −1 from the installed spring orientation; change it only for a different coordinate mapping.',
  },
  ramp_axial_direction: {
    label: 'Ramp axial orientation sign',
    description:
      'Maps the positive ramp-profile axial coordinate to the primary sheave axis. This is a coordinate orientation, not the ramp angle.',
  },
  roller_side_sign: {
    label: 'Roller contact-side sign',
    description:
      'Selects which geometric side of the roller contacts the ramp. Leave it unchanged unless the roller/ramp construction is mirrored.',
  },
  movable_member_torque_fraction: {
    label: 'Movable-sheave torque share',
    description:
      'Fraction of secondary shaft torque reacted through the movable member before the helix converts that reaction into axial force.',
  },
  opening_per_axial_position: {
    label: 'Helix opening-to-sheave travel mapping',
    description:
      'Signed mapping from local movable-sheave axial position to the helix opening coordinate. Change only for a different helix coordinate convention.',
  },
  opening_offset_m: {
    label: 'Helix opening-coordinate offset',
    description:
      'Helix opening coordinate corresponding to zero local axial position. This is a coordinate mapping, not an extra physical travel.',
  },
  axial_position_min_m: {
    label: 'Custom contact-search minimum',
    description:
      'Legacy/custom lower bound for the fixed-pivot roller contact search. Ordinary primary travel starts at 0 and does not need this input.',
  },
  axial_position_max_m: {
    label: 'Custom contact-search maximum',
    description:
      'Legacy/custom upper bound for the fixed-pivot roller contact search. Ordinary geometry derives this from available primary travel.',
  },
  root_scan_points: {
    label: 'Contact root scan points',
    description: 'Numerical sampling density used to bracket roller/ramp contact roots.',
  },
  validation_positions: {
    label: 'Construction validation samples',
    description: 'Number of travel positions used for the fixed-pivot construction check.',
  },
  root_residual_tolerance_m2: {
    label: 'Contact root residual tolerance',
    description: 'Numerical residual tolerance used by the roller/ramp contact solve.',
  },
  coordinate_tolerance_m: {
    label: 'Geometry coordinate tolerance',
    description: 'Numerical coordinate tolerance used while compiling the fixed-pivot geometry.',
  },
  compilation_points: {
    label: 'Compiled geometry samples',
    description: 'Number of samples retained in the compiled fixed-pivot geometry map.',
  },
};

function fieldKey(path: string): string {
  return path.split('/').at(-1) ?? '';
}

export function primaryFixedPivot(assembly: Assembly): {
  component: FixedPivotComponent;
  index: number;
} | null {
  const index = assembly.pulleys.primary.components.findIndex(
    (component) => component.kind === 'fixed_pivot_roller_flyweight',
  );
  if (index < 0) return null;
  const component = assembly.pulleys.primary.components[index];
  if (component.kind !== 'fixed_pivot_roller_flyweight') return null;
  return { component, index };
}

/** Editable CVT hardware. Replaceable clamping and ramp settings live in Tunes. */
export function isCvtHardwareField(path: string): boolean {
  if (!path.startsWith('/pulleys/')) return true;
  if (RAMP_PLACEMENT_FIELDS.has(fieldKey(path)) || REFERENCE_ONLY_FIELDS.has(fieldKey(path))) return false;
  return (
    !['/mass_geometry/', '/ramp_profile/', '/circumferential_profile/'].some(
      (part) => path.includes(part),
    ) &&
    !/\/(stiffness_N_per_m|torsional_stiffness_Nm_per_rad|initial_compression_m|initial_twist_rad|flyweight_mass_kg)$/.test(
      path,
    )
  );
}

export function isAdvancedCvtField(field: PhysicalField, path: string): boolean {
  return field.advanced || ADVANCED_MECHANICAL_FIELDS.has(fieldKey(path));
}

export function cvtFieldPresentation(field: PhysicalField, path: string) {
  const copy = FIELD_COPY[fieldKey(path)];
  return {
    label: copy?.label ?? field.label,
    description: copy?.description ?? field.description,
    advanced: isAdvancedCvtField(field, path),
  };
}

export function primaryShaftRadius(value: CvtData): number {
  return (
    value.assembly.geometry.primary_outer_radius_at_zero_shift_m -
    value.belt.data.height_m
  );
}

export function withPrimaryShaftRadius(value: CvtData, shaftRadiusM: number): CvtData {
  return {
    ...value,
    assembly: {
      ...value.assembly,
      geometry: {
        ...value.assembly.geometry,
        primary_outer_radius_at_zero_shift_m:
          shaftRadiusM + value.belt.data.height_m,
      },
    },
  };
}

/** A belt change owns belt dimensions, but not the physical shaft/sleeve radius. */
export function withBeltPreservingPrimaryShaft(
  value: CvtData,
  belt: BeltChoice,
): CvtData {
  const shaftRadiusM = primaryShaftRadius(value);
  const { outer_length_m, density_kg_per_m3, half_angle_rad, length_reference, ...section } = belt.data;
  void length_reference;
  return {
    ...value,
    belt,
    assembly: {
      ...value.assembly,
      geometry: {
        ...value.assembly.geometry,
        sheave_half_angle_rad: half_angle_rad,
        belt_outer_length_m: outer_length_m,
        belt: section,
        primary_outer_radius_at_zero_shift_m: belt.data.height_m === value.belt.data.height_m
          ? value.assembly.geometry.primary_outer_radius_at_zero_shift_m
          : shaftRadiusM + belt.data.height_m,
      },
      inertias: { ...value.assembly.inertias, belt_density_kg_per_m3: density_kg_per_m3 },
    },
  };
}

export function primaryHasRelativeRotationCoupling(value: CvtData): boolean {
  return value.assembly.pulleys.primary.helical_coupling != null;
}

export function primaryRotatingHardwareInertia(value: CvtData): number {
  const primary = value.assembly.inertias.primary;
  return (
    primary.fixed_rotating_hardware_inertia_kg_m2 +
    primary.movable_sheave_rotational_inertia_kg_m2
  );
}

/** Preserve the existing split while exposing a single total when the split is dynamically irrelevant. */
export function withPrimaryRotatingHardwareInertia(
  value: CvtData,
  totalKgM2: number,
): CvtData {
  const primary = value.assembly.inertias.primary;
  const current = primaryRotatingHardwareInertia(value);
  const fixedFraction = current > 0
    ? primary.fixed_rotating_hardware_inertia_kg_m2 / current
    : 1;
  const fixed = totalKgM2 * fixedFraction;
  return {
    ...value,
    assembly: {
      ...value.assembly,
      inertias: {
        ...value.assembly.inertias,
        primary: {
          ...primary,
          fixed_rotating_hardware_inertia_kg_m2: fixed,
          movable_sheave_rotational_inertia_kg_m2: totalKgM2 - fixed,
        },
      },
    },
  };
}

export function usesOrdinaryPrimaryTravel(value: CvtData): boolean {
  const fixedPivot = primaryFixedPivot(value.assembly);
  if (!fixedPivot) return false;
  const geometry = fixedPivot.component.geometry;
  return (
    Math.abs(geometry.axial_position_min_m) <= EPS &&
    Math.abs(
      geometry.axial_position_max_m - value.assembly.geometry.max_shift_m,
    ) <= EPS
  );
}

export function isOrdinaryPrimaryTravelField(path: string, value: CvtData): boolean {
  if (!usesOrdinaryPrimaryTravel(value)) return false;
  const fixedPivot = primaryFixedPivot(value.assembly);
  if (!fixedPivot) return false;
  const prefix = `/pulleys/primary/components/${fixedPivot.index}/geometry/`;
  return (
    path === `${prefix}axial_position_min_m` ||
    path === `${prefix}axial_position_max_m`
  );
}

export function withAvailablePrimaryTravel(value: CvtData, travelM: number): CvtData {
  const ordinary = usesOrdinaryPrimaryTravel(value);
  const fixedPivot = primaryFixedPivot(value.assembly);
  const base: CvtData = {
    ...value,
    assembly: {
      ...value.assembly,
      geometry: { ...value.assembly.geometry, max_shift_m: travelM },
    },
  };
  if (!ordinary || !fixedPivot) return base;
  const components = base.assembly.pulleys.primary.components.map((component, index) =>
    index === fixedPivot.index && component.kind === 'fixed_pivot_roller_flyweight'
      ? {
          ...component,
          geometry: {
            ...component.geometry,
            axial_position_min_m: 0,
            axial_position_max_m: travelM,
          },
        }
      : component,
  ) as typeof base.assembly.pulleys.primary.components;
  return {
    ...base,
    assembly: {
      ...base.assembly,
      pulleys: {
        ...base.assembly.pulleys,
        primary: { ...base.assembly.pulleys.primary, components },
      },
    },
  };
}

export function isCanonicalPrimaryRadiusField(path: string): boolean {
  return path === '/geometry/primary_outer_radius_at_zero_shift_m';
}

export function isPrimaryRotationalInertiaField(path: string): boolean {
  return (
    path === '/inertias/primary/fixed_rotating_hardware_inertia_kg_m2' ||
    path === '/inertias/primary/movable_sheave_rotational_inertia_kg_m2'
  );
}
