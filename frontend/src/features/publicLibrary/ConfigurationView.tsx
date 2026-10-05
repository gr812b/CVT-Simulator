import {
  Accordion,
  Paper,
  SimpleGrid,
  Stack,
  Table,
  Text,
  Title,
} from '@mantine/core';
import type {
  BeltData,
  EngineData,
  PhysicalDocument,
  PhysicalField,
  VehicleData,
} from '../physicalLibrary/api';
import {
  expandJsonPointerTemplate,
  getValueAtJsonPointer,
} from '@utils/jsonPointer';
import { displayScale } from '@utils/units';
import { EngineCurve } from '../physicalLibrary/EngineCurve';

type Measurement = {
  label: string;
  value: number;
  unit?: string;
  scale?: number;
};
function Measurements({ items }: { items: Measurement[] }) {
  return (
    <SimpleGrid cols={{ base: 1, sm: 2, lg: 3 }} component="dl" m={0}>
      {items.map(({ label, value, unit = '', scale }, index) => (
        <div key={`${label}-${index}`}>
          <Text component="dt" size="sm" c="dimmed">
            {label}
          </Text>
          <Text component="dd" m={0} fw={500}>
            {new Intl.NumberFormat(undefined, {
              maximumSignificantDigits: 6,
            }).format(value * (scale ?? displayScale(unit)))}
            {unit ? ` ${unit}` : ''}
          </Text>
        </div>
      ))}
    </SimpleGrid>
  );
}
function BeltView({ value }: { value: BeltData }) {
  return (
    <Measurements
      items={[
        { label: 'Outer length', value: value.outer_length_m, unit: 'mm' },
        { label: 'Top width', value: value.outer_width_m, unit: 'mm' },
        { label: 'Bottom width', value: value.inner_width_m, unit: 'mm' },
        { label: 'Height', value: value.height_m, unit: 'mm' },
        { label: 'Half-angle', value: value.half_angle_rad, unit: 'deg' },
        {
          label: 'Cord depth from top',
          value: value.cord_depth_from_outer_m,
          unit: 'mm',
        },
        { label: 'Density', value: value.density_kg_per_m3, unit: 'kg/m³' },
      ]}
    />
  );
}
function VehicleView({ value }: { value: VehicleData }) {
  return (
    <Measurements
      items={[
        { label: 'Total vehicle mass', value: value.mass_kg, unit: 'kg' },
        {
          label: 'Loaded wheel radius',
          value: value.wheel_radius_m,
          unit: 'mm',
        },
        { label: 'Final-drive reduction', value: value.reduction_ratio },
        {
          label: 'Wheel rotational inertia',
          value: value.wheel_rotational_inertia_kg_m2,
          unit: 'kg·m²',
        },
        {
          label: 'Other secondary shaft inertia',
          value: value.direct_secondary_shaft_inertia_kg_m2,
          unit: 'kg·m²',
        },
        {
          label: 'Rolling resistance coefficient',
          value: value.rolling_resistance_coefficient,
        },
        { label: 'Drag coefficient', value: value.drag_coefficient },
        { label: 'Frontal area', value: value.frontal_area_m2, unit: 'm²' },
        {
          label: 'Air density',
          value: value.air_density_kg_per_m3,
          unit: 'kg/m³',
        },
      ]}
    />
  );
}
function EngineView({ value }: { value: EngineData }) {
  return (
    <Stack>
      <EngineCurve value={value} />
      <Measurements
        items={[
          {
            label: 'Equivalent rotational inertia',
            value: value.equivalent_rotational_inertia_kg_m2,
            unit: 'kg·m²',
          },
        ]}
      />
      <Accordion variant="separated">
        <Accordion.Item value="engine-details">
          <Accordion.Control>Curve values & engine braking</Accordion.Control>
          <Accordion.Panel>
            <Stack>
              <Table>
                <Table.Thead>
                  <Table.Tr>
                    <Table.Th>Speed (rpm)</Table.Th>
                    <Table.Th>FOT torque (N·m)</Table.Th>
                  </Table.Tr>
                </Table.Thead>
                <Table.Tbody>
                  {value.points.map((point) => (
                    <Table.Tr key={point.angular_speed_rad_per_s}>
                      <Table.Td>
                        {(
                          (point.angular_speed_rad_per_s * 30) /
                          Math.PI
                        ).toFixed(0)}
                      </Table.Td>
                      <Table.Td>{point.torque_Nm}</Table.Td>
                    </Table.Tr>
                  ))}
                </Table.Tbody>
              </Table>
              <Measurements
                items={[
                  {
                    label: 'Low-speed braking torque',
                    value: value.low_speed_braking_torque_Nm,
                    unit: 'N·m',
                  },
                  {
                    label: 'Low-speed braking peak',
                    value: value.low_speed_braking_peak_speed_rad_per_s,
                    unit: 'rpm',
                  },
                  {
                    label: 'High-speed braking torque',
                    value: value.high_speed_braking_torque_Nm,
                    unit: 'N·m',
                  },
                  {
                    label: 'High-speed transition width',
                    value: value.high_speed_braking_transition_width_rad_per_s,
                    unit: 'rpm',
                  },
                ]}
              />
            </Stack>
          </Accordion.Panel>
        </Accordion.Item>
      </Accordion>
    </Stack>
  );
}

/** Read-only presentation: no editors, disabled controls, or validation requests. */
export function ConfigurationView({
  document,
  fields,
}: {
  document: PhysicalDocument;
  fields: PhysicalField[];
}) {
  const cvt =
    document.kind === 'setups'
      ? document.data.cvt.data
      : document.kind === 'cvts'
        ? document.data
        : null;
  const engine =
    document.kind === 'setups'
      ? document.data.engine.data
      : document.kind === 'engines'
        ? document.data
        : null;
  const groups = cvt
    ? [
        'geometry',
        'pulleys/primary',
        'pulleys/secondary',
        'inertias',
        'contact',
      ]
        .map((group) => ({
          group,
          items: fields
            .filter(
              (field) =>
                field.path.startsWith(`/${group}/`) &&
                !field.path.startsWith('/geometry/belt'),
            )
            .flatMap((field) =>
              expandJsonPointerTemplate(cvt.assembly, field.path).flatMap(
                (path) => {
                  const value = getValueAtJsonPointer(cvt.assembly, path);
                  const segment = path.match(/\/segments\/(\d+)\//);
                  return typeof value === 'number'
                    ? [
                        {
                          label: `${segment ? `Segment ${Number(segment[1]) + 1} · ` : ''}${field.label}`,
                          value,
                          unit: field.display_unit,
                          scale: field.display_scale,
                        },
                      ]
                    : [];
                },
              ),
            ),
        }))
        .filter((group) => group.items.length)
    : [];
  return (
    <Stack gap="lg">
      {document.kind === 'setups' && (
        <Paper withBorder p="lg">
          <Stack>
            <Title order={2} size="h3">
              Vehicle & drivetrain
            </Title>
            <VehicleView value={document.data.vehicle} />
          </Stack>
        </Paper>
      )}
      {engine && (
        <Paper withBorder p="lg">
          <Stack>
            <Title order={2} size="h3">
              {document.kind === 'setups'
                ? document.data.engine.name
                : 'Full-open-throttle torque curve'}
            </Title>
            <EngineView value={engine} />
          </Stack>
        </Paper>
      )}
      {document.kind === 'belts' && (
        <Paper withBorder p="lg">
          <BeltView value={document.data} />
        </Paper>
      )}
      {cvt && (
        <>
          <Paper withBorder p="lg">
            <Stack>
              <Title order={2} size="h3">
                Belt · {cvt.belt.name}
              </Title>
              <BeltView value={cvt.belt.data} />
              <Text size="sm" c="dimmed">
                CINDER uses the belt half-angle for both sheaves.
              </Text>
            </Stack>
          </Paper>
          <Accordion multiple defaultValue={['geometry']} variant="separated">
            {groups.map(({ group, items }) => (
              <Accordion.Item key={group} value={group}>
                <Accordion.Control tt="capitalize">
                  {group.replace('pulleys/', '')}
                </Accordion.Control>
                <Accordion.Panel>
                  <Measurements items={items} />
                </Accordion.Panel>
              </Accordion.Item>
            ))}
          </Accordion>
        </>
      )}
    </Stack>
  );
}
