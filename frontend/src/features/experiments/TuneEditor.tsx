import { lazy, Suspense, useEffect, useState } from 'react';
import { Alert, Box, Group, Loader, Paper, SimpleGrid, Slider, Stack, Text, Title } from '@mantine/core';
import { ActionButton as Button } from '@components/button/ActionButton';
import { QuantityInput } from '@components/quantityInput/QuantityInput';
import { AngleProfileEditor } from './AngleProfileEditor';
import { message, previewTune, type Tune, type TuneSurface, type TunePreview } from './api';
const GeometryScene = lazy(() => import('@components/scene3DViewer/GeometryScene'));

function Measurement({ label, value, unit }: { label: string; value: number; unit?: string }) {
  return <div><Text size="sm" c="dimmed">{label}</Text><Text>{Number(value.toPrecision(6))} {unit}</Text></div>;
}

function travelIndex(preview: TunePreview | null, mount: 'primary' | 'secondary', percent: number): number {
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

export function TuneEditor({ value, surface, onChange, readOnly = false }: {
  value: Tune; surface: TuneSurface; onChange: (value: Tune) => void; readOnly?: boolean;
}) {
  const [preview, setPreview] = useState<TunePreview | null>(null);
  const [previewKey, setPreviewKey] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [travel, setTravel] = useState({ primary: 0, secondary: 0 });
  const [resets, setResets] = useState({ primary: 0, secondary: 0 });
  const encoded = JSON.stringify({ cvt_revision_id: value.cvt_revision_id, values: value.values });
  useEffect(() => {
    const controller = new AbortController();
    setLoading(true); setError(null);
    const timer = window.setTimeout(() => {
      void previewTune(JSON.parse(encoded), controller.signal).then(next => {
        if (!controller.signal.aborted) { setPreview(next); setPreviewKey(encoded); setLoading(false); }
      }).catch(cause => {
        if (!controller.signal.aborted) { setError(message(cause)); setLoading(false); }
      });
    }, 350);
    return () => { window.clearTimeout(timer); controller.abort(); };
  }, [encoded]);
  const stale = preview !== null && encoded !== previewKey;
  const change = (key: string, next: NonNullable<Tune['values']>[string]) => onChange({ ...value, values: { ...value.values, [key]: next } });
  return <Stack gap="lg">
    {error && <Alert color="orange" title="Preview unavailable">{error}{preview && ' Showing the last valid preview, not these unsaved values.'}</Alert>}
    {stale && !error && <Text role="status" size="sm" c="dimmed">Updating the preview. The drawing still shows the previous values.</Text>}
    {preview?.warnings.length ? <Alert color="orange" title="Contact preview limitations">
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
      return <Paper key={mount} withBorder p="md" data-tune-mount={mount}>
        <Stack>
          <Group justify="space-between"><Title order={3} tt="capitalize">{mount} tune</Title>{loading && <Loader size="xs" aria-label="Updating component preview"/>}</Group>
          <SimpleGrid cols={{ base: 1, md: 2 }}>
            <Stack>
              <SimpleGrid cols={{ base: 1, sm: 2, md: 1 }}>
                {surface.fields.filter(f => f.group === mount).filter(f => f.kind === 'number').map(field => {
                  const current = value.values?.[field.key];
                  const numeric = typeof current === 'number' ? current : field.default;
                  return readOnly ? <Measurement key={field.key} label={field.label} value={numeric * (field.display_scale ?? 1)} unit={field.display_unit}/> :
                    <QuantityInput key={field.key} label={field.label} value={numeric} onChange={n => change(field.key, n)} unit={field.display_unit}
                      scale={field.display_scale} description={field.description} min={field.minimum ?? undefined} max={field.maximum ?? undefined}/>;
                })}
              </SimpleGrid>
              {surface.fields.filter(f => f.group === mount).filter(f => f.kind === 'ramp').map(field => {
                const current = value.values?.[field.key];
                return <Stack key={field.key} gap="xs"><Text fw={600}>{field.label}</Text>
                  <AngleProfileEditor field={field} value={typeof current === 'object' && current !== null ? current : field.default}
                    onChange={next => change(field.key, next)} readOnly={readOnly} trace={trace} contact={contact}/>
                </Stack>;
              })}
            </Stack>
            <Stack gap="sm" style={{ alignSelf: 'start', position: 'sticky', top: 0 }}>
              <Group justify="space-between"><Text fw={600}>{mount === 'primary' ? 'Ramp & flyweight' : 'Helix & rollers'}</Text>
                <Button size="compact-xs" variant="subtle" disabled={!preview} onClick={() => setResets(r => ({ ...r, [mount]: r[mount] + 1 }))}>Reset {mount} view</Button>
              </Group>
              <Box h={360} pos="relative" style={{ minWidth: 0 }}>
                {preview && hasMechanism ? <Suspense fallback={<Loader/>}><GeometryScene preview={preview} component={mount} frameIndex={index} resetKey={resets[mount]}/></Suspense> :
                  loading ? <Loader/> : <Text size="sm" c="dimmed">No supported {mount} mechanism is available to preview.</Text>}
              </Box>
              <Text size="xs" c="dimmed">Drag to rotate · Scroll or pinch to zoom · The camera stays where you leave it while scrubbing.</Text>
              <Text size="sm" fw={500}>{mount === 'primary' ? 'Movable-sheave closure' : 'Secondary opening travel'}</Text>
              <Slider aria-label={`${mount} travel`} min={0} max={sliderMax} step={sliderMax / 128} value={travel[mount] / 100 * sliderMax}
                disabled={!hasMechanism} label={v => `${v.toFixed(2)}${mount === 'primary' ? ' mm' : '%'}`} marks={[{ value: 0, label: 'Start' }, { value: sliderMax, label: 'End' }]}
                onChange={v => setTravel(p => ({ ...p, [mount]: v / sliderMax * 100 }))}/>
              <Text size="sm" mt="sm" aria-live="polite">
                {mount === 'primary'
                  ? `${((primaryClosure ?? 0) * 1000).toFixed(2)} mm closure · ${arm != null ? `Flyweight arm ${(arm * 180 / Math.PI).toFixed(1)}°` : 'No valid contact at this position'}`
                  : opening != null ? `${openingPercent?.toFixed(1) ?? '—'}% opening · ${(opening * 1000).toFixed(2)} mm profile coordinate` : 'No helix contact preview'}
              </Text>
              <Text size="xs" c="dimmed">{mount === 'primary'
                ? 'The roller follows CINDER’s selected contact branch. Ramp position and sheave closure are different coordinates; the drawing shows the arm swinging between them. The arm angle is measured from the positive axial direction at the fixed pivot.'
                : 'The roller position and relative twist come from the configured helix coupling.'} This is a sampled kinematic preview, not a completed simulation or a substitute for save/run validation.</Text>
            </Stack>
          </SimpleGrid>
        </Stack>
      </Paper>;
    })}
  </Stack>;
}
