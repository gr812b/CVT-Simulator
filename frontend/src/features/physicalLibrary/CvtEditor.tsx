import { useCallback, useEffect, useState, type ReactNode } from 'react';
import {
  Accordion,
  Alert,
  Badge,
  Box,
  Checkbox,
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
import { BeltPicker } from './BeltPicker';
import { CvtPrimaryHardwarePreview, CvtPulleyPreview } from './CvtHardwarePreviews';
import { InitialTunePanel } from './InitialTunePanel';
import {
  cvtFieldPresentation,
  isCanonicalPrimaryRadiusField,
  isCvtHardwareField,
  isOrdinaryPrimaryTravelField,
  isPrimaryRotationalInertiaField,
  primaryBeltContactTravel,
  primaryFreeTravel,
  primaryGrooveFitsBelt,
  primaryGrooveWidth,
  primaryHasRelativeRotationCoupling,
  primaryRotatingHardwareInertia,
  primaryShaftRadius,
  withBeltPreservingPrimaryShaft,
  withPrimaryGrooveWidth,
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
            <Text size="xs" c="dimmed">
              Coordinate mappings, orientation signs and numerical construction settings. The descriptions below explain when each value should be changed.
            </Text>
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
  const [openedCategories, setOpenedCategories] = useState<string[]>(['geometry']);
  const focusPath = (path: string) => (focused: boolean) => {
    if (focused) setFocusedPath(path);
  };
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
          field.path !== '/geometry/sheave_half_angle_rad' &&
          field.path !== '/geometry/deadzone_shift_m' &&
          field.path !== '/geometry/max_shift_m',
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
    changeAssembly(setValueAtJsonPointer(assembly, path, next));
  };

  const renderEntries = (items: Entry[]) => (
    <SimpleGrid cols={{ base: 1, sm: 2 }}>
      {items.map(({ field, path }) => {
        const current = getValueAtJsonPointer(assembly, path);
        if (typeof current !== 'number') return null;
        const presentation = cvtFieldPresentation(field, path);
        const label = fieldLabel(field, path);
        return (
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
            description={presentation.description}
            min={field.minimum ?? undefined}
            max={field.maximum ?? undefined}
            integer={field.integer}
            onFocusChange={focusPath(path)}
          />
        );
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
        <Accordion.Item value="geometry">
          <Accordion.Control>Pulley geometry & travel</Accordion.Control>
          <Accordion.Panel>
            <SimpleGrid cols={{ base: 1, lg: 2 }} spacing="xl" verticalSpacing="lg">
              <Stack gap="lg">
                <Stack gap="sm">
                  <Text fw={600}>Reusable belt</Text>
                  <BeltPicker
                    value={value.belt}
                    onChange={(belt) => onChange(withBeltPreservingPrimaryShaft(value, belt))}
                    items={belts}
                    disabled={disabled}
                    onLoadingChange={onLoadingChange}
                  />
                  <Text size="xs" c="dimmed">
                    The selected belt sets the inner width and sheave angle. Changing belts keeps the primary shaft radius and fully-open groove width fixed, then recomputes the free travel to first contact.
                  </Text>
                </Stack>

                {!primaryGrooveFitsBelt(value) && (
                  <Alert color="red" title="Selected belt is too wide">
                    Increase the primary groove width or choose a belt with a smaller inner width. The groove must be at least as wide as the belt at its inner surface.
                  </Alert>
                )}

                <QuantityInput
                  scope="hardware"
                  draftKey={`cvt:${draftPathPrefix}:groove-width`}
                  label="Primary groove width"
                  value={primaryGrooveWidth(value)}
                  unit="mm"
                  min={primaryBeltContactTravel(value)}
                  disabled={disabled}
                  description="With the primary fully open, measure the axial face-to-face groove width at the shaft/sleeve outer radius. This CAD-friendly dimension equals total primary travel and must be at least the selected belt inner width."
                  onChange={(next) => onChange(withPrimaryGrooveWidth(value, next))}
                  onFocusChange={focusPath('@primary-groove-width')}
                />

                <SimpleGrid cols={{ base: 1, sm: 2 }}>
                  <div
                    tabIndex={0}
                    onFocus={() => setFocusedPath('@primary-free-travel')}
                  >
                    <QuantityInput
                      scope="hardware"
                      label="Free travel before belt contact"
                      value={Math.max(0, primaryFreeTravel(value))}
                      unit="mm"
                      disabled
                      description="Derived as the fully-open groove width minus the selected belt inner (bottom) width."
                      onChange={() => undefined}
                    />
                  </div>
                  <div
                    tabIndex={0}
                    onFocus={() => setFocusedPath('@primary-belt-contact-travel')}
                  >
                    <QuantityInput
                      scope="hardware"
                      label="Primary travel · set by belt"
                      value={primaryBeltContactTravel(value)}
                      unit="mm"
                      disabled
                      description="Travel after first belt contact; this is equal to the selected belt inner (bottom) width."
                      onChange={() => undefined}
                    />
                  </div>
                </SimpleGrid>
                <Text size="xs" c="dimmed">
                  Total travel from fully open to fully closed is the groove width: free travel to first contact plus the primary travel set by the selected belt.
                </Text>

                <div
                  tabIndex={0}
                  onFocus={() => setFocusedPath('/geometry/sheave_half_angle_rad')}
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

              <Box style={{ position: 'sticky', top: 88, alignSelf: 'start' }}>
                <CvtPulleyPreview value={value} activePath={focusedPath} />
              </Box>
            </SimpleGrid>
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
