import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import {
  Alert,
  Badge,
  Button,
  Group,
  Loader,
  Slider,
  Stack,
  Switch,
  Text,
  Title,
} from '@mantine/core';
import { PublicHeader } from '@components/appShell/PublicHeader';
import {
  EditorHistoryBoundary,
  UndoRedoControls,
} from '@components/editorHistory/EditorHistory';
import {
  SlidingBlockEditor,
  type Feature,
  type DimensionKey,
} from './SlidingBlockEditor';
import { useSlidingBlockPreview } from './useSlidingBlockPreview';
import { SlidingBlockSection } from './SlidingBlockSection';
import { SlidingBlockScene } from './SlidingBlockScene';
import { colors } from './slidingBlockModels';
import styles from './SlidingBlock.module.scss';

export function SlidingBlockDemo() {
  const preview = useSlidingBlockPreview();
  const { data, error, draft } = preview;
  const [selected, setSelected] = useState<Feature>('block');
  const [focused, setFocused] = useState<DimensionKey>('block_thickness_m');
  const [index, setIndex] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [cutaway, setCutaway] = useState(true);
  const [contacts, setContacts] = useState(true);
  const [reset, setReset] = useState(0);
  useEffect(() => {
    if (!playing || !data || !preview.geometryCurrent) return;
    const end = data.frames.length - 1;
    let direction = index === end ? -1 : 1;
    const timer = window.setInterval(
      () =>
        setIndex((value) => {
          if (value >= end) direction = -1;
          if (value <= 0) direction = 1;
          return value + direction;
        }),
      30
    );
    return () => window.clearInterval(timer);
    // Start from the current slider position; scrubbing stops playback.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [playing, data, preview.geometryCurrent]);
  const frame = data?.frames[index];
  const select = (feature: Feature) => {
    setSelected(feature);
    const first = data?.dimensions.find((d) => d.feature === feature);
    if (first) setFocused(first.key);
  };
  return (
    <main className={styles.page}>
      <PublicHeader />
      <header className={styles.header}>
        <div>
          <Text className={styles.eyebrow}>MECHANISM LAB / SAMPLE 01</Text>
          <Title order={1}>Inside a sliding-block primary</Title>
          <Text c="dimmed" mt="xs">
            A rounded block against a curved cup, with a flat face matched to
            the movable ramp.
          </Text>
        </div>
        <Group gap="xs">
          <Badge variant="light">
            CINDER {data?.cinder_version ?? '1.2.0'}
          </Badge>
          <Button component={Link} to="/demo" variant="subtle">
            Drive demo →
          </Button>
        </Group>
      </header>
      {error && !data && (
        <Alert color="red" title="Sample unavailable" role="alert">
          {error}
          <Button variant="subtle" onClick={preview.retry}>
            Try again
          </Button>
        </Alert>
      )}
      {!data && !error && <Loader aria-label="Loading sliding-block sample" />}
      {data && frame && (
        <>
          <div className={styles.layout}>
            <section className={styles.viewerCard}>
              <div className={styles.viewerTop}>
                <span>
                  {preview.stale
                    ? 'Previous assembly preview'
                    : 'Assembly view'}
                </span>
                <span>Drag to orbit · scroll to zoom</span>
              </div>
              <SlidingBlockScene
                data={data}
                frame={frame}
                cutaway={cutaway}
                contacts={contacts}
                reset={reset}
              />
              <div className={styles.viewerTools}>
                <Switch
                  label="Cutaway"
                  checked={cutaway}
                  onChange={(e) => setCutaway(e.currentTarget.checked)}
                />
                <Switch
                  label="Contacts & normals"
                  checked={contacts}
                  onChange={(e) => setContacts(e.currentTarget.checked)}
                />
                <Button
                  size="xs"
                  variant="subtle"
                  onClick={() => setReset((v) => v + 1)}
                >
                  Reset view
                </Button>
              </div>
            </section>
            <aside className={styles.panel}>
              <Text className={styles.eyebrow}>INSPECT THE STROKE</Text>
              <Title order={2}>
                Outward motion,
                <br /> axial closure.
              </Title>
              <Text size="sm" c="dimmed">
                The cup stays fixed along the shaft. The inclined track travels
                with the movable sheave, while the guided block translates
                between them.
              </Text>
              <div className={styles.closure}>
                <span>Sheave closure</span>
                <strong data-testid="closure-value">
                  {(frame.closure_m * 1000).toFixed(2)} <small>mm</small>
                </strong>
              </div>
              <Slider
                thumbLabel="Sheave closure"
                thumbValueText={(v) =>
                  `${(data.frames[v].closure_m * 1000).toFixed(2)} millimetres`
                }
                min={0}
                max={data.frames.length - 1}
                step={1}
                value={index}
                label={(v) =>
                  `${(data.frames[v].closure_m * 1000).toFixed(2)} mm`
                }
                onChange={(v) => {
                  setPlaying(false);
                  setIndex(v);
                }}
                marks={[
                  { value: 0, label: 'Open' },
                  { value: data.frames.length - 1, label: 'Closed' },
                ]}
              />
              <Group mt="xl">
                <Button
                  onClick={() => setPlaying((v) => !v)}
                  variant="light"
                  disabled={!preview.geometryCurrent}
                >
                  {playing ? 'Pause stroke' : 'Play stroke'}
                </Button>
                <Button
                  variant="subtle"
                  onClick={() => {
                    setPlaying(false);
                    setIndex(0);
                  }}
                >
                  Return to open
                </Button>
              </Group>
              <div className={styles.metrics}>
                <Metric
                  label="Block COM radius"
                  value={
                    preview.geometryCurrent
                      ? `${(frame.com_m[0] * 1000).toFixed(2)} mm`
                      : '—'
                  }
                />
                <Metric
                  label="Section gap · full stroke"
                  value={
                    preview.geometryCurrent
                      ? data.findings.length
                        ? 'Interference'
                        : `${(data.minimum_hardware_clearance_m * 1000).toFixed(2)} mm`
                      : '—'
                  }
                />
                <Metric
                  label="Closing force · whole set"
                  value={
                    preview.loadsCurrent
                      ? `${frame.closing_force_N.toFixed(0)} N`
                      : '—'
                  }
                />
                <Metric
                  label="Cup normal · per block"
                  value={
                    preview.loadsCurrent
                      ? `${(frame.fixed_reaction_N / data.block_count).toFixed(0)} N`
                      : '—'
                  }
                />
                <Metric
                  label="Ramp normal · per block"
                  value={
                    preview.loadsCurrent
                      ? `${(frame.moving_reaction_N / data.block_count).toFixed(0)} N`
                      : '—'
                  }
                />
                <Metric
                  label="Guide couple · per block"
                  value="Pressure dependent"
                />
              </div>
              <Text size="xs" c="dimmed">
                {preview.loadsCurrent
                  ? `Loads at ${data.rpm.toLocaleString()} rpm with closure held.`
                  : 'Loads unavailable until the current dimensions are valid.'}{' '}
                Playback scrubs geometry; it is not a transient simulation.
              </Text>
              {!data.simulation_ready && (
                <Alert title="Face contact study" color="orange" mt="sm">
                  The flat faces share one angle. The orange segment marks their
                  contact span; the arrow shows normal direction. Pressure
                  location and guide couple are undetermined. CINDER 1.2 does
                  not yet accept this face contact in simulations.
                </Alert>
              )}
            </aside>
          </div>
          <section className={styles.sectionCard}>
            <div className={styles.sectionHeader}>
              <div>
                <Title order={2}>Edit the cross section</Title>
                <Text size="sm" c="dimmed">
                  Select a part, then change its dimensions. Both views refresh
                  together.
                </Text>
              </div>
              <div className={styles.legend}>
                {[
                  [colors.fixedTrack, 'Cup track'],
                  [colors.movingTrack, 'Moving track'],
                  [colors.block, 'Sliding block'],
                ].map(([color, label]) => (
                  <span key={label}>
                    <i style={{ background: color }} />
                    {label}
                  </span>
                ))}
              </div>
            </div>
            {data && (
              <div
                className={styles.previewStatus}
                role="status"
                data-testid="preview-status"
              >
                {preview.invalid
                  ? 'Correct the highlighted input. The drawing shows the previous dimensions.'
                  : preview.loading
                    ? 'Updating preview… The drawing shows the previous dimensions.'
                    : preview.stale
                      ? 'Preview unavailable for these dimensions. The drawing shows the previous dimensions.'
                      : preview.findings.length
                        ? 'Preview updated · hardware interference needs attention'
                        : 'Preview updated · hardware clears the full stroke'}
              </div>
            )}
            {preview.findings.length > 0 && (
              <Alert color="red" title="Geometry needs attention">
                {preview.findings.map((finding) => (
                  <Text key={finding.code} size="sm">
                    {finding.message}
                  </Text>
                ))}
              </Alert>
            )}
            {error && (
              <Alert color="red" title="Preview unavailable">
                {error}
                <Button variant="subtle" onClick={preview.retry}>
                  Try again
                </Button>
              </Alert>
            )}
            {draft.value && (
              <EditorHistoryBoundary
                history={draft.history}
                onRestore={() => setPlaying(false)}
              >
                <Group justify="space-between" mt="md">
                  <UndoRedoControls
                    history={draft.history}
                    onRestore={() => setPlaying(false)}
                  />
                  <Button
                    size="xs"
                    variant="subtle"
                    onClick={() => {
                      setPlaying(false);
                      preview.restoreDefaults();
                    }}
                  >
                    Reset dimensions
                  </Button>
                </Group>
                <div
                  className={styles.editorLayout}
                  onInput={() => setPlaying(false)}
                >
                  <div className={styles.sectionCanvas}>
                    <SlidingBlockSection
                      data={data}
                      frame={frame}
                      contacts={contacts}
                      selected={selected}
                      dimensionKey={focused}
                      onSelect={select}
                    />
                    <Text size="xs" c="dimmed" mt="xs">
                      Equal axis scale · red outlines mark interfering hardware
                      at this closure
                      {preview.stale ? ' · previous dimensions' : ''}
                    </Text>
                  </div>
                  <SlidingBlockEditor
                    data={data}
                    inputs={draft.value}
                    selected={selected}
                    onSelect={select}
                    onFocus={setFocused}
                    findings={preview.findings}
                    onChange={(key, value) => {
                      setPlaying(false);
                      draft.setValue((old) =>
                        old ? { ...old, [key]: value } : old
                      );
                    }}
                  />
                </div>
              </EditorHistoryBoundary>
            )}
          </section>
          <footer className={styles.footer}>
            <Stack gap={3}>
              <Text fw={600}>
                {data.block_count} distributed steel blocks ·{' '}
                {((data.total_mass_kg * 1000) / data.block_count).toFixed(1)} g
                each
              </Text>
              <Text size="sm" c="dimmed">
                The weight outline and mass properties describe the same solid.
                Surrounding cup and sheave material is representative CVT
                hardware.
              </Text>
            </Stack>
            <Text size="xs" c="dimmed">
              Synthetic sample · frictionless contacts · ideal orientation guide
            </Text>
          </footer>
        </>
      )}
    </main>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}
