import { useEffect, useRef, useState } from 'react';
import {
  Alert,
  Badge,
  Group,
  Paper,
  ScrollArea,
  Select,
  SimpleGrid,
  Stack,
  Text,
  TextInput,
} from '@mantine/core';
import { ActionButton as Button } from '@components/button/ActionButton';
import {
  IconArrowDown,
  IconArrowUp,
  IconCopy,
  IconTrash,
} from '@tabler/icons-react';
import { QuantityInput } from '@components/quantityInput/QuantityInput';
import {
  message,
  resolveRoad,
  type ExperimentMetadata,
  type Road,
  type RoadFeature,
  type RoadPoint,
  type RoadResolution,
} from './api';

type Section = RoadResolution['sections'][number];
type Selection = { featureId: string; index: number };

function FeatureInputs({
  value,
  onChange,
}: {
  value: RoadFeature;
  onChange: (next: RoadFeature) => void;
}) {
  return (
    <Stack gap="sm">
      <TextInput
        label="Section name"
        value={value.name ?? ''}
        maxLength={120}
        onChange={(event) =>
          onChange({ ...value, name: event.currentTarget.value })
        }
      />
      <SimpleGrid cols={{ base: 1, xs: 2 }}>
        {'length_m' in value && (
          <QuantityInput
            label="Section length"
            unit="m"
            scale={1}
            min={0.01}
            value={value.length_m}
            onChange={(length_m) => onChange({ ...value, length_m })}
          />
        )}
        {'rise_m' in value && (
          <QuantityInput
            label="Elevation change"
            unit="m"
            scale={1}
            value={value.rise_m}
            onChange={(rise_m) => onChange({ ...value, rise_m })}
          />
        )}
        {'height_m' in value && (
          <QuantityInput
            label="Feature height"
            unit="m"
            scale={1}
            min={0.001}
            value={value.height_m}
            onChange={(height_m) => onChange({ ...value, height_m })}
          />
        )}
        {value.kind === 'whoops' && (
          <>
            <QuantityInput
              label="Whoops spacing"
              unit="m"
              scale={1}
              min={0.01}
              value={value.spacing_m}
              onChange={(spacing_m) => onChange({ ...value, spacing_m })}
            />
            <QuantityInput
              label="Whoops count"
              integer
              min={1}
              max={32}
              value={value.count}
              onChange={(count) => onChange({ ...value, count })}
            />
          </>
        )}
        {'shape' in value && (
          <Select
            label="Feature shape"
            data={[
              { value: 'rounded', label: 'Rounded · 8 segments' },
              { value: 'triangular', label: 'Triangular · 2 segments' },
            ]}
            value={value.shape ?? 'rounded'}
            onChange={(shape) =>
              onChange({
                ...value,
                shape: shape === 'triangular' ? 'triangular' : 'rounded',
              })
            }
          />
        )}
      </SimpleGrid>
      {value.kind === 'points' && (
        <Text size="sm" c="dimmed">
          Custom points. Select a handle on the road to edit exact coordinates
          below.
        </Text>
      )}
    </Stack>
  );
}

export function RoadEditor({
  value,
  metadata,
  onChange,
  onValidityChange,
}: {
  value: Road;
  metadata: ExperimentMetadata;
  onChange: (road: Road) => void;
  onValidityChange: (valid: boolean) => void;
}) {
  const [resolution, setResolution] = useState<RoadResolution | null>(null);
  const [resolvedKey, setResolvedKey] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [selection, setSelection] = useState<Selection | null>(null);
  const [sectionId, setSectionId] = useState(value.features[0].id);
  const [templateId, setTemplateId] = useState(
    metadata.feature_templates[0].id,
  );
  const [drag, setDrag] = useState<{
    selection: Selection;
    point: RoadPoint;
  } | null>(null);
  const svg = useRef<SVGSVGElement>(null);
  const key = JSON.stringify(value);
  const fresh = key === resolvedKey && !error;
  useEffect(() => {
    const controller = new AbortController();
    const timer = setTimeout(() => {
      void resolveRoad(value, controller.signal)
        .then((next) => {
          setResolution(next);
          setResolvedKey(key);
          setError(null);
        })
        .catch((cause) => {
          if (!controller.signal.aborted) setError(message(cause));
        });
    }, 180);
    return () => {
      clearTimeout(timer);
      controller.abort();
    };
  }, [key, value]);
  useEffect(() => {
    onValidityChange(fresh);
  }, [fresh, onValidityChange]);
  const activeFeature =
    value.features.find((feature) => feature.id === sectionId) ??
    value.features[0];
  const activeSection = resolution?.sections.find(
    (section) => section.feature_id === activeFeature.id,
  );
  const resolvedSelection =
    selection &&
    resolution?.sections.find(
      (section) => section.feature_id === selection.featureId,
    );
  const selectedFeature =
    selection &&
    value.features.find((feature) => feature.id === selection.featureId);
  const selectedSection =
    resolvedSelection && selectedFeature?.kind === 'points'
      ? { ...resolvedSelection, points: selectedFeature.points }
      : resolvedSelection;
  const selectedPoint =
    selectedSection && selectedSection.points[selection!.index];
  const elevationRange = resolution
    ? resolution.maximum_elevation_m - resolution.minimum_elevation_m
    : 0;
  const elevationPadding =
    elevationRange > 0 ? Math.max(0.1, elevationRange * 0.2) : 1;
  const minElevation = resolution
    ? Math.min(0, resolution.minimum_elevation_m) - elevationPadding
    : -1;
  const maxElevation = resolution
    ? Math.max(0, resolution.maximum_elevation_m) + elevationPadding
    : 2;
  const length = Math.max(resolution?.length_m ?? 20, 1);
  const x = (distance: number) => 58 + (distance / length) * 810;
  const y = (elevation: number) =>
    254 - ((elevation - minElevation) / (maxElevation - minElevation)) * 222;
  const updateFeature = (feature: RoadFeature) =>
    onChange({
      ...value,
      features: value.features.map((item) =>
        item.id === feature.id ? feature : item,
      ),
    });
  const replacePoints = (section: Section, points: RoadPoint[]) => {
    const feature = value.features.find(
      (item) => item.id === section.feature_id,
    )!;
    updateFeature({
      id: feature.id,
      name: feature.name,
      kind: 'points',
      points,
    });
  };
  const changePoint = (selected: Selection, next: RoadPoint) => {
    const resolved = resolution?.sections.find(
      (item) => item.feature_id === selected.featureId,
    );
    const feature = value.features.find(
      (item) => item.id === selected.featureId,
    );
    const section =
      resolved && feature?.kind === 'points'
        ? { ...resolved, points: feature.points }
        : resolved;
    if (!section || selected.index === 0) return;
    replacePoints(
      section,
      section.points.map((point, index) =>
        index === selected.index ? next : point,
      ),
    );
  };
  const boundedPoint = (section: Section, index: number, point: RoadPoint) => ({
    distance_m: Math.max(
      section.points[index - 1].distance_m + 0.01,
      Math.min(
        section.points[index + 1]?.distance_m - 0.01 ||
          metadata.limits.max_distance_m,
        point.distance_m,
      ),
    ),
    elevation_m: point.elevation_m,
  });
  const pointerPoint = (
    clientX: number,
    clientY: number,
    selected: Selection,
  ) => {
    const section = resolution!.sections.find(
      (item) => item.feature_id === selected.featureId,
    )!;
    const matrix = svg.current!.getScreenCTM();
    if (!matrix) return section.points[selected.index];
    const point = new DOMPoint(clientX, clientY).matrixTransform(
      matrix.inverse(),
    );
    return boundedPoint(section, selected.index, {
      distance_m: Number(
        (((point.x - 58) / 810) * length - section.start_distance_m).toFixed(3),
      ),
      elevation_m: Number(
        (
          minElevation +
          ((254 - point.y) / 222) * (maxElevation - minElevation) -
          section.start_elevation_m
        ).toFixed(3),
      ),
    });
  };
  return (
    <Stack>
      <Alert color="blue" title="Grade-only road model">
        Distance is travel along the road. Features change road load—not
        suspension motion, tire lift, or jumps. The straight segments below are
        the exact profile used by the solver.
      </Alert>
      <Group justify="space-between">
        <Text fw={700}>Road profile</Text>
        <Badge variant="light" color={fresh ? 'teal' : 'yellow'}>
          {fresh ? 'Preview up to date' : 'Preview needs refresh'}
        </Badge>
      </Group>
      {error && (
        <Alert color="red" role="alert">
          {error}
        </Alert>
      )}
      <Paper withBorder p="xs" radius="md">
        <ScrollArea type="auto" offsetScrollbars>
          <div style={{ minWidth: 900 }}>
            <svg
              ref={svg}
              viewBox="0 0 900 300"
              width="100%"
              role="group"
              aria-label="Road elevation editor"
              style={{ display: 'block', touchAction: 'pan-x' }}
            >
              <line
                x1="58"
                y1="254"
                x2="868"
                y2="254"
                stroke="var(--mantine-color-default-border)"
              />
              {[0, 0.25, 0.5, 0.75, 1].map((tick) => (
                <g key={tick}>
                  <line
                    x1={x(tick * length)}
                    x2={x(tick * length)}
                    y1="32"
                    y2="254"
                    stroke="var(--mantine-color-default-border)"
                    strokeDasharray="3 5"
                  />
                  <text
                    x={x(tick * length)}
                    y="273"
                    textAnchor="middle"
                    fill="var(--mantine-color-dimmed)"
                    fontSize="12"
                  >
                    {(tick * length).toFixed(1)}
                  </text>
                </g>
              ))}
              <text
                x="465"
                y="294"
                textAnchor="middle"
                fill="var(--mantine-color-dimmed)"
                fontSize="12"
              >
                Road distance (m)
              </text>
              <text
                x="12"
                y="22"
                fill="var(--mantine-color-dimmed)"
                fontSize="12"
              >
                Elevation (m)
              </text>
              <text
                x="52"
                y="40"
                textAnchor="end"
                fill="var(--mantine-color-dimmed)"
                fontSize="12"
              >
                {maxElevation.toFixed(1)}
              </text>
              <text
                x="52"
                y="250"
                textAnchor="end"
                fill="var(--mantine-color-dimmed)"
                fontSize="12"
              >
                {minElevation.toFixed(1)}
              </text>
              {resolution?.sections.map((section) => (
                <g key={section.feature_id}>
                  <polyline
                    points={section.points
                      .map(
                        (point) =>
                          `${x(section.start_distance_m + point.distance_m)},${y(section.start_elevation_m + point.elevation_m)}`,
                      )
                      .join(' ')}
                    fill="none"
                    stroke={
                      section.feature_id === activeFeature.id
                        ? 'var(--mantine-color-red-4)'
                        : 'var(--mantine-color-dimmed)'
                    }
                    strokeWidth="3"
                  />
                  {section.points.map((point, index) => {
                    const selected = { featureId: section.feature_id, index };
                    const moving =
                      drag?.selection.featureId === selected.featureId &&
                      drag.selection.index === index
                        ? drag.point
                        : point;
                    return (
                      <circle
                        key={index}
                        cx={x(section.start_distance_m + moving.distance_m)}
                        cy={y(section.start_elevation_m + moving.elevation_m)}
                        r={
                          selection?.featureId === selected.featureId &&
                          selection.index === index
                            ? 8
                            : 5
                        }
                        fill="var(--mantine-color-body)"
                        stroke="var(--mantine-color-red-4)"
                        strokeWidth="2"
                        tabIndex={0}
                        role="button"
                        aria-label={`Section ${value.features.findIndex((f) => f.id === section.feature_id) + 1}, point ${index + 1}: ${point.distance_m.toFixed(2)} m, elevation ${point.elevation_m.toFixed(2)} m`}
                        style={{
                          cursor: index && fresh ? 'grab' : 'pointer',
                          outlineOffset: 3,
                          touchAction: 'none',
                        }}
                        onFocus={() => {
                          setSelection(selected);
                          setSectionId(section.feature_id);
                        }}
                        onPointerDown={(event) => {
                          setSelection(selected);
                          setSectionId(section.feature_id);
                          if (index && fresh) {
                            event.currentTarget.setPointerCapture(
                              event.pointerId,
                            );
                            setDrag({ selection: selected, point });
                          }
                        }}
                        onPointerMove={(event) => {
                          if (drag)
                            setDrag({
                              selection: drag.selection,
                              point: pointerPoint(
                                event.clientX,
                                event.clientY,
                                drag.selection,
                              ),
                            });
                        }}
                        onPointerUp={(event) => {
                          if (drag) {
                            changePoint(
                              drag.selection,
                              pointerPoint(
                                event.clientX,
                                event.clientY,
                                drag.selection,
                              ),
                            );
                            setDrag(null);
                          }
                        }}
                        onPointerCancel={() => setDrag(null)}
                        onKeyDown={(event) => {
                          if (
                            !index ||
                            !fresh ||
                            ![
                              'ArrowLeft',
                              'ArrowRight',
                              'ArrowUp',
                              'ArrowDown',
                            ].includes(event.key)
                          )
                            return;
                          event.preventDefault();
                          const step = event.shiftKey ? 1 : 0.1;
                          changePoint(
                            selected,
                            boundedPoint(section, index, {
                              distance_m:
                                point.distance_m +
                                (event.key === 'ArrowRight'
                                  ? step
                                  : event.key === 'ArrowLeft'
                                    ? -step
                                    : 0),
                              elevation_m:
                                point.elevation_m +
                                (event.key === 'ArrowUp'
                                  ? step
                                  : event.key === 'ArrowDown'
                                    ? -step
                                    : 0),
                            }),
                          );
                        }}
                      />
                    );
                  })}
                </g>
              ))}
            </svg>
          </div>
        </ScrollArea>
      </Paper>
      <Text size="xs" c="dimmed">
        On small screens, swipe to pan the road. Drag a point, use arrow keys
        (Shift for larger steps), or enter exact values. Editing a generated
        feature's points converts that section to custom points; Undo restores
        its parameters.
      </Text>
      {activeSection && (
        <Select
          label="Edit point in selected section"
          placeholder="Choose a point for exact coordinates"
          searchable
          value={
            selection?.featureId === activeFeature.id
              ? String(selection.index)
              : null
          }
          data={(activeFeature.kind === 'points'
            ? activeFeature.points
            : activeSection.points
          ).map((point, index) => ({
            value: String(index),
            label: `Point ${index + 1} · ${point.distance_m.toFixed(2)} m · elevation ${point.elevation_m.toFixed(2)} m`,
          }))}
          onChange={(index) =>
            index !== null &&
            setSelection({ featureId: activeFeature.id, index: Number(index) })
          }
        />
      )}
      {selectedSection && selectedPoint && (
        <Paper withBorder p="sm">
          <Stack gap="xs">
            <Text fw={600}>
              Selected point {selection!.index + 1} · local section coordinates
            </Text>
            <SimpleGrid cols={{ base: 1, sm: 2 }}>
              <QuantityInput
                label="Point distance"
                unit="m"
                scale={1}
                value={selectedPoint.distance_m}
                disabled={selection!.index === 0}
                onChange={(distance_m) =>
                  changePoint(selection!, { ...selectedPoint, distance_m })
                }
              />
              <QuantityInput
                label="Point elevation"
                unit="m"
                scale={1}
                value={selectedPoint.elevation_m}
                disabled={selection!.index === 0}
                onChange={(elevation_m) =>
                  changePoint(selection!, { ...selectedPoint, elevation_m })
                }
              />
            </SimpleGrid>
            <Button
              variant="subtle"
              color="red"
              size="xs"
              disabledReason={
                !fresh
                  ? 'Wait for the road preview to update.'
                  : selection!.index === 0
                    ? 'The start point of a section is fixed.'
                    : selectedSection.points.length <= 2
                      ? 'A road section needs at least two points.'
                      : undefined
              }
              onClick={() => {
                replacePoints(
                  selectedSection,
                  selectedSection.points.filter(
                    (_, i) => i !== selection!.index,
                  ),
                );
                setSelection(null);
              }}
            >
              Remove selected point
            </Button>
          </Stack>
        </Paper>
      )}
      <Group align="end">
        <Select
          label="Add road feature"
          value={templateId}
          data={metadata.feature_templates.map((template) => ({
            value: template.id,
            label: template.name || template.kind,
          }))}
          onChange={(next) => next && setTemplateId(next)}
          style={{ flex: 1, minWidth: 180 }}
        />
        <Button
          disabledReason={
            value.features.length >= metadata.limits.max_features
              ? 'This load case has reached its road-section limit.'
              : undefined
          }
          onClick={() => {
            const feature = {
              ...structuredClone(
                metadata.feature_templates.find(
                  (item) => item.id === templateId,
                )!,
              ),
              id: crypto.randomUUID(),
            };
            onChange({ ...value, features: [...value.features, feature] });
            setSectionId(feature.id);
            setSelection(null);
          }}
        >
          Add section
        </Button>
      </Group>
      <Group gap="xs">
        {value.features.map((feature, index) => (
          <Button
            key={feature.id}
            size="xs"
            variant={feature.id === activeFeature.id ? 'filled' : 'default'}
            onClick={() => {
              setSectionId(feature.id);
              setSelection(null);
            }}
          >
            {index + 1}. {feature.name || feature.kind}
          </Button>
        ))}
      </Group>
      <Paper withBorder p="md">
        <Stack>
          <Group justify="space-between">
            <Text fw={700}>
              Section {value.features.indexOf(activeFeature) + 1} ·{' '}
              {activeFeature.kind}
            </Text>
            <Group gap="xs">
              {([-1, 1] as const).map((direction) => (
                <Button
                  key={direction}
                  size="compact-sm"
                  variant="default"
                  aria-label={
                    direction === -1
                      ? 'Move section earlier'
                      : 'Move section later'
                  }
                  disabledReason={
                    (
                      direction === -1
                        ? value.features.indexOf(activeFeature) === 0
                        : value.features.indexOf(activeFeature) ===
                          value.features.length - 1
                    )
                      ? 'This section is already at that end of the road.'
                      : undefined
                  }
                  onClick={() => {
                    const features = [...value.features],
                      index = features.indexOf(activeFeature);
                    [features[index], features[index + direction]] = [
                      features[index + direction],
                      features[index],
                    ];
                    onChange({ ...value, features });
                  }}
                >
                  {direction === -1 ? (
                    <IconArrowUp size={16} />
                  ) : (
                    <IconArrowDown size={16} />
                  )}
                </Button>
              ))}
              <Button
                size="compact-sm"
                variant="default"
                aria-label="Duplicate section"
                disabledReason={
                  value.features.length >= metadata.limits.max_features
                    ? 'This load case has reached its road-section limit.'
                    : undefined
                }
                onClick={() => {
                  const feature = {
                    ...structuredClone(activeFeature),
                    id: crypto.randomUUID(),
                  };
                  const features = [...value.features];
                  features.splice(
                    features.indexOf(activeFeature) + 1,
                    0,
                    feature,
                  );
                  onChange({ ...value, features });
                  setSectionId(feature.id);
                }}
              >
                <IconCopy size={16} />
              </Button>
              <Button
                size="compact-sm"
                variant="subtle"
                color="red"
                aria-label="Delete section"
                disabledReason={
                  value.features.length <= 1
                    ? 'A load case needs at least one road section.'
                    : undefined
                }
                onClick={() => {
                  onChange({
                    ...value,
                    features: value.features.filter(
                      (feature) => feature.id !== activeFeature.id,
                    ),
                  });
                  setSelection(null);
                }}
              >
                <IconTrash size={16} />
              </Button>
            </Group>
          </Group>
          <FeatureInputs value={activeFeature} onChange={updateFeature} />
          <Button
            variant="light"
            disabledReason={
              !fresh
                ? 'Wait for the road preview to update.'
                : !activeSection
                  ? 'Select a road section first.'
                  : (resolution?.profile.segments.length ?? 0) >=
                      metadata.limits.max_segments
                    ? 'This road has reached its point limit.'
                    : undefined
            }
            onClick={() => {
              if (!activeSection) return;
              const points = [...activeSection.points];
              const a = points.at(-2)!,
                b = points.at(-1)!;
              points.splice(points.length - 1, 0, {
                distance_m: (a.distance_m + b.distance_m) / 2,
                elevation_m: (a.elevation_m + b.elevation_m) / 2,
              });
              replacePoints(activeSection, points);
              setSelection({
                featureId: activeSection.feature_id,
                index: points.length - 2,
              });
            }}
          >
            Add point inside section
          </Button>
        </Stack>
      </Paper>
      <Select
        label="After the final point"
        value={value.endpoint ?? 'flat'}
        data={[
          { value: 'flat', label: 'Continue on flat road' },
          { value: 'continue_grade', label: 'Continue the final grade' },
        ]}
        onChange={(endpoint) =>
          onChange({
            ...value,
            endpoint: endpoint === 'continue_grade' ? 'continue_grade' : 'flat',
          })
        }
      />
      {resolution && (
        <Text size="sm" c="dimmed">
          {resolution.length_m.toFixed(1)} m ·{' '}
          {resolution.profile.segments.length} grade segments · steepest grade{' '}
          {((resolution.maximum_absolute_grade_rad * 180) / Math.PI).toFixed(1)}
          °. Abrupt joins may require a smaller maximum solver step.
        </Text>
      )}
    </Stack>
  );
}
