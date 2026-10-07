import { useEffect, useId, useRef, useState } from 'react';
import {
  Alert,
  Checkbox,
  Group,
  Paper,
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
import { projectCourse, roadFromMap } from '@components/course/courseGeometry';
import {
  message,
  resolveRoad,
  type ExperimentMetadata,
  type Road,
  type RoadFeature,
  type RoadPoint,
  type RoadResolution,
} from './api';
import styles from './RoadEditor.module.css';

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
            scope="course"
            label="Section length"
            unit="m"
            scale={1}
            min={0.01}
            value={value.length_m}
            onChange={(length_m) => onChange({ ...value, length_m })}
          />
        )}
        {'angle_rad' in value && (
          <QuantityInput
            scope="course"
            label="Incline angle"
            unit="deg"
            description="Positive climbs; negative descends. Changing length keeps this angle."
            min={-Math.PI / 2 + Number.EPSILON}
            max={Math.PI / 2 - Number.EPSILON}
            value={value.angle_rad}
            onChange={(angle_rad) => onChange({ ...value, angle_rad })}
          />
        )}
        {'height_m' in value && (
          <QuantityInput
            scope="course"
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
              scope="course"
              label="Whoops spacing"
              unit="m"
              scale={1}
              min={0.01}
              value={value.spacing_m}
              onChange={(spacing_m) => onChange({ ...value, spacing_m })}
            />
            <QuantityInput
              scope="course"
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
  const [sectionId, setSectionId] = useState(value.features[0].id);
  const [templateId, setTemplateId] = useState(
    metadata.feature_templates[0].id,
  );
  const [pointIndex, setPointIndex] = useState(1);
  const [editPoints, setEditPoints] = useState(false);
  const [viewport, setViewport] = useState<{
    cx: number;
    cy: number;
    scale: number;
  } | null>(null);
  const [draft, setDraft] = useState<RoadPoint[] | null>(null);
  const svg = useRef<SVGSVGElement>(null);
  const clipId = useId();
  const gesture = useRef<{
    kind: 'point' | 'pan';
    index: number;
    x: number;
    y: number;
    cx: number;
    cy: number;
    points: ReturnType<typeof projectCourse>;
  } | null>(null);
  const key = JSON.stringify(value);
  const fresh = key === resolvedKey && !error;
  useEffect(() => {
    const controller = new AbortController();
    const timer = setTimeout(() => {
      void resolveRoad(JSON.parse(key) as Road, controller.signal)
        .then((next) => {
          if (!controller.signal.aborted) {
            setResolution(next);
            setResolvedKey(key);
            setError(null);
          }
        })
        .catch((cause) => {
          if (!controller.signal.aborted) setError(message(cause));
        });
    }, 140);
    return () => {
      clearTimeout(timer);
      controller.abort();
    };
  }, [key]);
  useEffect(() => onValidityChange(fresh), [fresh, onValidityChange]);
  const active =
    value.features.find((f) => f.id === sectionId) ?? value.features[0];
  const index = value.features.indexOf(active);
  const section = resolution?.sections.find((s) => s.feature_id === active.id);
  const points = section?.points ?? [];
  const mapped = projectCourse(resolution?.points ?? []);
  const selectedMapped = projectCourse(draft ?? points);
  const start =
    mapped.find(
      (p) =>
        section && Math.abs(p.distance_m - section.start_distance_m) < 1e-7,
    )?.horizontal_m ?? 0;
  const minY = Math.min(0, ...mapped.map((p) => p.elevation_m));
  const maxY = Math.max(1, ...mapped.map((p) => p.elevation_m));
  const length = mapped.at(-1)?.horizontal_m ?? 20;
  const fit = {
    cx: length / 2,
    cy: (minY + maxY) / 2,
    scale: Math.min(780 / Math.max(length, 1), 240 / (maxY - minY)),
  };
  const view = viewport ?? fit;
  const x = (v: number) => 460 + (v - view.cx) * view.scale;
  const y = (v: number) => 170 - (v - view.cy) * view.scale;
  const update = (feature: RoadFeature) =>
    onChange({
      ...value,
      features: value.features.map((f) => (f.id === feature.id ? feature : f)),
    });
  const changePoints = (next: RoadPoint[]) =>
    update({ id: active.id, name: active.name, kind: 'points', points: next });
  const pick = (id: string) => {
    setSectionId(id);
    setDraft(null);
    setPointIndex(1);
  };
  const localPointer = (event: React.PointerEvent<SVGSVGElement>) => {
    const matrix = svg.current?.getScreenCTM();
    return matrix
      ? new DOMPoint(event.clientX, event.clientY).matrixTransform(
          matrix.inverse(),
        )
      : null;
  };
  const zoom = (factor: number) =>
    setViewport({
      ...view,
      scale: Math.max(
        fit.scale / 2,
        Math.min(fit.scale * 100, view.scale * factor),
      ),
    });
  const moveSection = (delta: number) => {
    const features = [...value.features];
    [features[index], features[index + delta]] = [
      features[index + delta],
      features[index],
    ];
    onChange({ ...value, features });
  };
  return (
    <Stack gap="md">
      <Group justify="space-between">
        <Text fw={700}>
          Road profile · {resolution?.length_m.toFixed(1) ?? '…'} m
        </Text>
        <Group gap="xs">
          <Button
            size="xs"
            variant="default"
            onClick={() => zoom(1 / 1.5)}
            aria-label="Zoom out"
          >
            −
          </Button>
          <Button
            size="xs"
            variant="default"
            onClick={() => zoom(1.5)}
            aria-label="Zoom in"
          >
            +
          </Button>
          <Button size="xs" variant="light" onClick={() => setViewport(null)}>
            Fit course
          </Button>
          <Button
            size="xs"
            variant="light"
            disabledReason={!section ? 'Wait for the preview.' : undefined}
            onClick={() => {
              const local = projectCourse(points);
              const end = local.at(-1)?.horizontal_m ?? 1;
              const low = Math.min(...local.map((p) => p.elevation_m));
              const high = Math.max(...local.map((p) => p.elevation_m));
              setViewport({
                cx: start + end / 2,
                cy: (section?.start_elevation_m ?? 0) + (low + high) / 2,
                scale: Math.min(
                  650 / Math.max(end, 1),
                  210 / Math.max(high - low, 1),
                ),
              });
            }}
          >
            Fit section
          </Button>
        </Group>
      </Group>
      {error && (
        <Alert color="red" role="alert">
          {error}
        </Alert>
      )}
      <Paper withBorder p="xs" style={{ minWidth: 0, overflow: 'hidden' }}>
        <svg
          ref={svg}
          viewBox="0 0 900 350"
          role="group"
          aria-label="Road elevation editor"
          style={{
            width: '100%',
            display: 'block',
            touchAction: 'none',
            cursor: 'grab',
          }}
          onPointerDown={(event) => {
            if (event.button !== 0) return;
            const p = localPointer(event);
            if (!p) return;
            const handle = (event.target as Element).getAttribute('data-point');
            if (handle !== null && fresh && Number(handle) > 0) {
              setPointIndex(Number(handle));
              gesture.current = {
                kind: 'point',
                index: Number(handle),
                x: p.x,
                y: p.y,
                cx: view.cx,
                cy: view.cy,
                points: projectCourse(points),
              };
            } else {
              gesture.current = {
                kind: 'pan',
                index: 0,
                x: p.x,
                y: p.y,
                cx: view.cx,
                cy: view.cy,
                points: [],
              };
            }
            setViewport(view);
            event.currentTarget.setPointerCapture(event.pointerId);
          }}
          onPointerMove={(event) => {
            const g = gesture.current,
              p = localPointer(event);
            if (!g || !p) return;
            if (g.kind === 'pan')
              setViewport({
                ...view,
                cx: g.cx - (p.x - g.x) / view.scale,
                cy: g.cy + (p.y - g.y) / view.scale,
              });
            else {
              const next = g.points.map((p) => ({ ...p }));
              const i = g.index;
              const upper = next[i + 1]
                ? next[i + 1].horizontal_m - 0.01
                : metadata.limits.max_distance_m;
              next[i].horizontal_m = Math.max(
                next[i - 1].horizontal_m + 0.01,
                Math.min(
                  upper,
                  g.points[i].horizontal_m + (p.x - g.x) / view.scale,
                ),
              );
              next[i].elevation_m =
                g.points[i].elevation_m - (p.y - g.y) / view.scale;
              setDraft(roadFromMap(next));
            }
          }}
          onPointerUp={() => {
            if (gesture.current?.kind === 'point' && draft) changePoints(draft);
            gesture.current = null;
            setDraft(null);
          }}
          onPointerCancel={() => {
            gesture.current = null;
            setDraft(null);
          }}
        >
          <defs>
            <clipPath id={clipId}>
              <rect x="60" y="25" width="810" height="270" />
            </clipPath>
          </defs>
          {[0, 1, 2, 3, 4].map((i) => {
            const py = 35 + i * 60;
            const elevation = view.cy + (170 - py) / view.scale;
            return (
              <g key={i}>
                <line
                  x1="60"
                  x2="870"
                  y1={py}
                  y2={py}
                  stroke="var(--mantine-color-default-border)"
                />
                <text
                  x="52"
                  y={py + 4}
                  textAnchor="end"
                  fill="currentColor"
                  fontSize="12"
                >
                  {elevation.toFixed(1)}
                </text>
              </g>
            );
          })}
          <g clipPath={`url(#${clipId})`}>
            <polyline
              points={mapped
                .map((p) => `${x(p.horizontal_m)},${y(p.elevation_m)}`)
                .join(' ')}
              stroke="var(--mantine-color-dimmed)"
              fill="none"
              strokeWidth="3"
            />
            {resolution?.sections.map((s) => {
              const begin =
                mapped.find(
                  (p) => Math.abs(p.distance_m - s.start_distance_m) < 1e-7,
                )?.horizontal_m ?? 0;
              const local =
                s.feature_id === active.id
                  ? selectedMapped
                  : projectCourse(s.points);
              return (
                <polyline
                  key={s.feature_id}
                  points={local
                    .map(
                      (p) =>
                        `${x(begin + p.horizontal_m)},${y(s.start_elevation_m + p.elevation_m)}`,
                    )
                    .join(' ')}
                  stroke={
                    s.feature_id === active.id
                      ? 'var(--mantine-primary-color-filled)'
                      : 'transparent'
                  }
                  fill="none"
                  strokeWidth={s.feature_id === active.id ? 4 : 18}
                  style={{ cursor: 'pointer' }}
                  onClick={() => pick(s.feature_id)}
                />
              );
            })}
            {editPoints &&
              selectedMapped.map((p, i) => (
                <circle
                  key={i}
                  data-point={i}
                  cx={x(start + p.horizontal_m)}
                  cy={y((section?.start_elevation_m ?? 0) + p.elevation_m)}
                  r={i === pointIndex ? 9 : 7}
                  stroke="var(--mantine-primary-color-filled)"
                  strokeWidth="2"
                  fill="var(--mantine-color-body)"
                  tabIndex={0}
                  role="button"
                  aria-label={`Edit point ${i + 1}`}
                  onFocus={() => setPointIndex(i)}
                  style={{ cursor: i ? 'grab' : 'default' }}
                />
              ))}
          </g>
          {[80, 460, 840].map((px) => (
            <text
              key={px}
              x={px}
              y="316"
              textAnchor="middle"
              fill="currentColor"
              fontSize="12"
            >
              {(view.cx + (px - 460) / view.scale).toFixed(1)}
            </text>
          ))}
          <text x="65" y="18" fill="currentColor" fontSize="12">
            Elevation (m)
          </text>
          <text
            x="460"
            y="340"
            textAnchor="middle"
            fill="currentColor"
            fontSize="13"
          >
            Horizontal distance (m)
          </text>
        </svg>
      </Paper>
      <Text size="xs" c="dimmed">
        Drag the background to pan. Zoom in or fit a section to edit a long
        course. {fresh ? '' : 'Updating preview…'}
      </Text>
      <div className={styles.editorColumns}>
        <Paper withBorder p="md">
          <Stack gap="xs">
            <Text fw={600}>Sections</Text>
            {value.features.map((feature, i) => (
              <Button
                key={feature.id}
                justify="start"
                variant={feature.id === active.id ? 'light' : 'subtle'}
                onClick={() => pick(feature.id)}
              >
                {i + 1}. {feature.name || feature.kind}
              </Button>
            ))}
            <Select
              label="Add section"
              value={templateId}
              allowDeselect={false}
              data={metadata.feature_templates.map((t) => ({
                value: t.id,
                label: t.name || t.kind,
              }))}
              onChange={(id) => id && setTemplateId(id)}
            />
            <Button
              disabledReason={
                value.features.length >= metadata.limits.max_features
                  ? 'The section limit has been reached.'
                  : undefined
              }
              onClick={() => {
                const feature = {
                  ...structuredClone(
                    metadata.feature_templates.find(
                      (t) => t.id === templateId,
                    )!,
                  ),
                  id: crypto.randomUUID(),
                };
                onChange({ ...value, features: [...value.features, feature] });
                pick(feature.id);
              }}
            >
              Add section
            </Button>
          </Stack>
        </Paper>
        <Paper withBorder p="md">
          <Stack>
            <Group justify="space-between">
              <Text fw={600}>Section {index + 1}</Text>
              <Group gap="xs">
                <Button
                  size="compact-xs"
                  variant="default"
                  aria-label="Move section earlier"
                  disabledReason={
                    index === 0 ? 'This is the first section.' : undefined
                  }
                  onClick={() => moveSection(-1)}
                >
                  <IconArrowUp size={16} />
                </Button>
                <Button
                  size="compact-xs"
                  variant="default"
                  aria-label="Move section later"
                  disabledReason={
                    index === value.features.length - 1
                      ? 'This is the last section.'
                      : undefined
                  }
                  onClick={() => moveSection(1)}
                >
                  <IconArrowDown size={16} />
                </Button>
                <Button
                  size="compact-xs"
                  variant="default"
                  aria-label="Duplicate section"
                  disabledReason={
                    value.features.length >= metadata.limits.max_features
                      ? 'The section limit has been reached.'
                      : undefined
                  }
                  onClick={() => {
                    const copy = {
                      ...structuredClone(active),
                      id: crypto.randomUUID(),
                    };
                    const features = [...value.features];
                    features.splice(index + 1, 0, copy);
                    onChange({ ...value, features });
                    pick(copy.id);
                  }}
                >
                  <IconCopy size={16} />
                </Button>
                <Button
                  size="compact-xs"
                  variant="default"
                  color="red"
                  aria-label="Remove section"
                  disabledReason={
                    value.features.length === 1
                      ? 'Keep at least one section.'
                      : undefined
                  }
                  onClick={() => {
                    onChange({
                      ...value,
                      features: value.features.filter(
                        (f) => f.id !== active.id,
                      ),
                    });
                    pick(value.features[index ? index - 1 : 1].id);
                  }}
                >
                  <IconTrash size={16} />
                </Button>
              </Group>
            </Group>
            <FeatureInputs value={active} onChange={update} />
            <Checkbox
              label="Edit individual points"
              checked={editPoints}
              onChange={(e) => setEditPoints(e.currentTarget.checked)}
            />
            {editPoints && (
              <>
                <Text size="xs" c="dimmed">
                  Dragging a point converts this section to custom points. Undo
                  restores its original feature.
                </Text>
                <Select
                  label="Point"
                  value={String(Math.min(pointIndex, points.length - 1))}
                  data={points.map((_, i) => ({
                    value: String(i),
                    label: `Point ${i + 1}`,
                  }))}
                  onChange={(v) => v !== null && setPointIndex(Number(v))}
                />
                {points[pointIndex] && (
                  <SimpleGrid cols={{ base: 1, sm: 2 }}>
                    <QuantityInput
                      scope="course"
                      label="Distance along section"
                      unit="m"
                      scale={1}
                      value={points[pointIndex].distance_m}
                      disabled={pointIndex === 0}
                      onChange={(v) =>
                        changePoints(
                          points.map((p, i) =>
                            i === pointIndex ? { ...p, distance_m: v } : p,
                          ),
                        )
                      }
                    />
                    <QuantityInput
                      scope="course"
                      label="Elevation from section start"
                      unit="m"
                      scale={1}
                      value={points[pointIndex].elevation_m}
                      disabled={pointIndex === 0}
                      onChange={(v) =>
                        changePoints(
                          points.map((p, i) =>
                            i === pointIndex ? { ...p, elevation_m: v } : p,
                          ),
                        )
                      }
                    />
                  </SimpleGrid>
                )}
                <Group>
                  <Button
                    size="xs"
                    variant="light"
                    disabledReason={
                      !fresh
                        ? 'Wait for the preview.'
                        : points.length >= metadata.limits.max_segments
                          ? 'Point limit reached.'
                          : undefined
                    }
                    onClick={() => {
                      const next = [...points];
                      const i = Math.max(
                        1,
                        Math.min(pointIndex, points.length - 1),
                      );
                      const a = next[i - 1],
                        b = next[i];
                      next.splice(i, 0, {
                        distance_m: (a.distance_m + b.distance_m) / 2,
                        elevation_m: (a.elevation_m + b.elevation_m) / 2,
                      });
                      changePoints(next);
                      setPointIndex(i);
                    }}
                  >
                    Insert point
                  </Button>
                  <Button
                    size="xs"
                    color="red"
                    variant="subtle"
                    disabledReason={
                      pointIndex === 0 || points.length <= 2
                        ? 'Keep the starting point and at least two points.'
                        : undefined
                    }
                    onClick={() => {
                      changePoints(points.filter((_, i) => i !== pointIndex));
                      setPointIndex(Math.max(1, pointIndex - 1));
                    }}
                  >
                    Remove point
                  </Button>
                </Group>
              </>
            )}
          </Stack>
        </Paper>
      </div>
      <Select
        label="Beyond the course finish"
        value={value.endpoint ?? 'flat'}
        allowDeselect={false}
        data={[
          { value: 'flat', label: 'Continue on flat ground' },
          { value: 'continue_grade', label: 'Continue the final grade' },
        ]}
        onChange={(v) =>
          onChange({ ...value, endpoint: v === 'continue_grade' ? v : 'flat' })
        }
      />
      <Text size="xs" c="dimmed">
        Section lengths are measured along the road. This model changes grade
        load; it does not model suspension or jumps.
      </Text>
    </Stack>
  );
}
