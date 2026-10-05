import { useState } from 'react';
import {
  Accordion,
  Badge,
  Checkbox,
  Group,
  SimpleGrid,
  Stack,
  Text,
  Tooltip,
} from '@mantine/core';
import { QuantityInput } from '@components/quantityInput/QuantityInput';
import {
  expandJsonPointerTemplate,
  getValueAtJsonPointer,
  setValueAtJsonPointer,
} from '@utils/jsonPointer';
import { BeltPicker } from './BeltPicker';
import { isCvtHardwareField } from './cvtHardware';
import type { CvtData, PhysicalField, PhysicalItem } from './api';

function fieldLabel(field: PhysicalField, path: string) {
  const segment = path.match(/\/segments\/(\d+)\//);
  return segment
    ? `Segment ${Number(segment[1]) + 1} · ${field.label}`
    : field.label;
}

export function CvtEditor({
  value,
  onChange,
  fields,
  belts,
  disabled = false,
  onLoadingChange,
}: {
  value: CvtData;
  onChange: (value: CvtData) => void;
  fields: PhysicalField[];
  belts: PhysicalItem[];
  disabled?: boolean;
  onLoadingChange?: (loading: boolean) => void;
}) {
  const [advanced, setAdvanced] = useState(false);
  const assembly = value.assembly;
  const changeAssembly = (next: CvtData['assembly']) =>
    onChange({ ...value, assembly: next });
  const numericFields = (prefix: string) => (
    <SimpleGrid cols={{ base: 1, sm: 2 }}>
      {fields
        .filter(
          (field) =>
            isCvtHardwareField(field.path) &&
            (advanced || !field.advanced) &&
            field.path.startsWith(prefix.replace(/\/\d+\//g, '/*/')) &&
            !field.path.startsWith('/geometry/belt') &&
            field.path !== '/inertias/belt_density_kg_per_m3' &&
            field.path !== '/geometry/sheave_half_angle_rad',
        )
        .flatMap((field) =>
          expandJsonPointerTemplate(assembly, field.path)
            .filter((path) => path.startsWith(prefix))
            .map((path) => ({ field, path })),
        )
        .map(({ field, path }) => {
          const current = getValueAtJsonPointer(assembly, path);
          if (typeof current !== 'number') return null;
          return (
            <QuantityInput
              key={path}
              label={fieldLabel(field, path)}
              value={current}
              disabled={disabled}
              onChange={(next) =>
                changeAssembly(setValueAtJsonPointer(assembly, path, next))
              }
              unit={field.display_unit}
              scale={field.display_scale ?? 1}
              description={field.description}
              min={field.minimum ?? undefined}
              max={field.maximum ?? undefined}
              integer={field.integer}
            />
          );
        })}
    </SimpleGrid>
  );
  return (
    <Stack gap="lg">
      <Text size="sm" c="dimmed">
        Weights, springs, ramp and helix profiles are adjusted in Tunes for this
        CVT after saving the hardware.
      </Text>
      <Accordion
        variant="separated"
        multiple
        defaultValue={['belt', 'geometry']}
      >
        <Accordion.Item value="belt">
          <Accordion.Control>Reusable belt</Accordion.Control>
          <Accordion.Panel>
            <Stack>
              <BeltPicker
                value={value.belt}
                onChange={(belt) =>
                  onChange({
                    ...value,
                    belt,
                    assembly: {
                      ...value.assembly,
                      geometry: {
                        ...value.assembly.geometry,
                        sheave_half_angle_rad: belt.data.half_angle_rad,
                      },
                    },
                  })
                }
                items={belts}
                disabled={disabled}
                onLoadingChange={onLoadingChange}
              />
            </Stack>
          </Accordion.Panel>
        </Accordion.Item>
        <Accordion.Item value="geometry">
          <Accordion.Control>Pulley geometry & travel</Accordion.Control>
          <Accordion.Panel>
            <Stack>
              <Tooltip
                label="CINDER requires the sheave half-angle to match the selected belt’s half-angle."
                multiline
                w={300}
                withArrow
                events={{ hover: true, focus: true, touch: true }}
              >
                <div tabIndex={0}>
                  <QuantityInput
                    label="Sheave half-angle · set by belt"
                    value={value.belt.data.half_angle_rad}
                    unit="deg"
                    disabled
                    onChange={() => undefined}
                  />
                </div>
              </Tooltip>
              {numericFields('/geometry/')}
            </Stack>
          </Accordion.Panel>
        </Accordion.Item>
        <Accordion.Item value="inertias">
          <Accordion.Control>CVT masses & inertias</Accordion.Control>
          <Accordion.Panel>
            <Stack>
              <Text fw={600}>Primary</Text>
              {numericFields('/inertias/primary/')}
              <Text fw={600}>Secondary</Text>
              {numericFields('/inertias/secondary/')}
            </Stack>
          </Accordion.Panel>
        </Accordion.Item>
        <Accordion.Item value="contact">
          <Accordion.Control>Belt contact</Accordion.Control>
          <Accordion.Panel>
            <Stack>
              <Checkbox
                label="Use the static coefficient for kinetic friction"
                checked={assembly.contact.kinetic_friction_coefficient === null}
                disabled={disabled}
                onChange={(event) =>
                  changeAssembly({
                    ...assembly,
                    contact: {
                      ...assembly.contact,
                      kinetic_friction_coefficient: event.currentTarget.checked
                        ? null
                        : assembly.contact.static_friction_coefficient,
                    },
                  })
                }
              />
              {numericFields('/contact/')}
            </Stack>
          </Accordion.Panel>
        </Accordion.Item>
        {(['primary', 'secondary'] as const).map((mount) => (
          <Accordion.Item key={mount} value={mount}>
            <Accordion.Control>
              {mount === 'primary' ? 'Primary' : 'Secondary'} mounting geometry
            </Accordion.Control>
            <Accordion.Panel>
              <Stack gap="xl">
                {assembly.pulleys[mount].components.map((component, index) => (
                  <Stack key={`${index}-${component.kind}`} gap="md">
                    <Group>
                      <Badge variant="outline">
                        {component.kind.replace(/_/g, ' ')}
                      </Badge>
                    </Group>
                    {numericFields(`/pulleys/${mount}/components/${index}/`)}
                  </Stack>
                ))}
                {assembly.pulleys[mount].helical_coupling && (
                  <Stack>
                    <Text fw={600}>Helical coupling</Text>
                    {numericFields(`/pulleys/${mount}/helical_coupling/`)}
                  </Stack>
                )}
              </Stack>
            </Accordion.Panel>
          </Accordion.Item>
        ))}
      </Accordion>
      <Checkbox
        label="Show advanced geometry compilation settings"
        checked={advanced}
        onChange={(event) => setAdvanced(event.currentTarget.checked)}
      />
      {advanced && (
        <Text size="sm" c="dimmed">
          These numerical controls compile fixed-pivot geometry. Ordinary
          physical edits do not require changing them.
        </Text>
      )}
    </Stack>
  );
}
