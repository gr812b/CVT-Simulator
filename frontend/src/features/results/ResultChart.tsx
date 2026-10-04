import { useEffect, useMemo, useState } from 'react';
import {
  Alert,
  Group,
  Loader,
  Paper,
  Select,
  Stack,
  Text,
  Title,
  useMantineTheme,
} from '@mantine/core';
import { ActionButton as Button } from '@components/button/ActionButton';
import ReactECharts from 'echarts-for-react';
import type { EChartsOption } from 'echarts';
import { getSeries, type RunInspection, type RunSeries } from './api';
import { message } from '../experiments/api';

export function ResultChart({ inspection }: { inspection: RunInspection }) {
  const { run, availability } = inspection;
  const [full, setFull] = useState(false);
  const [data, setData] = useState<RunSeries | null>(null);
  const [signal, setSignal] = useState('vehicle.speed');
  const [error, setError] = useState<string | null>(null);
  const [retry, setRetry] = useState(0);
  const theme = useMantineTheme();
  const resolution = full || !availability.preview ? 'full' : 'preview';
  useEffect(() => {
    const controller = new AbortController();
    setData(null);
    setError(null);
    void getSeries(run.id, resolution, controller.signal)
      .then((value) => {
        if (!controller.signal.aborted) setData(value);
      })
      .catch((cause) => {
        if (!controller.signal.aborted) setError(message(cause));
      });
    return () => controller.abort();
  }, [run.id, resolution, retry]);
  const available =
    data?.columns.filter((column) => column.key !== data.axis_key) ?? [];
  const selected =
    available.find((column) => column.key === signal) ?? available[0];
  const option = useMemo<EChartsOption>(() => {
    const x = data?.columns.find((column) => column.key === data.axis_key);
    return {
      animation: false,
      color: [theme.colors.red[5]],
      textStyle: { color: theme.colors.dark[0], fontFamily: theme.fontFamily },
      grid: { left: 70, right: 25, top: 55, bottom: 80 },
      legend: { top: 0, textStyle: { color: theme.colors.dark[0] } },
      tooltip: { trigger: 'axis', renderMode: 'richText', confine: true },
      xAxis: {
        type: 'value',
        name: `Time (${x?.canonical_unit ?? 's'})`,
        nameLocation: 'middle',
        nameGap: 30,
        splitLine: { lineStyle: { color: theme.colors.dark[4] } },
      },
      yAxis: {
        type: 'value',
        name: selected?.canonical_unit || 'Dimensionless',
        splitLine: { lineStyle: { color: theme.colors.dark[4] } },
      },
      dataZoom: [
        { type: 'inside' },
        {
          type: 'slider',
          bottom: 0,
          textStyle: { color: theme.colors.dark[1] },
        },
      ],
      series:
        selected && x
          ? [
              {
                type: 'line',
                name: selected.label,
                showSymbol: false,
                connectNulls: false,
                data: x.values.map((time, index) => [
                  time,
                  selected.values[index] ?? null,
                ]),
              },
            ]
          : [],
    };
  }, [data, selected, theme]);
  return (
    <Paper withBorder p="lg">
      <Stack>
        <Group justify="space-between">
          <Title order={2} size="h3">
            Time history
          </Title>
          {availability.full_result && availability.preview && (
            <Button
              variant="default"
              onClick={() => setFull((value) => !value)}
            >
              {full ? 'Show display preview' : 'Load full report data'}
            </Button>
          )}
        </Group>
        <Text size="sm" c="dimmed">
          {resolution === 'preview'
            ? 'Reduced display preview. Short events may be omitted; metrics below come from the stored solver result.'
            : 'All stored report-table samples, including duplicate transition times. This is the reporting grid, not an adaptive solver trace.'}
        </Text>
        {error ? (
          <Alert color="red" role="alert">
            {error}
            <Button
              variant="subtle"
              onClick={() => setRetry((value) => value + 1)}
            >
              Retry chart
            </Button>
          </Alert>
        ) : !data ? (
          <Loader aria-label="Loading time histories" />
        ) : !selected ? (
          <Text>No plottable report columns are available.</Text>
        ) : (
          <>
            <Select
              label="Signal"
              searchable
              value={selected.key}
              data={available.map((column) => ({
                value: column.key,
                label: `${column.label}${column.canonical_unit ? ` (${column.canonical_unit})` : ''}`,
              }))}
              onChange={(value) => value && setSignal(value)}
            />
            <Text size="xs" c="dimmed">
              {data.row_count} displayed / {data.original_row_count} original
              report rows. {selected.description}
            </Text>
            <div
              role="img"
              aria-label={`${selected.label} versus time in seconds. ${data.resolution} data.`}
            >
              <ReactECharts
                option={option}
                notMerge
                style={{ height: 350, width: '100%' }}
              />
            </div>
          </>
        )}
      </Stack>
    </Paper>
  );
}
