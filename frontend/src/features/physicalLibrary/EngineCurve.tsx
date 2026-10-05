import { lazy, Suspense } from 'react';
import { Center, Loader, useMantineTheme } from '@mantine/core';
import type { EngineData } from './api';

const ReactECharts = lazy(() => import('echarts-for-react'));
const RPM_PER_RAD_S = 30 / Math.PI;
export function EngineCurve({ value }: { value: EngineData }) {
  const theme = useMantineTheme();
  return (
    <Suspense
      fallback={
        <Center h={250}>
          <Loader size="sm" aria-label="Loading torque curve" />
        </Center>
      }
    >
      <ReactECharts
        style={{ height: 250 }}
        option={{
          animation: false,
          backgroundColor: 'transparent',
          color: [theme.colors.red[4]],
          aria: {
            enabled: true,
            description: 'Full-open-throttle torque versus engine speed.',
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
    </Suspense>
  );
}
