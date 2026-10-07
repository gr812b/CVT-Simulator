import { SimpleGrid, Stack, Text } from '@mantine/core';
import { QuantityInput } from '@components/quantityInput/QuantityInput';
import type { VehicleData } from './api';

export function VehicleEditor({
  value,
  onChange,
  disabled = false,
}: {
  value: VehicleData;
  onChange: (value: VehicleData) => void;
  disabled?: boolean;
}) {
  const patch = (changes: Partial<VehicleData>) =>
    onChange({ ...value, ...changes });
  return (
    <Stack>
      <Text size="sm" c="dimmed">
        Vehicle and locked final-drive properties. The load case supplies the
        road profile separately.
      </Text>
      <SimpleGrid cols={{ base: 1, sm: 2 }}>
        <QuantityInput
          scope="vehicle"
          label="Total vehicle mass"
          value={value.mass_kg}
          unit="kg"
          min={0}
          disabled={disabled}
          description="Include the driver and carried load."
          onChange={(next) => patch({ mass_kg: next })}
        />
        <QuantityInput
          scope="vehicle"
          label="Loaded wheel radius"
          value={value.wheel_radius_m}
          unit="mm"
          min={0}
          disabled={disabled}
          onChange={(next) => patch({ wheel_radius_m: next })}
        />
        <QuantityInput
          scope="vehicle"
          label="Final-drive reduction"
          value={value.reduction_ratio}
          min={0}
          disabled={disabled}
          description="Secondary shaft speed divided by wheel speed."
          onChange={(next) => patch({ reduction_ratio: next })}
        />
        <QuantityInput
          scope="vehicle"
          label="Total wheel rotational inertia"
          value={value.wheel_rotational_inertia_kg_m2}
          unit="kg·m²"
          min={0}
          disabled={disabled}
          description="Combined wheel inertia at the modeled wheel speed."
          onChange={(next) => patch({ wheel_rotational_inertia_kg_m2: next })}
        />
        <QuantityInput
          scope="vehicle"
          label="Other inertia at the secondary shaft"
          value={value.direct_secondary_shaft_inertia_kg_m2}
          unit="kg·m²"
          min={0}
          disabled={disabled}
          description="Excludes the CVT secondary hardware and wheel inertia entered separately."
          onChange={(next) =>
            patch({ direct_secondary_shaft_inertia_kg_m2: next })
          }
        />
        <QuantityInput
          scope="vehicle"
          label="Rolling resistance coefficient"
          value={value.rolling_resistance_coefficient}
          min={0}
          disabled={disabled}
          onChange={(next) => patch({ rolling_resistance_coefficient: next })}
        />
        <QuantityInput
          scope="vehicle"
          label="Drag coefficient"
          value={value.drag_coefficient}
          min={0}
          disabled={disabled}
          onChange={(next) => patch({ drag_coefficient: next })}
        />
        <QuantityInput
          scope="vehicle"
          label="Frontal area"
          value={value.frontal_area_m2}
          unit="m²"
          min={0}
          disabled={disabled}
          onChange={(next) => patch({ frontal_area_m2: next })}
        />
        <QuantityInput
          scope="vehicle"
          label="Air density"
          value={value.air_density_kg_per_m3}
          unit="kg/m³"
          min={0}
          disabled={disabled}
          onChange={(next) => patch({ air_density_kg_per_m3: next })}
        />
      </SimpleGrid>
    </Stack>
  );
}
