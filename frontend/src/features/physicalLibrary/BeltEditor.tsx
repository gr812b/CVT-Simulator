import { Alert, SimpleGrid, Stack } from '@mantine/core';
import { QuantityInput } from '@components/quantityInput/QuantityInput';
import type { BeltData } from './api';

export function BeltEditor({
  value,
  onChange,
  disabled = false,
}: {
  value: BeltData;
  onChange: (value: BeltData) => void;
  disabled?: boolean;
}) {
  const patch = (changes: Partial<BeltData>) =>
    onChange({ ...value, ...changes });
  return (
    <Stack>
      <Alert
        color="blue"
        variant="light"
        title="Measure the belt’s outer length"
      >
        CINDER uses the circumference at the belt’s outer surface. Cord depth is
        measured inward from that surface. Do not substitute a nominal
        part-number length or pitch length.
      </Alert>
      <SimpleGrid cols={{ base: 1, sm: 2 }}>
        <QuantityInput
          label="Outer circumference"
          value={value.outer_length_m}
          unit="mm"
          min={0}
          disabled={disabled}
          onChange={(next) => patch({ outer_length_m: next })}
        />
        <QuantityInput
          label="Belt height"
          value={value.height_m}
          unit="mm"
          min={0}
          disabled={disabled}
          onChange={(next) => patch({ height_m: next })}
        />
        <QuantityInput
          label="Outer width"
          value={value.outer_width_m}
          unit="mm"
          min={0}
          disabled={disabled}
          onChange={(next) => patch({ outer_width_m: next })}
        />
        <QuantityInput
          label="Inner width"
          value={value.inner_width_m}
          unit="mm"
          min={0}
          max={value.outer_width_m}
          disabled={disabled}
          onChange={(next) => patch({ inner_width_m: next })}
        />
        <QuantityInput
          label="Cord depth from outer surface"
          value={value.cord_depth_from_outer_m}
          unit="mm"
          min={0}
          max={value.height_m}
          disabled={disabled}
          onChange={(next) => patch({ cord_depth_from_outer_m: next })}
        />
        <QuantityInput
          label="Belt density"
          value={value.density_kg_per_m3}
          unit="kg/m³"
          min={0}
          disabled={disabled}
          onChange={(next) => patch({ density_kg_per_m3: next })}
        />
      </SimpleGrid>
    </Stack>
  );
}
