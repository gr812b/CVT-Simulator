import { useEffect, useMemo, useRef, useState } from 'react';
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
import { isActive, message } from '../experiments/api';

export function ResultChart({ inspection }: { inspection: RunInspection }) {
  const { run, availability } = inspection;
  const [data, setData] = useState<RunSeries | null>(null);
  const [signal, setSignal] = useState('vehicle.speed');
  const [error, setError] = useState<string | null>(null);
  const [retry, setRetry] = useState(0);
  const theme = useMantineTheme();
  const chart = useRef<ReactECharts>(null);
  const zoom = useRef<NonNullable<EChartsOption['dataZoom']> | undefined>(
    undefined,
  );
  const resolution =
    availability.preview && (isActive(run) || !availability.full_result)
      ? 'preview'
      : 'full';
  const checkpoint = availability.full_result_hash;
  useEffect(() => {
    const controller = new AbortController();
    setError(null);
    void getSeries(run.id, resolution, controller.signal)
      .then((value) => {
        if (!controller.signal.aborted) setData(value);
      })
      .catch((cause) => {
        if (!controller.signal.aborted) setError(message(cause));
      });
    return () => controller.abort();
  }, [run.id, resolution, checkpoint, retry]);
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
      grid: { left: 70, right: 25, top: 45, bottom: 45 },
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
      toolbox: {
        feature: { dataZoom: {}, restore: {}, saveAsImage: {} },
        iconStyle: { borderColor: theme.colors.dark[0] },
      },
      dataZoom: zoom.current ?? [
        { type: 'inside', xAxisIndex: 0, filterMode: 'none' },
        { type: 'inside', yAxisIndex: 0, filterMode: 'none' },
      ],
      series:
        selected && x
          ? [
              {
                id: 'selected-signal',
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
          {isActive(run) && (
            <Text size="xs" c="dimmed">
              Updates with saved progress
            </Text>
          )}
        </Group>
        <Text size="sm" c="dimmed">
          {resolution === 'preview' ? 'Live preview' : 'Full report'}
        </Text>
        {error && (
          <Alert color="red" role="alert">
            {error}
            <Button
              variant="subtle"
              onClick={() => setRetry((value) => value + 1)}
            >
              Retry chart
            </Button>
          </Alert>
        )}
        {!data ? (
          !error && <Loader aria-label="Loading time histories" />
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
              onChange={(value) => {
                if (value) {
                  if (Array.isArray(zoom.current))
                    zoom.current = [
                      zoom.current[0],
                      {
                        type: 'inside',
                        yAxisIndex: 0,
                        filterMode: 'none',
                        start: 0,
                        end: 100,
                      },
                    ];
                  setSignal(value);
                }
              }}
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
                ref={chart}
                option={option}
                onEvents={{
                  datazoom: () => {
                    const option = chart.current
                      ?.getEchartsInstance()
                      .getOption() as
                      | {
                          dataZoom?: {
                            start: number;
                            end: number;
                            startValue: number;
                            endValue: number;
                          }[];
                        }
                      | undefined;
                    zoom.current = option?.dataZoom?.map((value, i) => ({
                      type: 'inside',
                      ...(i === 0 ? { xAxisIndex: 0 } : { yAxisIndex: 0 }),
                      filterMode: 'none',
                      ...(value.start === 0 && value.end === 100
                        ? { start: 0, end: 100 }
                        : {
                            startValue: value.startValue,
                            endValue: value.endValue,
                          }),
                    }));
                  },
                  restore: () => {
                    chart.current
                      ?.getEchartsInstance()
                      .dispatchAction({
                        type: 'dataZoom',
                        batch: [0, 1].map((dataZoomIndex) => ({
                          dataZoomIndex,
                          start: 0,
                          end: 100,
                        })),
                      });
                    zoom.current = undefined;
                  },
                }}
                style={{ height: 350, width: '100%' }}
              />
            </div>
          </>
        )}
      </Stack>
    </Paper>
  );
}
