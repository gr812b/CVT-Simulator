import { lazy, Suspense, useEffect, useState } from 'react';
import { Alert, Box, Group, Loader, Paper, SimpleGrid, Slider, Stack, Text, Title } from '@mantine/core';
import { ActionButton as Button } from '@components/button/ActionButton';
import { QuantityInput } from '@components/quantityInput/QuantityInput';
import { AngleProfileEditor } from './AngleProfileEditor';
import { message, previewTune, type Tune, type TuneField, type TuneSurface, type TunePreview } from './api';
import { tuneInputKey, type TuneCheck } from './tunePreviewState';
const GeometryScene = lazy(() => import('@components/scene3DViewer/GeometryScene'));

type Mount = 'primary' | 'secondary';
type NumberField = Extract<TuneField, { kind: 'number' }>;

function Measurement({ label, value, unit }: { label: string; value: number; unit?: string }) {
  return <div><Text size="sm" c="dimmed">{label}</Text><Text>{Number(value.toPrecision(6))} {unit}</Text></div>;
}

function travelIndex(preview: TunePreview | null, mount: Mount, percent: number): number {
  if (!preview?.frames.length) return 0;
  if (mount === 'primary') return Math.round(percent / 100 * (preview.frames.length - 1));
  const values = preview.secondary_opening_m;
  const finite = values.filter((x): x is number => x != null);
  if (!finite.length) return 0;
  const lo = Math.min(...finite), hi = Math.max(...finite);
  const target = lo + percent / 100 * (hi - lo);
  let best = 0, distance = Infinity;
  values.forEach((value, i) => {
    if (value != null && Math.abs(value - target) < distance) { best = i; distance = Math.abs(value - target); }
  });
  return best;
}

export function TuneEditor({ value, surface, onChange, readOnly = false, onValidationChange }: {
  value: Tune;
  surface: TuneSurface;
  onChange: (value: Tune) => void;
  readOnly?: boolean;
  onValidationChange?: (check: TuneCheck) => void;
}) {
  const [resolved, setResolved] = useState<{ inputKey: string; attempt: number; preview: TunePreview } | null>(null);
  const [failure, setFailure] = useState<{ inputKey: string; attempt: number; error: string } | null>(null);
  const [attempt, setAttempt] = useState(0);
  const [travel, setTravel] = useState({ primary: 0, secondary: 0 });
  const [resets, setResets] = useState({ primary: 0, secondary: 0 });
  const encoded = tuneInputKey(value);
  const preview = resolved?.preview ?? null;
  const current = resolved?.inputKey === encoded && resolved.attempt === attempt;
  const error = failure?.inputKey === encoded && failure.attempt === attempt ? failure.error : null;
  const loading = !current && !error;
  const stale = preview !== null && !current;
  const validation = current ? preview?.validation : undefined;

  useEffect(() => {
    const controller = new AbortController();
    const timer = window.setTimeout(() => {
      void previewTune(JSON.parse(encoded), controller.signal).then(next => {
        if (!controller.signal.aborted) {
          if (!next.validation || typeof next.validation.is_valid !== 'boolean' || !Array.isArray(next.validation.findings)) {
            throw new Error('The backend did not return a geometry check. Restart the updated backend and retry.');
          }
          setResolved({ inputKey: encoded, attempt, preview: next });
          setFailure(null);
        }
      }).catch(cause => {
        if (!controller.signal.aborted) setFailure({ inputKey: encoded, attempt, error: message(cause) });
      });
    }, 350);
    return () => { window.clearTimeout(timer); controller.abort(); };
  }, [encoded, attempt]);

  useEffect(() => {
    onValidationChange?.({ inputKey: encoded, validation, error });
  }, [encoded, validation, error, onValidationChange]);

  const change = (key: string, next: NonNullable<Tune['values']>[string]) =>
    onChange({ ...value, values: { ...value.values, [key]: next } });
  const measurement = (field: NumberField) => {
    const currentValue = value.values?.[field.key];
    const numeric = typeof currentValue === 'number' ? currentValue : field.default;
    return readOnly
      ? <Measurement key={field.key} label={field.label} value={numeric * (field.display_scale ?? 1)} unit={field.display_unit}/>
      : <QuantityInput key={field.key} label={field.label} value={numeric} onChange={n => change(field.key, n)} unit={field.display_unit}
          scale={field.display_scale} description={field.description} min={field.minimum ?? undefined} max={field.maximum ?? undefined}/>;
  };
  const findings = validation?.findings.filter(finding => finding.severity === 'error') ?? [];
  return <Stack gap="lg">
    {error && <Alert color="orange" title="Geometry could not be checked">
      <Stack gap="xs"><Text size="sm">{error}{preview && ' The drawing shows the previous values.'}</Text>
        <Button variant="light" size="xs" onClick={() => { setFailure(null); setAttempt(n => n + 1); }}>Retry geometry check</Button>
      </Stack>
    </Alert>}
    {loading && <Text role="status" size="sm" c="dimmed">Checking geometry…{stale && ' The drawing still shows the previous values.'}</Text>}
    {validation && (!validation.is_valid || findings.length > 0) && <Alert color="red" title="Geometry needs attention">
      {findings.length ? findings.map((finding, i) => <Text size="sm" key={i}>{finding.message}</Text>)
        : <Text size="sm">This geometry did not pass the construction check.</Text>}
      <Text size="sm" mt="xs">You can keep editing, but cannot save or use this tune until the geometry is valid.</Text>
    </Alert>}
    {current && preview?.warnings.length ? <Alert color="orange" title="Contact diagnostics">
      {preview.warnings.map((warning, i) => <Text size="sm" key={i}>{warning}</Text>)}
    </Alert> : null}
    {(['primary', 'secondary'] as const).map(mount => {
      const index = travelIndex(preview, mount, travel[mount]);
      const frame = preview?.frames[index];
      const arm = preview?.primary_arm_angles_rad[index];
      const opening = preview?.secondary_opening_m[index];
      const trace = mount === 'primary' ? preview?.primary_profile : preview?.secondary_profile;
      const contact = mount === 'primary' ? preview?.primary_contact_coordinates_m[index] : opening;
      const hasMechanism = mount === 'primary' ? !!preview?.geometry.mechanisms?.primary : !!preview?.geometry.mechanisms?.secondary_helix_points_m.length;
      const primaryClosure = preview?.geometry.mechanisms?.poses.find(p => p.shift_m === frame?.shift_m)?.primary_ramp_shift_m;
      const sliderMax = mount === 'primary' ? Math.max(1e-9, (preview?.geometry.max_shift_m ?? 0.02) * 1000) : 100;
      const openingPercent = trace?.used_start_m != null && trace.used_end_m != null && opening != null && trace.used_end_m > trace.used_start_m
        ? 100 * (opening - trace.used_start_m) / (trace.used_end_m - trace.used_start_m) : null;
      const contactFailure = current && mount === 'primary' && preview?.primary_contact_failure_m != null
        ? Math.min(sliderMax, Math.max(0, preview.primary_contact_failure_m * 1000)) : null;
      const marks = [{ value: 0, label: contactFailure === 0 ? 'No contact at start' : 'Start' },
        ...(contactFailure !== null && contactFailure > 0 && contactFailure < sliderMax ? [{ value: contactFailure, label: 'Contact limit' }] : []),
        { value: sliderMax, label: contactFailure === sliderMax ? 'No contact at end' : 'End' }];
      const numbers = surface.fields.filter((field): field is NumberField => field.group === mount && field.kind === 'number');
      const placement = numbers.filter(field => field.subgroup === 'ramp_position');
      return <Paper key={mount} withBorder p="md" data-tune-mount={mount}>
        <Stack>
          <Group justify="space-between"><Title order={3} tt="capitalize">{mount} tune</Title>{loading && <Loader size="xs" aria-label="Checking component geometry"/>}</Group>
          <SimpleGrid cols={{ base: 1, md: 2 }}>
            <Stack>
              <SimpleGrid cols={{ base: 1, sm: 2, md: 1 }}>
                {numbers.filter(field => field.subgroup !== 'ramp_position').map(measurement)}
              </SimpleGrid>
              {placement.length > 0 && <Stack gap="xs">
                <Text fw={600}>Ramp start position</Text>
                <Text size="sm" c="dimmed">Position of the ramp’s starting tip relative to the fixed pivot, at fully open primary. This moves the ramp, not the pivot or arm. The initial roller contact is solved from the resulting geometry.</Text>
                <SimpleGrid cols={{ base: 1, sm: 2, md: 1 }}>{placement.map(measurement)}</SimpleGrid>
              </Stack>}
              {surface.fields.filter(f => f.group === mount).filter(f => f.kind === 'ramp').map(field => {
                const currentValue = value.values?.[field.key];
                return <Stack key={field.key} gap="xs"><Text fw={600}>{field.label}</Text>
                  <AngleProfileEditor field={field} value={typeof currentValue === 'object' && currentValue !== null ? currentValue : field.default}
                    onChange={next => change(field.key, next)} readOnly={readOnly} trace={trace} contact={contact}/>
                </Stack>;
              })}
            </Stack>
            <Stack gap="sm" style={{ alignSelf: 'start', position: 'sticky', top: 0 }}>
              <Group justify="space-between"><Text fw={600}>{mount === 'primary' ? 'Ramp & flyweight' : 'Helix & rollers'}</Text>
                <Button size="compact-xs" variant="subtle" disabled={!preview} onClick={() => setResets(r => ({ ...r, [mount]: r[mount] + 1 }))}>Reset {mount} view</Button>
              </Group>
              <Box h={360} pos="relative" style={{ minWidth: 0 }}>
                {preview && hasMechanism ? <Suspense fallback={<Loader/>}><GeometryScene preview={preview} component={mount} frameIndex={index} resetKey={resets[mount]}/></Suspense>
                  : loading ? <Loader/> : <Text size="sm" c="dimmed">No supported {mount} mechanism is available to preview.</Text>}
              </Box>
              <Text size="xs" c="dimmed">Drag to rotate · Scroll or pinch to zoom · The camera stays where you leave it while scrubbing.</Text>
              <Text size="sm" fw={500}>{mount === 'primary' ? 'Movable-sheave closure' : 'Secondary opening travel'}</Text>
              <Slider aria-label={`${mount} travel`} min={0} max={sliderMax} step={sliderMax / 128} value={travel[mount] / 100 * sliderMax}
                disabled={!hasMechanism} label={v => `${v.toFixed(2)}${mount === 'primary' ? ' mm' : '%'}`} marks={marks}
                onChange={v => setTravel(p => ({ ...p, [mount]: v / sliderMax * 100 }))}/>
              <Text size="sm" mt="sm" aria-live="polite">
                {mount === 'primary'
                  ? `${((primaryClosure ?? 0) * 1000).toFixed(2)} mm closure · ${arm != null ? `Flyweight arm ${(arm * 180 / Math.PI).toFixed(1)}°` : 'No valid contact at this position'}`
                  : opening != null ? `${openingPercent?.toFixed(1) ?? '—'}% opening · ${(opening * 1000).toFixed(2)} mm profile coordinate` : 'No helix contact preview'}
              </Text>
              {contactFailure != null && <Text size="xs" c="red">First unavailable contact sample: {contactFailure.toFixed(2)} mm closure. Save and Use remain disabled.</Text>}
              <Text size="xs" c="dimmed">{mount === 'primary'
                ? 'Ramp angle and flyweight arm angle are different. The arm angle is measured from the positive axial direction at the fixed pivot.'
                : 'The orientation indicator’s radial and tangent directions refer to the marked roller 1.'} This is a kinematic inspection; a valid geometry check does not guarantee compressive contact forces throughout a dynamic run.</Text>
            </Stack>
          </SimpleGrid>
        </Stack>
      </Paper>;
    })}
  </Stack>;
}
