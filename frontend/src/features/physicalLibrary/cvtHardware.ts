/** Editable CVT hardware. Replaceable clamping settings live in the tune editor. */
export function isCvtHardwareField(path: string): boolean {
  if (!path.startsWith('/pulleys/')) return true;
  return (
    !['/mass_geometry/', '/ramp_profile/', '/circumferential_profile/'].some(
      (part) => path.includes(part),
    ) &&
    !/\/(stiffness_N_per_m|torsional_stiffness_Nm_per_rad|initial_compression_m|initial_twist_rad|flyweight_mass_kg)$/.test(
      path,
    )
  );
}
