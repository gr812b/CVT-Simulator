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
  getSlidingBlockDemo,
  type SlidingBlockDemo as DemoData,
} from '@api/client';
import { SlidingBlockSection } from './SlidingBlockSection';
import { SlidingBlockScene } from './SlidingBlockScene';
import { colors } from './slidingBlockModels';
import styles from './SlidingBlock.module.scss';

export function SlidingBlockDemo() {
  const [data, setData] = useState<DemoData | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [retry, setRetry] = useState(0);
  const [index, setIndex] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [cutaway, setCutaway] = useState(true);
  const [contacts, setContacts] = useState(true);
  const [reset, setReset] = useState(0);
  useEffect(() => {
    const controller = new AbortController();
    setError(null);
    void getSlidingBlockDemo(controller.signal)
      .then((value) => {
        if (!controller.signal.aborted) {
          setData(value);
          setIndex(0);
        }
      })
      .catch((cause) => {
        if (!controller.signal.aborted)
          setError(cause instanceof Error ? cause.message : String(cause));
      });
    return () => controller.abort();
  }, [retry]);
  useEffect(() => {
    if (!playing || !data) return;
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
  }, [playing, data]);
  const frame = data?.frames[index];
  return (
    <main className={styles.page}>
      <PublicHeader />
      <header className={styles.header}>
        <div>
          <Text className={styles.eyebrow}>MECHANISM LAB / SAMPLE 01</Text>
          <Title order={1}>Inside a sliding-block primary</Title>
          <Text c="dimmed" mt="xs">
            A curved reaction cup, a straight ramp, and the solid hardware that
            connects them.
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
      {error && (
        <Alert color="red" title="Sample unavailable" role="alert">
          {error}
          <Button variant="subtle" onClick={() => setRetry((v) => v + 1)}>
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
                <span>Assembly view</span>
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
                <br />
            {' '}axial closure.
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
                <Button onClick={() => setPlaying((v) => !v)} variant="light">
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
                  value={`${(frame.com_m[0] * 1000).toFixed(2)} mm`}
                />
                <Metric
                  label="Closing force · whole set"
                  value={`${frame.closing_force_N.toFixed(0)} N`}
                />
                <Metric
                  label="Cup normal · per block"
                  value={`${(frame.fixed_reaction_N / data.block_count).toFixed(0)} N`}
                />
                <Metric
                  label="Ramp normal · per block"
                  value={`${(frame.moving_reaction_N / data.block_count).toFixed(0)} N`}
                />
                <Metric
                  label="Guide couple · per block"
                  value={`${(Math.hypot(...frame.guide_moment_Nm) / data.block_count).toFixed(2)} N·m`}
                />
              </div>
              <Text size="xs" c="dimmed">
                Loads at {data.rpm.toLocaleString()} rpm with closure held.
                Playback scrubs geometry; it is not a transient simulation.
              </Text>
            </aside>
          </div>
          <section className={styles.sectionCard}>
            <div className={styles.sectionHeader}>
              <div>
                <Title order={2}>Through the centreline</Title>
                <Text size="sm" c="dimmed">
                  Full hardware sections around the same contact geometry.
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
            <SlidingBlockSection
              data={data}
              frame={frame}
              contacts={contacts}
            />
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
