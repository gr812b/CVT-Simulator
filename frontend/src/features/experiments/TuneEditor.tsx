import {
  Accordion,
  Button,
  Group,
  SimpleGrid,
  Stack,
  Text,
} from '@mantine/core';
import { QuantityInput } from '@components/quantityInput/QuantityInput';
import {
  expandJsonPointerTemplate,
  getValueAtJsonPointer,
  setValueAtJsonPointer,
} from '@utils/jsonPointer';
import type { Tune, TuneField, TuneSurface } from './api';

type RampField = Extract<TuneField, { kind: 'ramp' }>;
function RampEditor({
  field,
  value,
  onChange,
}: {
  field: RampField;
  value: RampField['default'];
  onChange: (value: RampField['default']) => void;
}) {
  return (
    <Stack>
      <Text size="sm" c="dimmed">
        {field.description} Changes are validated against the selected CINDER
        assembly.
      </Text>
      <SimpleGrid cols={{ base: 1, sm: 2 }}>
        {field.fields
          .flatMap((hint) =>
            expandJsonPointerTemplate(value, hint.path).map((path) => ({
              hint,
              path,
            })),
          )
          .map(({ hint, path }) => {
            const current = getValueAtJsonPointer(value, path);
            if (typeof current !== 'number') return null;
            const segment = path.match(/\/segments\/(\d+)\//);
            return (
              <QuantityInput
                key={path}
                label={`${segment ? `Segment ${Number(segment[1]) + 1} · ` : ''}${hint.label}`}
                value={current}
                onChange={(next) =>
                  onChange(setValueAtJsonPointer(value, path, next))
                }
                unit={hint.display_unit}
                scale={hint.display_scale}
                min={hint.minimum ?? undefined}
                max={hint.maximum ?? undefined}
                integer={hint.integer}
              />
            );
          })}
      </SimpleGrid>
      <Group>
        <Button
          variant="light"
          size="xs"
          disabled={value.segments.length >= 24}
          onClick={() =>
            onChange({
              ...value,
              segments: [
                ...value.segments,
                structuredClone(value.segments.at(-1)!),
              ],
            })
          }
        >
          Duplicate final segment
        </Button>
        <Button
          variant="subtle"
          size="xs"
          disabled={value.segments.length <= 1}
          onClick={() =>
            onChange({ ...value, segments: value.segments.slice(0, -1) })
          }
        >
          Remove final segment
        </Button>
      </Group>
    </Stack>
  );
}

export function TuneEditor({
  value,
  surface,
  onChange,
}: {
  value: Tune;
  surface: TuneSurface;
  onChange: (value: Tune) => void;
}) {
  const change = (key: string, next: NonNullable<Tune['values']>[string]) =>
    onChange({ ...value, values: { ...value.values, [key]: next } });
  return (
    <Stack>
      <Text size="sm" c="dimmed">
        Pinned to {surface.setup_name} · revision{' '}
        {surface.setup_revision_number}. Editing these values does not change
        the physical setup.
      </Text>
      <SimpleGrid cols={{ base: 1, sm: 2 }}>
        {surface.fields
          .filter((field) => field.kind === 'number')
          .map((field) => (
            <QuantityInput
              key={field.key}
              label={field.label}
              value={
                typeof value.values?.[field.key] === 'number'
                  ? (value.values[field.key] as number)
                  : field.default
              }
              onChange={(next) => change(field.key, next)}
              unit={field.display_unit}
              scale={field.display_scale}
              description={field.description}
              min={field.minimum ?? undefined}
              max={field.maximum ?? undefined}
            />
          ))}
      </SimpleGrid>
      <Accordion variant="separated" multiple>
        {surface.fields
          .filter((field) => field.kind === 'ramp')
          .map((field) => {
            const current = value.values?.[field.key];
            return (
              <Accordion.Item key={field.key} value={field.key}>
                <Accordion.Control>{field.label}</Accordion.Control>
                <Accordion.Panel>
                  <RampEditor
                    field={field}
                    value={
                      typeof current === 'object' && current !== null
                        ? current
                        : field.default
                    }
                    onChange={(next) => change(field.key, next)}
                  />
                </Accordion.Panel>
              </Accordion.Item>
            );
          })}
      </Accordion>
    </Stack>
  );
}
