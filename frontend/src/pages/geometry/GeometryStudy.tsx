import { libraryOptions } from '../../features/physicalLibrary/libraryOptions';
import { lazy, Suspense, useEffect, useState } from 'react';
import {
  Accordion,
  Alert,
  Badge,
  Checkbox,
  Container,
  Group,
  Loader,
  Paper,
  Select,
  Slider,
  SimpleGrid,
  Stack,
  Table,
  Text,
  Title,
} from '@mantine/core';
import { ActionButton as Button } from '@components/button/ActionButton';
import { QuantityInput } from '@components/quantityInput/QuantityInput';
import { QuantityValidationContext } from '@components/quantityInput/validation';
import { api, dataOrThrow } from '@api/transport';
import type { components } from '@api/generated/backend';
import {
  getPhysical,
  resolveBeltSection,
  listPhysical,
  type PhysicalItem,
} from '../../features/physicalLibrary/api';
import { message } from '../../features/experiments/api';
import { useAuth } from '@contexts/AuthContext';
import {
  formatPreferredProjectedQuantity,
  formatPreferredQuantity,
  isQuantityDimension,
  normalizeUnitPreferences,
  preferredProjectedDisplayUnit,
  siToDisplay,
  type DisplayUnit,
} from '@utils/units';

const GeometryScene = lazy(
  () => import('@components/scene3DViewer/GeometryScene'),
);

type Inputs = components['schemas']['SimpleGeometryRequest'];
type Result = components['schemas']['SimpleGeometryResponse'];

export function GeometryStudy() {
  const { unitPreferences } = useAuth();
  const preferences = normalizeUnitPreferences(unitPreferences);
  const [value, setValue] = useState<Inputs | null>(null);
  const [belts, setBelts] = useState<PhysicalItem[]>([]);
  const [beltId, setBeltId] = useState<string | null>(null);
  const [result, setResult] = useState<Result | null>(null);
  const [frameIndex, setFrameIndex] = useState(0);
  const [resultKey, setResultKey] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [invalid, setInvalid] = useState(new Set<string>());
  const [retry, setRetry] = useState(0);
  const [sectionError, setSectionError] = useState<string | null>(null);
  const measuredSection =
    value?.section_mode === 'measured'
      ? JSON.stringify({
          outer_width_m: value.belt_outer_width_m,
          inner_width_m: value.measured_inner_width_m,
          height_m: value.belt_height_m,
        })
      : null;
  useEffect(() => {
    const key = 'geometry-belt-section';
    const clear = () =>
      setInvalid((previous) => {
        const next = new Set(previous);
        next.delete(key);
        return next;
      });
    setSectionError(null);
    if (!measuredSection) {
      clear();
      return;
    }
    const controller = new AbortController();
    setInvalid((previous) => new Set(previous).add(key));
    const timer = window.setTimeout(() => {
      void resolveBeltSection(JSON.parse(measuredSection), controller.signal)
        .then((section) => {
          if (controller.signal.aborted) return;
          setValue(
            (previous) =>
              previous && {
                ...previous,
                sheave_half_angle_rad: section.half_angle_rad,
              },
          );
          clear();
        })
        .catch((cause: unknown) => {
          if (!controller.signal.aborted) setSectionError(message(cause));
        });
    }, 180);
    return () => {
      window.clearTimeout(timer);
      controller.abort();
      clear();
    };
  }, [measuredSection]);
  useEffect(() => {
    let disposed = false;
    setBusy(true);
    setError(null);
    void Promise.all([
      api.GET('/api/v1/studies/geometry/template').then(dataOrThrow),
      listPhysical('belts', 'all'),
    ])
      .then(([template, items]) => {
        if (!disposed) {
          setValue(template);
          setBelts(items);
        }
      })
      .catch((cause) => {
        if (!disposed) setError(message(cause));
      })
      .finally(() => {
        if (!disposed) setBusy(false);
      });
    return () => {
      disposed = true;
    };
  }, [retry]);
  const patch = (next: Partial<Inputs>) => {
    if (value) {
      setValue({ ...value, ...next });
      if (
        Object.keys(next).some(
          (key) =>
            key.startsWith('belt_') ||
            key === 'measured_inner_width_m' ||
            key === 'sheave_half_angle_rad' ||
            key === 'section_mode' ||
            key === 'cord_depth_from_outer_m',
        )
      )
        setBeltId(null);
    }
  };
  const chooseBelt = async (id: string) => {
    if (!value) return;
    setBusy(true);
    setError(null);
    try {
      const detail = await getPhysical('belts', id);
      if (detail.document.kind !== 'belts') return;
      const b = detail.document.data;
      setValue({
        ...value,
        section_mode: 'measured',
        belt_height_m: b.height_m,
        belt_outer_width_m: b.outer_width_m,
        belt_outer_length_m: b.outer_length_m,
        measured_inner_width_m: b.inner_width_m,
        cord_depth_from_outer_m: b.cord_depth_from_outer_m,
        sheave_half_angle_rad: b.half_angle_rad,
        active_travel_limit_m: null,
      });
      setBeltId(id);
    } catch (cause) {
      setError(message(cause));
    } finally {
      setBusy(false);
    }
  };
  const run = async () => {
    if (!value) return;
    setBusy(true);
    setError(null);
    try {
      const next = dataOrThrow(
        await api.POST('/api/v1/studies/geometry/simple', { body: value }),
      );
      setResult(next);
      setFrameIndex(0);
      setResultKey(JSON.stringify(value));
    } catch (cause) {
      setError(message(cause));
    } finally {
      setBusy(false);
    }
  };
  const field = (
    key: keyof Inputs,
    label: string,
    unit = 'mm',
    minimum = Number.MIN_VALUE,
  ) => (
    <QuantityInput
      key={key}
      scope="hardware"
      label={label}
      unit={unit}
      min={minimum}
      value={typeof value?.[key] === 'number' ? (value[key] as number) : 0}
      disabled={
        (key === 'sheave_half_angle_rad' &&
          value?.section_mode === 'measured') ||
        (Boolean(beltId) &&
          [
            'belt_outer_length_m',
            'belt_outer_width_m',
            'belt_height_m',
            'sheave_half_angle_rad',
            'measured_inner_width_m',
            'cord_depth_from_outer_m',
          ].includes(key))
      }
      description={
        beltId && key === 'sheave_half_angle_rad'
          ? 'CINDER matches the selected belt’s half-angle.'
          : undefined
      }
      onChange={(next) => patch({ [key]: next })}
    />
  );
  return (
    <Container size="lg" py="lg">
      <Stack gap="lg">
        <Title order={1}>Geometry study</Title>
        <Text c="dimmed">
          Choose a belt and starting pulley radii. CINDER resolves the centre
          distance, ratio range and geometry through the shift.
        </Text>
        {sectionError && (
          <Alert color="red" title="Check the belt section">
            {sectionError}
          </Alert>
        )}
        {error && (
          <Alert color="red" title="Check the geometry inputs">
            {error}
            {!value && (
              <Button onClick={() => setRetry((x) => x + 1)}>Try again</Button>
            )}
          </Alert>
        )}
        {!value ? (
          busy && <Loader />
        ) : (
          <QuantityValidationContext.Provider value={setInvalid}>
            <Paper withBorder p="lg">
              <Stack>
                <Select
                  label="Start from a catalog belt"
                  searchable
                  clearable
                  value={beltId}
                  data={libraryOptions(belts, (item) => item.id)}
                  onChange={(id) =>
                    id ? void chooseBelt(id) : setBeltId(null)
                  }
                  disabled={busy}
                />
                <fieldset
                  disabled={busy}
                  style={{ border: 0, margin: 0, padding: 0, minWidth: 0 }}
                >
                  <Stack>
                    <Select
                      label="Belt section"
                      allowDeselect={false}
                      value={value.section_mode ?? 'matching_angle'}
                      disabled={Boolean(beltId)}
                      data={[
                        {
                          value: 'matching_angle',
                          label:
                            'Match the sheave angle — calculate bottom width',
                        },
                        {
                          value: 'measured',
                          label: 'Use measured belt widths',
                        },
                      ]}
                      onChange={(mode) =>
                        patch({
                          section_mode:
                            mode === 'measured' ? 'measured' : 'matching_angle',
                        })
                      }
                    />
                    <Text size="sm" c="dimmed">
                      {value.section_mode === 'measured'
                        ? 'The sheave angle is calculated from the measured belt section.'
                        : 'Bottom width is derived from top width, height and sheave half-angle; there is no fourth independent dimension.'}
                    </Text>
                    <SimpleGrid cols={{ base: 1, sm: 2 }}>
                      {field('belt_outer_length_m', 'Belt outer circumference')}
                      {field('belt_outer_width_m', 'Belt top width')}
                      {field('belt_height_m', 'Belt height')}
                      {field(
                        'sheave_half_angle_rad',
                        'Sheave half-angle',
                        'deg',
                      )}
                      {value.section_mode === 'measured' &&
                        field(
                          'measured_inner_width_m',
                          'Measured belt bottom width',
                        )}
                      {field(
                        'cord_depth_from_outer_m',
                        'Cord depth from outer face',
                        'mm',
                        0,
                      )}
                      {field(
                        'primary_outer_radius_at_zero_shift_m',
                        'Primary starting outer belt radius',
                      )}
                      {field(
                        'secondary_outer_radius_at_zero_shift_m',
                        'Secondary starting outer belt radius',
                      )}
                    </SimpleGrid>
                    <Accordion variant="separated">
                      <Accordion.Item value="advanced">
                        <Accordion.Control>
                          Advanced travel limits
                        </Accordion.Control>
                        <Accordion.Panel>
                          <Stack>
                            {field(
                              'deadzone_shift_m',
                              'Primary deadzone travel',
                              'mm',
                              0,
                            )}
                            <Checkbox
                              label="Use a shorter mechanical travel limit"
                              checked={value.active_travel_limit_m != null}
                              onChange={(e) =>
                                patch({
                                  active_travel_limit_m: e.currentTarget.checked
                                    ? 0.005
                                    : null,
                                })
                              }
                            />
                            {value.active_travel_limit_m != null &&
                              field(
                                'active_travel_limit_m',
                                'Maximum active axial travel',
                              )}
                          </Stack>
                        </Accordion.Panel>
                      </Accordion.Item>
                    </Accordion>
                    <Text size="sm" c="dimmed">
                      Full active axial travel defaults to the belt bottom
                      width. Total shift includes the deadzone. This is a design
                      assumption, not a guarantee of available hardware travel.
                    </Text>
                    <Button
                      loading={busy}
                      disabledReason={
                        invalid.size
                          ? 'Correct the highlighted geometry inputs.'
                          : undefined
                      }
                      onClick={() => void run()}
                    >
                      Run geometry study
                    </Button>
                  </Stack>
                </fieldset>
              </Stack>
            </Paper>
            {result && (
              <>
                <Group>
                  <Title order={2}>Resolved geometry</Title>
                  {resultKey !== JSON.stringify(value) && (
                    <Badge color="yellow">
                      Inputs changed · rerun to update
                    </Badge>
                  )}
                </Group>
                <Paper withBorder p="lg">
                  <Stack>
                    <Title order={3}>Geometry preview</Title>
                    <Text size="sm" c="dimmed">
                      Resolved belt and sheave geometry. Hubs and shafts are
                      illustrative. Drag to rotate; move through the sampled
                      shift range below.
                    </Text>
                    <div style={{ height: 400 }}>
                      <Suspense fallback={<Loader />}>
                        <GeometryScene
                          preview={result.scene}
                          frameIndex={frameIndex}
                        />
                      </Suspense>
                    </div>
                    <Text size="sm">
                      Shift:{' '}
                      {formatPreferredQuantity(
                        result.scene.frames[frameIndex]?.shift_m ?? 0,
                        'length',
                        'hardware',
                        preferences,
                        'mm',
                        2,
                      )}
                    </Text>
                    <Slider
                      thumbLabel="Geometry preview shift"
                      thumbValueText={(i) =>
                        formatPreferredQuantity(
                          result.scene.frames[i]?.shift_m ?? 0,
                          'length',
                          'hardware',
                          preferences,
                          'mm',
                          2,
                        )
                      }
                      min={0}
                      max={result.scene.frames.length - 1}
                      step={1}
                      value={frameIndex}
                      onChange={setFrameIndex}
                      label={(i) =>
                        formatPreferredQuantity(
                          result.scene.frames[i]?.shift_m ?? 0,
                          'length',
                          'hardware',
                          preferences,
                          'mm',
                          2,
                        )
                      }
                    />
                  </Stack>
                </Paper>
                <Paper withBorder p="lg">
                  <SimpleGrid cols={{ base: 2, sm: 3 }}>
                    <div>
                      <Text size="xs" c="dimmed">
                        Belt bottom width
                      </Text>
                      <Text fw={600}>
                        {formatPreferredQuantity(
                          result.resolved_context.belt.inner_width_m,
                          'length',
                          'hardware',
                          preferences,
                          'mm',
                          3,
                        )}
                      </Text>
                    </div>
                    <div>
                      <Text size="xs" c="dimmed">
                        Total maximum shift
                      </Text>
                      <Text fw={600}>
                        {formatPreferredQuantity(
                          result.resolved_context.max_shift_m,
                          'length',
                          'hardware',
                          preferences,
                          'mm',
                          3,
                        )}
                      </Text>
                    </div>
                    {result.study.summary.scalars.map((item) => (
                      <div key={item.key}>
                        <Text size="xs" c="dimmed">
                          {item.label}
                        </Text>
                        <Text fw={600}>
                          {item.value === null
                            ? '—'
                            : formatPreferredProjectedQuantity(
                                item.value,
                                item.dimension,
                                item.canonical_unit,
                                'hardware',
                                preferences,
                                5,
                              )}
                        </Text>
                      </div>
                    ))}
                  </SimpleGrid>
                </Paper>
                <Alert
                  color={
                    result.study.feasibility.is_feasible ? 'teal' : 'yellow'
                  }
                  title={
                    result.study.feasibility.is_feasible
                      ? 'Geometry is feasible'
                      : 'Geometry needs attention'
                  }
                >
                  {result.study.feasibility.findings.length
                    ? result.study.feasibility.findings.map(
                        (finding, index) => (
                          <Text size="sm" key={index}>
                            {finding.message}
                          </Text>
                        ),
                      )
                    : 'CINDER found no geometry feasibility errors.'}
                </Alert>
                <Accordion variant="separated">
                  <Accordion.Item value="path">
                    <Accordion.Control>Sampled geometry path</Accordion.Control>
                    <Accordion.Panel>
                      <Table.ScrollContainer minWidth={600}>
                        <Table>
                          <Table.Thead>
                            <Table.Tr>
                              {result.study.path.columns.map((column) => (
                                <Table.Th key={column.key}>
                                  {column.label} ({preferredProjectedDisplayUnit(
                                    column.dimension,
                                    column.canonical_unit,
                                    'hardware',
                                    preferences,
                                  )})
                                </Table.Th>
                              ))}
                            </Table.Tr>
                          </Table.Thead>
                          <Table.Tbody>
                            {Array.from(
                              {
                                length: Math.min(
                                  result.study.path.shape[0] ?? 0,
                                  11,
                                ),
                              },
                              (_, i) =>
                                Math.round(
                                  (i *
                                    ((result.study.path.shape[0] ?? 1) - 1)) /
                                    10,
                                ),
                            ).map((row) => (
                              <Table.Tr key={row}>
                                {result.study.path.columns.map((column) => {
                                  const v = Array.isArray(column.values)
                                    ? column.values[row]
                                    : null;
                                  return (
                                    <Table.Td key={column.key}>
                                      {typeof v === 'number'
                                        ? (isQuantityDimension(column.dimension)
                                            ? siToDisplay(
                                                v,
                                                preferredProjectedDisplayUnit(
                                                  column.dimension,
                                                  column.canonical_unit,
                                                  'hardware',
                                                  preferences,
                                                ) as DisplayUnit,
                                              )
                                            : v
                                          ).toPrecision(5)
                                        : '—'}
                                    </Table.Td>
                                  );
                                })}
                              </Table.Tr>
                            ))}
                          </Table.Tbody>
                        </Table>
                      </Table.ScrollContainer>
                    </Accordion.Panel>
                  </Accordion.Item>
                </Accordion>
              </>
            )}
          </QuantityValidationContext.Provider>
        )}
      </Stack>
    </Container>
  );
}
