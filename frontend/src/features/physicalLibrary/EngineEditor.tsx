import { useState } from 'react';
import {
  Accordion,
  ActionIcon,
  Alert,
  Button,
  FileButton,
  Group,
  Modal,
  Select,
  SimpleGrid,
  Stack,
  Text,
  Textarea,
  useMantineTheme,
} from '@mantine/core';
import { IconPlus, IconTrash, IconUpload } from '@tabler/icons-react';
import ReactECharts from 'echarts-for-react';
import { displayScale } from '@utils/units';
import { QuantityInput } from '@components/quantityInput/QuantityInput';
import { importCurve, type EngineData } from './api';

const RPM_PER_RAD_S = displayScale('rpm');

export function EngineEditor({
  value,
  onChange,
  disabled = false,
}: {
  value: EngineData;
  onChange: (value: EngineData) => void;
  disabled?: boolean;
}) {
  const theme = useMantineTheme();
  const [opened, setOpened] = useState(false);
  const [text, setText] = useState('');
  const [units, setUnits] = useState<
    Pick<Parameters<typeof importCurve>[0], 'speed_unit' | 'torque_unit'>
  >({ speed_unit: 'rpm', torque_unit: 'N·m' });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const patch = (changes: Partial<EngineData>) =>
    onChange({ ...value, ...changes });
  const importPoints = async () => {
    setBusy(true);
    setError(null);
    try {
      patch({ points: await importCurve({ text, ...units }) });
      setOpened(false);
    } catch (reason) {
      setError(
        reason instanceof Error
          ? reason.message
          : 'Unable to import this curve.',
      );
    } finally {
      setBusy(false);
    }
  };
  const readFile = async (file: File | null) => {
    if (!file) return;
    if (file.size > 100000) {
      setError('Choose a CSV or text file smaller than 100 KB.');
      return;
    }
    try {
      setText(await file.text());
      setError(null);
    } catch {
      setError('Unable to read this file. Try pasting its contents.');
    }
  };
  return (
    <Stack gap="lg">
      <QuantityInput
        label="Equivalent input inertia"
        value={value.equivalent_rotational_inertia_kg_m2}
        onChange={(next) =>
          patch({ equivalent_rotational_inertia_kg_m2: next })
        }
        unit="kg·m²"
        min={0}
        disabled={disabled}
        description="Engine and other input-side inertia about the primary shaft, excluding the CVT hardware entered separately."
      />
      <div>
        <Group justify="space-between" mb="sm">
          <div>
            <Text fw={600}>Full-throttle torque curve</Text>
            <Text size="sm" c="dimmed">
              Enter speed and shaft torque in ascending speed order.
            </Text>
          </div>
          {!disabled && (
            <Button
              variant="light"
              leftSection={<IconUpload size={16} />}
              onClick={() => setOpened(true)}
            >
              Paste or import CSV
            </Button>
          )}
        </Group>
        <ReactECharts
          style={{ height: 250 }}
          option={{
            animation: false,
            backgroundColor: 'transparent',
            color: [theme.colors.red[4]],
            aria: {
              enabled: true,
              description:
                'Engine torque versus speed. Exact values are editable in the table below.',
            },
            tooltip: { trigger: 'axis' },
            grid: { left: 65, right: 20, bottom: 45, top: 15 },
            xAxis: {
              type: 'value',
              name: 'Speed (rpm)',
              nameLocation: 'middle',
              nameGap: 28,
              axisLabel: { color: theme.colors.dark[1] },
              nameTextStyle: { color: theme.colors.dark[1] },
              splitLine: { lineStyle: { color: theme.colors.dark[5] } },
            },
            yAxis: {
              type: 'value',
              name: 'Torque (N·m)',
              nameLocation: 'middle',
              nameGap: 43,
              axisLabel: { color: theme.colors.dark[1] },
              nameTextStyle: { color: theme.colors.dark[1] },
              splitLine: { lineStyle: { color: theme.colors.dark[5] } },
            },
            series: [
              {
                type: 'line',
                showSymbol: true,
                data: value.points.map((point) => [
                  point.angular_speed_rad_per_s * RPM_PER_RAD_S,
                  point.torque_Nm,
                ]),
              },
            ],
          }}
        />
        <Text size="xs" c="dimmed" mb="sm">
          The plot joins the entered points for inspection. CINDER owns the
          engine-curve interpolation used in simulation.
        </Text>
        <Stack gap="md">
          {value.points.map((point, index) => (
            <Group key={index} align="end" wrap="nowrap">
              <SimpleGrid
                cols={{ base: 1, sm: 2 }}
                style={{ flex: 1, minWidth: 0 }}
              >
                <QuantityInput
                  label={`Speed row ${index + 1}`}
                  value={point.angular_speed_rad_per_s}
                  onChange={(next) =>
                    patch({
                      points: value.points.map((entry, i) =>
                        i === index
                          ? { ...entry, angular_speed_rad_per_s: next }
                          : entry,
                      ),
                    })
                  }
                  unit="rpm"
                  scale={RPM_PER_RAD_S}
                  min={0}
                  disabled={disabled}
                />
                <QuantityInput
                  label={`Torque row ${index + 1}`}
                  value={point.torque_Nm}
                  onChange={(next) =>
                    patch({
                      points: value.points.map((entry, i) =>
                        i === index ? { ...entry, torque_Nm: next } : entry,
                      ),
                    })
                  }
                  unit="N·m"
                  disabled={disabled}
                />
              </SimpleGrid>
              <ActionIcon
                variant="subtle"
                color="red"
                aria-label={`Remove curve row ${index + 1}`}
                disabled={disabled || value.points.length <= 2}
                onClick={() =>
                  patch({
                    points: value.points.filter((_, i) => i !== index),
                  })
                }
              >
                <IconTrash size={16} />
              </ActionIcon>
            </Group>
          ))}
        </Stack>
        {!disabled && (
          <Button
            variant="subtle"
            mt="sm"
            leftSection={<IconPlus size={16} />}
            disabled={value.points.length >= 1000}
            onClick={() =>
              patch({
                points: [
                  ...value.points,
                  {
                    angular_speed_rad_per_s:
                      (value.points.at(-1)?.angular_speed_rad_per_s ?? 0) +
                      500 / RPM_PER_RAD_S,
                    torque_Nm: 0,
                  },
                ],
              })
            }
          >
            Add curve point
          </Button>
        )}
      </div>
      <Accordion variant="separated">
        <Accordion.Item value="advanced">
          <Accordion.Control>Advanced engine braking</Accordion.Control>
          <Accordion.Panel>
            <Text size="sm" c="dimmed" mb="md">
              These values define CINDER’s low- and high-speed extensions to the
              full-throttle curve.
            </Text>
            <SimpleGrid cols={{ base: 1, sm: 2 }}>
              <QuantityInput
                label="Low-speed braking torque"
                unit="N·m"
                value={value.low_speed_braking_torque_Nm}
                disabled={disabled}
                onChange={(next) =>
                  patch({ low_speed_braking_torque_Nm: next })
                }
              />
              <QuantityInput
                label="Low-speed braking peak speed"
                unit="rpm"
                scale={RPM_PER_RAD_S}
                min={0}
                value={value.low_speed_braking_peak_speed_rad_per_s}
                disabled={disabled}
                onChange={(next) =>
                  patch({ low_speed_braking_peak_speed_rad_per_s: next })
                }
              />
              <QuantityInput
                label="High-speed braking torque"
                unit="N·m"
                value={value.high_speed_braking_torque_Nm}
                disabled={disabled}
                onChange={(next) =>
                  patch({ high_speed_braking_torque_Nm: next })
                }
              />
              <QuantityInput
                label="High-speed transition width"
                unit="rpm"
                scale={RPM_PER_RAD_S}
                min={0}
                value={value.high_speed_braking_transition_width_rad_per_s}
                disabled={disabled}
                onChange={(next) =>
                  patch({ high_speed_braking_transition_width_rad_per_s: next })
                }
              />
            </SimpleGrid>
          </Accordion.Panel>
        </Accordion.Item>
      </Accordion>
      <Modal
        opened={opened}
        onClose={() => !busy && setOpened(false)}
        title="Import engine torque curve"
        size="lg"
      >
        <Stack>
          <Text size="sm">
            Paste two columns or choose a CSV/TSV file. A speed/torque header is
            optional. Rows are sorted by speed; duplicate speeds are rejected.
          </Text>
          <SimpleGrid cols={2}>
            <Select
              label="Speed column unit"
              data={['rpm', 'rad/s']}
              value={units.speed_unit}
              allowDeselect={false}
              onChange={(next) =>
                setUnits({
                  ...units,
                  speed_unit: next === 'rad/s' ? 'rad/s' : 'rpm',
                })
              }
            />
            <Select
              label="Torque column unit"
              data={['N·m', 'lb·ft']}
              value={units.torque_unit}
              allowDeselect={false}
              onChange={(next) =>
                setUnits({
                  ...units,
                  torque_unit: next === 'lb·ft' ? 'lb·ft' : 'N·m',
                })
              }
            />
          </SimpleGrid>
          <Textarea
            label="Speed and torque rows"
            value={text}
            onChange={(event) => setText(event.currentTarget.value)}
            autosize
            minRows={7}
            maxRows={16}
            placeholder={'rpm,torque\n1800,24.4\n2400,25.1'}
          />
          {error && (
            <Alert color="red" role="alert">
              {error}
            </Alert>
          )}
          <Group justify="space-between">
            <FileButton
              accept=".csv,.tsv,.txt,text/csv,text/plain"
              onChange={(file) => void readFile(file)}
            >
              {(props) => (
                <Button {...props} variant="default">
                  Choose file
                </Button>
              )}
            </FileButton>
            <Button
              loading={busy}
              disabled={!text.trim()}
              onClick={() => void importPoints()}
            >
              Replace curve
            </Button>
          </Group>
        </Stack>
      </Modal>
    </Stack>
  );
}
