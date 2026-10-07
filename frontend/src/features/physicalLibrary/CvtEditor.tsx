import { useEffect, useState, type ReactNode } from 'react';
import {
  Accordion,
  ActionIcon,
  Badge,
  Checkbox,
  Group,
  Popover,
  SimpleGrid,
  Stack,
  Text,
  Tooltip,
} from '@mantine/core';
import { IconInfoCircle } from '@tabler/icons-react';
import { QuantityInput } from '@components/quantityInput/QuantityInput';
import {
  expandJsonPointerTemplate,
  getValueAtJsonPointer,
  setValueAtJsonPointer,
} from '@utils/jsonPointer';
import { BeltPicker } from './BeltPicker';
import { CvtMeasurementPreview } from './CvtMeasurementPreview';
import {
  cvtFieldPresentation,
  isCanonicalPrimaryRadiusField,
  isCvtHardwareField,
  isOrdinaryPrimaryTravelField,
  isPrimaryRotationalInertiaField,
  primaryHasRelativeRotationCoupling,
  primaryRotatingHardwareInertia,
  primaryShaftRadius,
  withAvailablePrimaryTravel,
  withBeltPreservingPrimaryShaft,
  withPrimaryRotatingHardwareInertia,
  withPrimaryShaftRadius,
} from './cvtHardware';
import type {
  CvtData,
  PhysicalField,
  PhysicalItem,
  PhysicalValidation,
} from './api';

function componentLabel(kind: string): string {
  return {
    fixed_pivot_roller_flyweight: 'Flyweight / roller mechanism',
    axial_spring: 'Axial spring',
    helical_torque_reaction: 'Torque reaction',
  }[kind] ?? kind.replace(/_/g, ' ');
}

function fieldLabel(field: PhysicalField, path: string) {
  const segment = path.match(/\/segments\/(\d+)\//);
  const label = cvtFieldPresentation(field, path).label;
  return segment ? `Segment ${Number(segment[1]) + 1} · ${label}` : label;
}

function FieldInfo({ label, description }: { label: string; description: string }) {
  if (!description) return null;
  return (
    <Popover width={320} position="bottom-end" withArrow shadow="md">
      <Popover.Target>
        <ActionIcon
          type="button"
          variant="subtle"
          color="gray"
          aria-label={`About ${label}`}
        >
          <IconInfoCircle size={17} />
        </ActionIcon>
      </Popover.Target>
      <Popover.Dropdown>
        <Text size="sm">{description}</Text>
      </Popover.Dropdown>
    </Popover>
  );
}

function AdvancedSection({
  title = 'Advanced mechanical settings',
  forceOpen,
  children,
}: {
  title?: string;
  forceOpen: boolean;
  children: ReactNode;
}) {
  const [opened, setOpened] = useState(forceOpen);
  useEffect(() => {
    if (forceOpen) setOpened(true);
  }, [forceOpen]);
  return (
    <Accordion
      variant="contained"
      value={opened ? 'advanced' : null}
      onChange={(value) => setOpened(value === 'advanced')}
    >
      <Accordion.Item value="advanced">
        <Accordion.Control>{title}</Accordion.Control>
        <Accordion.Panel>
          <Stack gap="md">
            {forceOpen && (
              <Text size="sm" c="red">
                This section is open because the latest input check reported an
                error in one of these settings.
              </Text>
            )}
            {children}
          </Stack>
        </Accordion.Panel>
      </Accordion.Item>
    </Accordion>
  );
}

type Entry = { field: PhysicalField; path: string };

export function CvtEditor({
  value,
  onChange,
  fields,
  belts,
  validation = null,
  disabled = false,
  onLoadingChange,
}: {
  value: CvtData;
  onChange: (value: CvtData) => void;
  fields: PhysicalField[];
  belts: PhysicalItem[];
  validation?: PhysicalValidation | null;
  disabled?: boolean;
  onLoadingChange?: (loading: boolean) => void;
}) {
  const assembly = value.assembly;
  const [focusedPath, setFocusedPath] = useState<string | null>(null);
  const focusPath = (path: string) => (focused: boolean) =>
    setFocusedPath((current) => focused ? path : current === path ? null : current);
  const primaryCoupled = primaryHasRelativeRotationCoupling(value);
  const changeAssembly = (next: CvtData['assembly']) =>
    onChange({ ...value, assembly: next });
  const entries = (prefix: string, advanced: boolean): Entry[] =>
    fields
      .filter(
        (field) =>
          isCvtHardwareField(field.path) &&
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
      .filter(({ field, path }) => {
        const presentation = cvtFieldPresentation(field, path);
        if (presentation.advanced !== advanced) return false;
        if (isCanonicalPrimaryRadiusField(path)) return false;
        if (!primaryCoupled && isPrimaryRotationalInertiaField(path)) return false;
        if (isOrdinaryPrimaryTravelField(path, value)) return false;
        return typeof getValueAtJsonPointer(assembly, path) === 'number';
      });

  const advancedHasError = (items: Entry[]) => {
    const paths = new Set(items.map(({ path }) => path));
    return (
      validation?.findings.some((finding) => {
        if (finding.severity !== 'error' || !finding.document_path) return false;
        const documentPath = finding.document_path.replace(/^\/assembly/, '');
        return [...paths].some(
          (path) => documentPath === path || documentPath.startsWith(`${path}/`),
        );
      }) ?? false
    );
  };

  const changePath = (path: string, next: number) => {
    if (path === '/geometry/max_shift_m') {
      onChange(withAvailablePrimaryTravel(value, next));
      return;
    }
    changeAssembly(setValueAtJsonPointer(assembly, path, next));
  };

  const renderEntries = (items: Entry[]) => (
    <SimpleGrid cols={{ base: 1, sm: 2 }}>
      {items.map(({ field, path }) => {
        const current = getValueAtJsonPointer(assembly, path);
        if (typeof current !== 'number') return null;
        const presentation = cvtFieldPresentation(field, path);
        const label = fieldLabel(field, path);
        const input = (
          <QuantityInput
            scope="hardware"
            key={path}
            label={label}
            value={current}
            disabled={disabled}
            onChange={(next) => changePath(path, next)}
            unit={field.display_unit}
            scale={field.display_scale ?? 1}
            description={presentation.advanced ? undefined : presentation.description}
            min={field.minimum ?? undefined}
            max={field.maximum ?? undefined}
            integer={field.integer}
            onFocusChange={focusPath(path)}
          />
        );
        return presentation.advanced && presentation.description ? (
          <Group key={path} align="end" wrap="nowrap">
            <div style={{ flex: 1 }}>{input}</div>
            <FieldInfo label={label} description={presentation.description} />
          </Group>
        ) : (
          input
        );
      })}
    </SimpleGrid>
  );

  const componentFields = (prefix: string) => {
    const basic = entries(prefix, false);
    const advanced = entries(prefix, true);
    return (
      <Stack gap="md">
        {basic.length > 0 && renderEntries(basic)}
        {advanced.length > 0 && (
          <AdvancedSection forceOpen={advancedHasError(advanced)}>
            {renderEntries(advanced)}
          </AdvancedSection>
        )}
      </Stack>
    );
  };

  return (
    <Stack gap="lg">
      <Text size="sm" c="dimmed">
        Enter fixed hardware measurements here. Flyweight mass, springs, ramp
        placement, ramp shape and helix shape are adjusted in Tunes after the
        CVT is saved.
      </Text>
      <Accordion variant="separated" multiple defaultValue={['belt', 'geometry']}>
        <Accordion.Item value="belt">
          <Accordion.Control>Reusable belt</Accordion.Control>
          <Accordion.Panel>
            <Stack>
              <BeltPicker
                value={value.belt}
                onChange={(belt) => onChange(withBeltPreservingPrimaryShaft(value, belt))}
                items={belts}
                disabled={disabled}
                onLoadingChange={onLoadingChange}
              />
              <Text size="xs" c="dimmed">
                Changing the belt keeps the physical primary shaft/sleeve radius
                unchanged and updates CINDER’s outer-belt radius from the new
                belt height.
              </Text>
            </Stack>
          </Accordion.Panel>
        </Accordion.Item>
        <Accordion.Item value="geometry">
          <Accordion.Control>Pulley geometry & travel</Accordion.Control>
          <Accordion.Panel>
            <Stack>
              <CvtMeasurementPreview value={value} activePath={focusedPath} />
              <Tooltip
                label="CINDER requires the sheave half-angle to match the selected belt’s half-angle."
                multiline
                w={300}
                withArrow
                events={{ hover: true, focus: true, touch: true }}
              >
                <div tabIndex={0}>
                  <QuantityInput
                    scope="hardware"
                    label="Sheave half-angle · set by belt"
                    value={value.belt.data.half_angle_rad}
                    unit="deg"
                    disabled
                    onChange={() => undefined}
                  />
                </div>
              </Tooltip>
              <QuantityInput
                scope="hardware"
                label="Primary shaft radius"
                value={primaryShaftRadius(value)}
                unit="mm"
                min={0}
                disabled={disabled}
                description="Outside radius of the shaft or sleeve supporting the belt at low ratio, measured from the primary shaft centreline. This is not the bore radius or cord-line radius."
                onChange={(next) => onChange(withPrimaryShaftRadius(value, next))}
                onFocusChange={focusPath('@primary-shaft-radius')}
              />
              {componentFields('/geometry/')}
            </Stack>
          </Accordion.Panel>
        </Accordion.Item>
        <Accordion.Item value="inertias">
          <Accordion.Control>CVT masses & inertias</Accordion.Control>
          <Accordion.Panel>
            <Stack>
              <Text fw={600}>Primary</Text>
              {!primaryCoupled && (
                <QuantityInput
                  scope="hardware"
                  label="Primary rotating hardware inertia"
                  value={primaryRotatingHardwareInertia(value)}
                  unit="kg·m²"
                  min={0}
                  disabled={disabled}
                  description="Total rotational inertia about the primary shaft of the fixed and movable primary hardware. Excludes the engine and separately modelled flyweights; movable-sheave translating mass remains separate below."
                  onChange={(next) =>
                    onChange(withPrimaryRotatingHardwareInertia(value, next))
                  }
                />
              )}
              {componentFields('/inertias/primary/')}
              <Text fw={600}>Secondary</Text>
              {componentFields('/inertias/secondary/')}
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
              {componentFields('/contact/')}
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
                {mount === 'primary' && (
                  <CvtMeasurementPreview value={value} activePath={focusedPath} />
                )}
                {assembly.pulleys[mount].components.map((component, index) => (
                  <Stack key={`${index}-${component.kind}`} gap="md">
                    <Group>
                      <Badge variant="outline">{componentLabel(component.kind)}</Badge>
                    </Group>
                    {componentFields(`/pulleys/${mount}/components/${index}/`)}
                  </Stack>
                ))}
                {assembly.pulleys[mount].helical_coupling && (
                  <Stack>
                    <Text fw={600}>Helical coupling geometry</Text>
                    {componentFields(`/pulleys/${mount}/helical_coupling/`)}
                  </Stack>
                )}
              </Stack>
            </Accordion.Panel>
          </Accordion.Item>
        ))}
      </Accordion>
    </Stack>
  );
}
