import { useEffect, useMemo, useRef, useState } from 'react';
import {
  Accordion,
  Alert,
  Checkbox,
  Group,
  Loader,
  MultiSelect,
  Popover,
  SegmentedControl,
  Slider,
  Stack,
  Switch,
  Table,
  Text,
} from '@mantine/core';
import { ActionButton as Button } from '@components/button/ActionButton';
import type { Scene3DController } from '@utils/Scene3DController';
import type { ReportReplayController } from '@utils/reportReplay';
import type { ReportTable } from '@api/client';
import { interpolatedValue } from '@utils/reportTable';
import { sceneDistance, type SceneGeometry } from './sceneSpec';
import { loadForces, type ForcePlayback } from './forceApi';
import {
  ForceRenderer,
  forceAt,
  forceBracket,
  type ForceOptions,
} from './forceRenderer';

export function ForceOverlay({
  source,
  scene,
  geometry,
  replay,
  table,
  transparent,
  onTransparent,
}: {
  source: string;
  scene: Scene3DController | null;
  geometry: SceneGeometry;
  replay: ReportReplayController;
  table: ReportTable;
  transparent: boolean;
  onTransparent: (value: boolean) => void;
}) {
  const [opened, setOpened] = useState(false);
  const [enabled, setEnabled] = useState(false);
  const [data, setData] = useState<ForcePlayback | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [retry, setRetry] = useState(0);
  const [body, setBody] = useState<ForceOptions['body']>('primary');
  const [selected, setSelected] = useState<string[] | null>(null);
  const [components, setComponents] = useState(['axial']);
  const [scale, setScale] = useState(1);
  const [labels, setLabels] = useState(false);
  const [cursor, setCursor] = useState(() => replay.visualSample());
  const time = cursor.simulationTime;
  const tracks = useMemo(
    () => data?.tracks.filter((t) => t.body === body) ?? [],
    [body, data],
  );
  const keys =
    selected ?? tracks.filter((t) => t.unit === 'N').map((t) => t.key);
  const options = useRef<ForceOptions>({
    body,
    tracks: keys,
    components,
    scale,
    labels,
  });
  options.current = { body, tracks: keys, components, scale, labels };
  useEffect(() => {
    if (!enabled || data) return;
    const abort = new AbortController();
    setError(null);
    void loadForces(source, abort.signal)
      .then((next) => {
        if (!abort.signal.aborted) setData(next);
      })
      .catch((cause) => {
        if (!abort.signal.aborted)
          setError(cause instanceof Error ? cause.message : String(cause));
      });
    return () => abort.abort();
  }, [enabled, source, data, retry]);
  useEffect(() => {
    if (!enabled || !data || !scene) return;
    const renderer = new ForceRenderer(scene, geometry, data);
    let lastTime = Number.NaN;
    let lastIndex = -1;
    let lastOptions: ForceOptions | null = null;
    const detach = scene.onFrame((now) => {
      const sample = replay.visualSample(now);
      if (
        sample.simulationTime === lastTime &&
        sample.lowerIndex === lastIndex &&
        options.current === lastOptions
      ) {
        return;
      }
      lastTime = sample.simulationTime;
      lastIndex = sample.lowerIndex;
      lastOptions = options.current;
      const shift = interpolatedValue(
        table,
        'state.shift_position',
        sample.lowerIndex,
        sample.upperIndex,
        sample.alpha,
      );
      renderer.update(sample, sceneDistance(shift ?? 0), options.current);
    });
    return () => {
      detach();
      renderer.dispose();
    };
  }, [enabled, data, scene, geometry, replay, table]);
  useEffect(() => {
    if (!opened) return;
    let last = 0;
    return replay.on(() => {
      const sample = replay.visualSample();
      if (!sample.playing || performance.now() - last > 100) {
        setCursor(sample);
        last = performance.now();
      }
    });
  }, [opened, replay]);
  const bracket = data ? forceBracket(data, cursor) : null;
  return (
    <Popover
      opened={opened}
      onChange={setOpened}
      position="bottom-end"
      width={380}
      withinPortal
    >
      <Popover.Target>
        <Button
          size="compact-xs"
          variant={enabled ? 'light' : 'default'}
          disabledReason={!scene ? 'Wait for the 3D scene.' : undefined}
          onClick={() => {
            setOpened((v) => !v);
            if (!data) setEnabled(true);
          }}
        >
          Forces
        </Button>
      </Popover.Target>
      <Popover.Dropdown
        style={{
          maxWidth: 'calc(100vw - 24px)',
          maxHeight: '75dvh',
          overflowY: 'auto',
        }}
      >
        <Stack gap="sm">
          <Switch
            label="Show contact vectors"
            checked={enabled}
            onChange={(e) => setEnabled(e.currentTarget.checked)}
          />
          {error && (
            <Alert color="red">
              {error}
              <Button variant="subtle" onClick={() => setRetry((x) => x + 1)}>
                Try again
              </Button>
            </Alert>
          )}
          {enabled && !data && !error && (
            <Group>
              <Loader size="sm" />
              <Text size="sm">Resolving force vectors…</Text>
            </Group>
          )}
          <SegmentedControl
            value={body}
            data={[
              { value: 'primary', label: 'Primary movable' },
              { value: 'secondary', label: 'Secondary movable' },
            ]}
            onChange={(v) => {
              setBody(v as ForceOptions['body']);
              setSelected(null);
            }}
          />
          <MultiSelect<string>
            label="Contacts and torques"
            data={tracks.map((t) => ({ value: t.key, label: t.label }))}
            value={keys}
            onChange={setSelected}
            searchable
          />
          <Checkbox.Group
            label="Vector components"
            value={components}
            onChange={setComponents}
          >
            <Group mt="xs">
              <Checkbox value="axial" label="Axial" color="cyan" />
              <Checkbox value="radial" label="Radial" color="pink" />
              <Checkbox value="tangential" label="Tangential" color="lime" />
            </Group>
          </Checkbox.Group>
          <Text size="xs" c="dimmed">
            Solid gold: resultant force. Curved purple: torque. Forces share one
            scale; torques have their own scale.
          </Text>
          <Text size="sm">Arrow scale</Text>
          <Slider
            min={0.25}
            max={3}
            step={0.05}
            value={scale}
            onChange={setScale}
            aria-label="Force arrow scale"
          />
          <Checkbox
            label="Labels on arrows"
            checked={labels}
            onChange={(e) => setLabels(e.currentTarget.checked)}
          />
          <Checkbox
            label="Transparent hardware"
            checked={transparent}
            onChange={(e) => onTransparent(e.currentTarget.checked)}
          />
          {data && bracket && (
            <Accordion variant="separated">
              <Accordion.Item value="values">
                <Accordion.Control>
                  Values at {time.toFixed(2)} s
                </Accordion.Control>
                <Accordion.Panel>
                  <Table fz="xs">
                    <Table.Thead>
                      <Table.Tr>
                        <Table.Th>Contact</Table.Th>
                        <Table.Th>Axial / τ</Table.Th>
                        <Table.Th>Radial</Table.Th>
                        <Table.Th>Tangential</Table.Th>
                      </Table.Tr>
                    </Table.Thead>
                    <Table.Tbody>
                      {tracks
                        .filter((t) => keys.includes(t.key))
                        .map((t) => {
                          const sample = forceAt(t, bracket);
                          return (
                            <Table.Tr key={t.key}>
                              <Table.Td>
                                {t.label} ({t.unit})
                              </Table.Td>
                              {[0, 1, 2].map((i) => (
                                <Table.Td key={i}>
                                  {sample
                                    ? sample.components[i].toFixed(1)
                                    : '—'}
                                </Table.Td>
                              ))}
                            </Table.Tr>
                          );
                        })}
                    </Table.Tbody>
                  </Table>
                </Accordion.Panel>
              </Accordion.Item>
              <Accordion.Item value="conventions">
                <Accordion.Control>Force conventions</Accordion.Control>
                <Accordion.Panel>
                  <Stack gap="xs">
                    {data.notes.map((note) => (
                      <Text size="xs" key={note}>
                        {note}
                      </Text>
                    ))}
                  </Stack>
                </Accordion.Panel>
              </Accordion.Item>
            </Accordion>
          )}
        </Stack>
      </Popover.Dropdown>
    </Popover>
  );
}
