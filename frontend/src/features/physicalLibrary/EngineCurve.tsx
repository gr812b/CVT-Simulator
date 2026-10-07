import { useAuth } from '@contexts/AuthContext';
import { normalizeUnitPreferences, preferredDisplayUnit, siToDisplay } from '@utils/units';
import { lazy, Suspense } from 'react';
import { Center, Loader, useMantineTheme } from '@mantine/core';
import type { EngineData } from './api';

const ReactECharts = lazy(() => import('echarts-for-react'));
export function EngineCurve({ value }: { value: EngineData }) {
  const theme = useMantineTheme();
  const { unitPreferences } = useAuth();
  const preferences = normalizeUnitPreferences(unitPreferences);
  const speedUnit = preferredDisplayUnit('angular_speed', 'hardware', preferences);
  const torqueUnit = preferredDisplayUnit('torque', 'hardware', preferences);
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
            name: `Speed (${speedUnit})`,
            nameLocation: 'middle',
            nameGap: 28,
            axisLabel: { color: theme.colors.dark[1] },
            nameTextStyle: { color: theme.colors.dark[1] },
            splitLine: { lineStyle: { color: theme.colors.dark[5] } },
          },
          yAxis: {
            type: 'value',
            name: `Torque (${torqueUnit})`,
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
                siToDisplay(point.angular_speed_rad_per_s, speedUnit),
                siToDisplay(point.torque_Nm, torqueUnit),
              ]),
            },
          ],
        }}
      />
    </Suspense>
  );
}
