import { useCallback, useEffect, useState, type ReactNode } from 'react';
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
} from '@mantine/core';
import { IconInfoCircle } from '@tabler/icons-react';
import { QuantityInput } from '@components/quantityInput/QuantityInput';
import {
  expandJsonPointerTemplate,
  getValueAtJsonPointer,
  setValueAtJsonPointer,
} from '@utils/jsonPointer';
import { BeltPicker } from './BeltPicker';
import { CvtPrimaryHardwarePreview, CvtPulleyPreview } from './CvtHardwarePreviews';
import { InitialTunePanel } from './InitialTunePanel';
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


function assemblyFindingPath(path: string): string {
  const normalized = path.replace(/\./g, '/');
  const marker = normalized.indexOf('/assembly/');
  if (marker >= 0) return normalized.slice(marker + '/assembly'.length);
  return normalized.replace(/^\/assembly/, '');
}

function relatedFieldPath(field: string, finding: string): boolean {
  const a = field.replace(/\/$/, '');
  const b = finding.replace(/\/$/, '');
  return a === b || a.startsWith(`${b}/`) || b.startsWith(`${a}/`);
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
  onSaveBlockChange,
  draftPathPrefix = '',
  enableInitialTune = false,
}: {
  value: CvtData;
  onChange: (value: CvtData) => void;
  fields: PhysicalField[];
  belts: PhysicalItem[];
  validation?: PhysicalValidation | null;
  disabled?: boolean;
  onLoadingChange?: (loading: boolean) => void;
  onSaveBlockChange?: (reason: string | null) => void;
  draftPathPrefix?: string;
  enableInitialTune?: boolean;
}) {
  const assembly = value.assembly;
  const [focusedPath, setFocusedPath] = useState<string | null>(null);
  const [openedCategories, setOpenedCategories] = useState<string[]>(['belt', 'geometry']);
  const focusPath = (path: string) => (focused: boolean) =>
    setFocusedPath((current) => focused ? path : current === path ? null : current);
  const primaryCoupled = primaryHasRelativeRotationCoupling(value);
  const changeAssembly = (next: CvtData['assembly']) =>
    onChange({ ...value, assembly: next });

  const entries = (prefix: string): Entry[] =>
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
      .filter(({ path }) => {
        if (isCanonicalPrimaryRadiusField(path)) return false;
        if (!primaryCoupled && isPrimaryRotationalInertiaField(path)) return false;
        if (isOrdinaryPrimaryTravelField(path, value)) return false;
        return typeof getValueAtJsonPointer(assembly, path) === 'number';
      });

  const findingTouches = useCallback((path: string) =>
    validation?.findings.some((finding) => {
      if (finding.severity !== 'error' || !finding.document_path) return false;
      const documentPath = assemblyFindingPath(finding.document_path);
      return relatedFieldPath(path, documentPath);
    }) ?? false, [validation]);

  const advancedHasError = (items: Entry[]) =>
    items.some(({ path }) => findingTouches(path));

  useEffect(() => {
    if (!validation?.findings.some((finding) => finding.severity === 'error')) return;
    const categories: Array<[string, string[]]> = [
      ['geometry', ['/geometry/']],
      ['inertias', ['/inertias/']],
      ['contact', ['/contact/']],
      ['primary', ['/pulleys/primary/']],
      ['secondary', ['/pulleys/secondary/']],
    ];
    const needed = categories
      .filter(([, prefixes]) => prefixes.some((prefix) => findingTouches(prefix)))
      .map(([category]) => category);
    if (needed.length)
      setOpenedCategories((current) => Array.from(new Set([...current, ...needed])));
  }, [validation, findingTouches]);

  useEffect(() => {
    if (!enableInitialTune) onSaveBlockChange?.(null);
    return () => onSaveBlockChange?.(null);
  }, [enableInitialTune, onSaveBlockChange]);

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
            draftKey={`cvt:${draftPathPrefix}${path}`}
            documentPath={draftPathPrefix ? `${draftPathPrefix}${path}` : undefined}
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
        ) : input;
      })}
    </SimpleGrid>
  );

  const groupedFields = (
    groups: Array<{ label?: string; prefix: string }>,
  ) => {
    const resolved = groups.map((group) => {
      const all = entries(group.prefix);
      return {
        ...group,
        basic: all.filter(({ field, path }) => !cvtFieldPresentation(field, path).advanced),
        advanced: all.filter(({ field, path }) => cvtFieldPresentation(field, path).advanced),
      };
    });
    const advanced = resolved.flatMap((group) => group.advanced);
    return (
      <Stack gap="lg">
        {resolved.map((group) => group.basic.length > 0 && (
          <Stack key={group.prefix} gap="sm">
            {group.label && <Badge variant="outline" w="fit-content">{group.label}</Badge>}
            {renderEntries(group.basic)}
          </Stack>
        ))}
        {advanced.length > 0 && (
          <AdvancedSection forceOpen={advancedHasError(advanced)}>
            {resolved.map((group) => group.advanced.length > 0 && (
              <Stack key={group.prefix} gap="sm">
                {group.label && <Text fw={600} size="sm">{group.label}</Text>}
                {renderEntries(group.advanced)}
              </Stack>
            ))}
          </AdvancedSection>
        )}
      </Stack>
    );
  };

  const pulleyGroups = (mount: 'primary' | 'secondary') => {
    const groups = assembly.pulleys[mount].components.map((component, index) => ({
      label: componentLabel(component.kind),
      prefix: `/pulleys/${mount}/components/${index}/`,
    }));
    if (assembly.pulleys[mount].helical_coupling)
      groups.push({
        label: 'Helical coupling geometry',
        prefix: `/pulleys/${mount}/helical_coupling/`,
      });
    return groups;
  };

  return (
    <Stack gap="lg">
      <Text size="sm" c="dimmed">
        Enter fixed hardware measurements here. Replaceable masses, springs,
        ramp placement, ramp shape and helix shape are adjusted in Tunes.
      </Text>
      <Accordion
        variant="separated"
        multiple
        value={openedCategories}
        onChange={setOpenedCategories}
      >
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
                unchanged and updates CINDER’s outer-belt radius from the new belt height.
              </Text>
            </Stack>
          </Accordion.Panel>
        </Accordion.Item>

        <Accordion.Item value="geometry">
          <Accordion.Control>Pulley geometry & travel</Accordion.Control>
          <Accordion.Panel>
            <Stack gap="lg">
              <CvtPulleyPreview value={value} activePath={focusedPath} />
              <div
                tabIndex={0}
                onFocus={() => setFocusedPath('/geometry/sheave_half_angle_rad')}
                onBlur={() => setFocusedPath((current) =>
                  current === '/geometry/sheave_half_angle_rad' ? null : current
                )}
              >
                <QuantityInput
                  scope="hardware"
                  label="Sheave half-angle · set by belt"
                  value={value.belt.data.half_angle_rad}
                  unit="deg"
                  disabled
                  onChange={() => undefined}
                />
              </div>
              <QuantityInput
                scope="hardware"
                draftKey={`cvt:${draftPathPrefix}:shaft-radius`}
                label="Primary shaft radius"
                value={primaryShaftRadius(value)}
                unit="mm"
                min={0}
                disabled={disabled}
                description="Outside radius of the shaft or sleeve supporting the belt at low ratio, measured from the primary shaft centreline. This is not the bore radius or cord-line radius."
                onChange={(next) => onChange(withPrimaryShaftRadius(value, next))}
                onFocusChange={focusPath('@primary-shaft-radius')}
              />
              {groupedFields([{ prefix: '/geometry/' }])}
            </Stack>
          </Accordion.Panel>
        </Accordion.Item>

        <Accordion.Item value="inertias">
          <Accordion.Control>CVT masses & inertias</Accordion.Control>
          <Accordion.Panel>
            <Stack gap="lg">
              {!primaryCoupled && (
                <QuantityInput
                  scope="hardware"
                  draftKey={`cvt:${draftPathPrefix}:primary-inertia`}
                  label="Primary rotating hardware inertia"
                  value={primaryRotatingHardwareInertia(value)}
                  unit="kg·m²"
                  min={0}
                  disabled={disabled}
                  description="Total rotational inertia about the primary shaft of the fixed and movable primary hardware. Excludes the engine and separately modelled flyweights; movable-sheave translating mass remains separate."
                  onChange={(next) => onChange(withPrimaryRotatingHardwareInertia(value, next))}
                />
              )}
              {groupedFields([
                { label: 'Primary', prefix: '/inertias/primary/' },
                { label: 'Secondary', prefix: '/inertias/secondary/' },
              ])}
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
              {groupedFields([{ prefix: '/contact/' }])}
            </Stack>
          </Accordion.Panel>
        </Accordion.Item>

        <Accordion.Item value="primary">
          <Accordion.Control>Primary mounting geometry</Accordion.Control>
          <Accordion.Panel>
            <Stack gap="lg">
              <CvtPrimaryHardwarePreview value={value} activePath={focusedPath} />
              {groupedFields(pulleyGroups('primary'))}
            </Stack>
          </Accordion.Panel>
        </Accordion.Item>

        <Accordion.Item value="secondary">
          <Accordion.Control>Secondary mounting geometry</Accordion.Control>
          <Accordion.Panel>
            {groupedFields(pulleyGroups('secondary'))}
          </Accordion.Panel>
        </Accordion.Item>

        {enableInitialTune && (
          <Accordion.Item value="initial-tune">
            <Accordion.Control>Initial tune</Accordion.Control>
            <Accordion.Panel>
              <InitialTunePanel
                value={value}
                onChange={onChange}
                disabled={disabled}
                onSaveBlockChange={onSaveBlockChange}
              />
            </Accordion.Panel>
          </Accordion.Item>
        )}
      </Accordion>
    </Stack>
  );
}
