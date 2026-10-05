import { lazy, Suspense, useEffect, useState } from 'react';
import {
  Accordion,
  Alert,
  Box,
  Group,
  Loader,
  Paper,
  SimpleGrid,
  Stack,
  Text,
  Title,
} from '@mantine/core';
import { ActionButton as Button } from '@components/button/ActionButton';
import { QuantityInput } from '@components/quantityInput/QuantityInput';
import {
  expandJsonPointerTemplate,
  getValueAtJsonPointer,
  setValueAtJsonPointer,
} from '@utils/jsonPointer';
import type { ScenePreview } from '@components/scene3DViewer/sceneSpec';
import {
  message,
  previewTune,
  type Tune,
  type TuneField,
  type TuneSurface,
} from './api';
const GeometryScene = lazy(
  () => import('@components/scene3DViewer/GeometryScene'),
);
type RampField = Extract<TuneField, { kind: 'ramp' }>;

/** UI convention only: CINDER stores profile slope from the axial direction. */
const helixAngle = (angle: number) => Math.PI / 2 - angle;

function Measurement({
  label,
  value,
  unit,
}: {
  label: string;
  value: number;
  unit?: string;
}) {
  return (
    <div>
      <Text size="sm" c="dimmed">
        {label}
      </Text>
      <Text>
        {Number(value.toPrecision(6))} {unit}
      </Text>
    </div>
  );
}
function RampEditor({
  field,
  value,
  onChange,
  readOnly,
}: {
  field: RampField;
  value: RampField['default'];
  onChange: (value: RampField['default']) => void;
  readOnly: boolean;
}) {
  const inputs = field.fields
    .flatMap((hint) =>
      expandJsonPointerTemplate(value, hint.path).map((path) => ({
        hint,
        path,
      })),
    )
    .map(({ hint, path }) => {
      const stored = getValueAtJsonPointer(value, path);
      if (typeof stored !== 'number') return null;
      const helix =
        field.angle_convention === 'helix' &&
        /\/(angle|angle_start|angle_end)_rad$/.test(path);
      const current = helix ? helixAngle(stored) : stored;
      const segment = path.match(/\/segments\/(\d+)\//);
      const label = `${value.segments.length > 1 && segment ? `Segment ${Number(segment[1]) + 1} · ` : ''}${helix ? hint.label.replace(/angle/i, 'helix angle') : hint.label}`;
      return (
        <div key={path}>
          {readOnly ? (
            <Measurement
              label={label}
              value={current * (hint.display_scale ?? 1)}
              unit={hint.display_unit}
            />
          ) : (
            <QuantityInput
              label={label}
              value={current}
              onChange={(next) =>
                onChange(
                  setValueAtJsonPointer(
                    value,
                    path,
                    helix ? helixAngle(next) : next,
                  ),
                )
              }
              unit={hint.display_unit}
              scale={hint.display_scale}
              min={helix ? undefined : (hint.minimum ?? undefined)}
              max={helix ? undefined : (hint.maximum ?? undefined)}
              integer={hint.integer}
            />
          )}
        </div>
      );
    });
  return (
    <Stack gap="sm">
      <Text size="sm" c="dimmed">
        {field.description}
      </Text>
      <SimpleGrid cols={{ base: 1, sm: 2 }}>{inputs}</SimpleGrid>
      {!readOnly && (
        <Accordion variant="separated">
          <Accordion.Item value="segments">
            <Accordion.Control>Profile segments</Accordion.Control>
            <Accordion.Panel>
              <Group>
                <Button
                  variant="light"
                  size="xs"
                  disabledReason={
                    value.segments.length >= 24
                      ? 'Maximum 24 segments.'
                      : undefined
                  }
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
                  Add segment
                </Button>
                <Button
                  variant="subtle"
                  size="xs"
                  disabledReason={
                    value.segments.length <= 1
                      ? 'At least one segment is required.'
                      : undefined
                  }
                  onClick={() =>
                    onChange({
                      ...value,
                      segments: value.segments.slice(0, -1),
                    })
                  }
                >
                  Remove final segment
                </Button>
              </Group>
            </Accordion.Panel>
          </Accordion.Item>
        </Accordion>
      )}
    </Stack>
  );
}
export function TuneEditor({
  value,
  surface,
  onChange,
  readOnly = false,
}: {
  value: Tune;
  surface: TuneSurface;
  onChange: (value: Tune) => void;
  readOnly?: boolean;
}) {
  const [preview, setPreview] = useState<ScenePreview | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const encoded = JSON.stringify({
    cvt_revision_id: value.cvt_revision_id,
    values: value.values,
  });
  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);
    setError(null);
    const timer = window.setTimeout(() => {
      void previewTune(JSON.parse(encoded), controller.signal)
        .then((next) => {
          if (!controller.signal.aborted) {
            setPreview(next);
            setLoading(false);
          }
        })
        .catch((cause) => {
          if (!controller.signal.aborted) {
            setError(message(cause));
            setLoading(false);
          }
        });
    }, 300);
    return () => {
      window.clearTimeout(timer);
      controller.abort();
    };
  }, [encoded]);
  const change = (key: string, next: NonNullable<Tune['values']>[string]) =>
    onChange({ ...value, values: { ...value.values, [key]: next } });
  return (
    <Stack gap="lg">
      {error && (
        <Alert color="orange" title="Preview unavailable">
          {error}
          {preview && ' Showing the last valid preview.'}
        </Alert>
      )}
      {(['primary', 'secondary'] as const).map((mount) => (
        <Paper key={mount} withBorder p="md">
          <Stack>
            <Group justify="space-between">
              <Title order={3} tt="capitalize">
                {mount} tune
              </Title>
              {loading && (
                <Loader size="xs" aria-label="Updating component preview" />
              )}
            </Group>
            <SimpleGrid cols={{ base: 1, md: 2 }}>
              <Stack>
                <SimpleGrid cols={{ base: 1, sm: 2, md: 1 }}>
                  {surface.fields
                    .filter((f) => f.group === mount)
                    .filter((f) => f.kind === 'number')
                    .map((field) => {
                      const current = value.values?.[field.key];
                      const numeric =
                        typeof current === 'number' ? current : field.default;
                      return readOnly ? (
                        <Measurement
                          key={field.key}
                          label={field.label}
                          value={numeric * (field.display_scale ?? 1)}
                          unit={field.display_unit}
                        />
                      ) : (
                        <QuantityInput
                          key={field.key}
                          label={field.label}
                          value={numeric}
                          onChange={(next) => change(field.key, next)}
                          unit={field.display_unit}
                          scale={field.display_scale}
                          description={field.description}
                          min={field.minimum ?? undefined}
                          max={field.maximum ?? undefined}
                        />
                      );
                    })}
                </SimpleGrid>
                {surface.fields
                  .filter((f) => f.group === mount)
                  .filter((f) => f.kind === 'ramp')
                  .map((field) => {
                    const current = value.values?.[field.key];
                    return (
                      <Stack key={field.key} gap="xs">
                        <Text fw={600}>{field.label}</Text>
                        <RampEditor
                          field={field}
                          value={
                            typeof current === 'object' && current !== null
                              ? current
                              : field.default
                          }
                          onChange={(next) => change(field.key, next)}
                          readOnly={readOnly}
                        />
                      </Stack>
                    );
                  })}
              </Stack>
              <Stack gap="xs">
                <Box h={300} pos="relative" style={{ minWidth: 0 }}>
                  {preview ? (
                    <Suspense fallback={<Loader />}>
                      <GeometryScene preview={preview} component={mount} />
                    </Suspense>
                  ) : (
                    !error && <Loader />
                  )}
                </Box>
                <Text size="xs" c="dimmed">
                  Drag to rotate ·{' '}
                  {mount === 'primary'
                    ? 'Flyweights and ramp'
                    : 'Helix and rollers'}
                </Text>
              </Stack>
            </SimpleGrid>
          </Stack>
        </Paper>
      ))}
    </Stack>
  );
}
