import { Button, Group, Stack, Text } from '@mantine/core';
import { QuantityInput } from '@components/quantityInput/QuantityInput';
import type { SlidingBlockDemo, SlidingBlockInputs } from '@api/client';
import styles from './SlidingBlock.module.scss';

export type Feature = SlidingBlockDemo['fields'][number]['feature'];
export type DimensionKey = SlidingBlockDemo['fields'][number]['key'];
const featureNames: Record<Feature, string> = {
  block: 'Block',
  cup: 'Reaction cup',
  ramp: 'Movable ramp',
  assembly: 'Stroke',
};

export function SlidingBlockEditor({
  data,
  inputs,
  selected,
  onSelect,
  onChange,
  onFocus,
  findings,
}: {
  data: SlidingBlockDemo;
  inputs: SlidingBlockInputs;
  selected: Feature;
  onSelect: (feature: Feature) => void;
  onChange: (key: DimensionKey, value: number) => void;
  onFocus: (key: DimensionKey) => void;
  findings: SlidingBlockDemo['findings'];
}) {
  return (
    <Stack className={styles.dimensionForm} gap="md">
      <Group gap="xs" aria-label="Section features">
        {(Object.keys(featureNames) as Feature[]).map((feature) => (
          <Button
            key={feature}
            size="xs"
            variant={selected === feature ? 'filled' : 'default'}
            aria-pressed={selected === feature}
            onClick={() => onSelect(feature)}
          >
            {featureNames[feature]}
          </Button>
        ))}
      </Group>
      <Text fw={600}>{featureNames[selected]} dimensions</Text>
      {data.fields
        .filter((field) => field.feature === selected)
        .map((field) => (
          <div key={field.key}>
            <QuantityInput
              draftKey={`sliding:${field.key}`}
              documentPath={`/${field.key}`}
              scope="hardware"
              label={field.label}
              description={field.description}
              value={inputs[field.key]}
              unit={field.unit}
              min={field.minimum ?? undefined}
              max={field.maximum ?? undefined}
              onChange={(value) => onChange(field.key, value)}
              onFocusChange={(focused) => {
                if (focused) onFocus(field.key);
              }}
            />
            {findings
              .filter((finding) => finding.field === field.key)
              .map((finding) => (
                <Text key={finding.code} c="red" size="xs" mt="xs">
                  {finding.message}
                </Text>
              ))}
          </div>
        ))}
      {selected === 'ramp' && (
        <Text size="xs" c="dimmed">
          The block face shares this angle. The belt-facing cone remains a
          separate 20° surface.
        </Text>
      )}
      {selected === 'block' && (
        <Text size="xs" c="dimmed">
          Three identical uniform-steel weights. Dimensions update their mass,
          COM and inertia together.
        </Text>
      )}
    </Stack>
  );
}
