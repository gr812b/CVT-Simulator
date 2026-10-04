import { useState } from 'react';
import {
  Accordion,
  Badge,
  Button,
  Checkbox,
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
  type JsonValue,
} from '@utils/jsonPointer';
import { BeltEditor } from './BeltEditor';
import { ComponentPicker } from './ComponentPicker';
import type { CvtData, PhysicalField, PhysicalItem } from './api';

function fieldLabel(field: PhysicalField, path: string) {
  const segment = path.match(/\/segments\/(\d+)\//);
  return segment
    ? `Segment ${Number(segment[1]) + 1} · ${field.label}`
    : field.label;
}

function ProfileActions({
  assembly,
  prefix,
  onChange,
}: {
  assembly: CvtData['assembly'];
  prefix: string;
  onChange: (assembly: CvtData['assembly']) => void;
}) {
  const profiles: { path: string; segments: JsonValue[] }[] = [];
  const visit = (value: unknown, path: string) => {
    if (!value || typeof value !== 'object') return;
    Object.entries(value).forEach(([key, child]) => {
      const next = `${path}/${key}`;
      if (key === 'segments' && Array.isArray(child) && next.startsWith(prefix))
        profiles.push({ path: next, segments: child as JsonValue[] });
      else visit(child, next);
    });
  };
  visit(assembly, '');
  return (
    <Stack gap="xs">
      {profiles.map((profile) => (
        <Group key={profile.path}>
          <Text size="sm">
            {profile.path.includes('circumferential')
              ? 'Helix profile'
              : 'Ramp profile'}
          </Text>
          <Button
            size="xs"
            variant="light"
            disabled={profile.segments.length >= 24}
            onClick={() =>
              onChange(
                setValueAtJsonPointer(assembly, profile.path, [
                  ...profile.segments,
                  structuredClone(profile.segments.at(-1)!),
                ]),
              )
            }
          >
            Duplicate final segment
          </Button>
          <Button
            size="xs"
            variant="subtle"
            color="red"
            disabled={profile.segments.length <= 1}
            onClick={() =>
              onChange(
                setValueAtJsonPointer(
                  assembly,
                  profile.path,
                  profile.segments.slice(0, -1),
                ),
              )
            }
          >
            Remove final segment
          </Button>
        </Group>
      ))}
    </Stack>
  );
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
            (advanced || !field.advanced) &&
            field.path.startsWith(prefix.replace(/\/\d+\//g, '/*/')) &&
            !field.path.startsWith('/geometry/belt') &&
            field.path !== '/inertias/belt_density_kg_per_m3',
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
      <Accordion
        variant="separated"
        multiple
        defaultValue={['belt', 'geometry']}
      >
        <Accordion.Item value="belt">
          <Accordion.Control>Reusable belt</Accordion.Control>
          <Accordion.Panel>
            <Stack>
              <ComponentPicker
                kind="belts"
                value={value.belt}
                onChange={(belt) => onChange({ ...value, belt })}
                items={belts}
                disabled={disabled}
                onLoadingChange={onLoadingChange}
              />
              <BeltEditor
                value={value.belt.data}
                onChange={(data) =>
                  onChange({ ...value, belt: { ...value.belt, data } })
                }
                disabled={disabled}
              />
            </Stack>
          </Accordion.Panel>
        </Accordion.Item>
        <Accordion.Item value="geometry">
          <Accordion.Control>Pulley geometry & travel</Accordion.Control>
          <Accordion.Panel>{numericFields('/geometry/')}</Accordion.Panel>
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
              {mount === 'primary' ? 'Primary' : 'Secondary'} actuator hardware
              & profiles
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
                {!disabled && (
                  <ProfileActions
                    assembly={assembly}
                    prefix={`/pulleys/${mount}/`}
                    onChange={changeAssembly}
                  />
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
