import { useMantineTheme } from '@mantine/core';
import ReactECharts from 'echarts-for-react';

export function ProfileChart({ points, xLabel, yLabel }: {
  points: [number, number][];
  xLabel: string;
  yLabel: string;
}) {
  const theme = useMantineTheme();
  return (
    <ReactECharts
      style={{ height: 230 }} opts={{ renderer: 'svg' }}
      option={{
        animation: false,
        color: [theme.colors[theme.primaryColor][6]],
        grid: { left: 65, right: 25, top: 30, bottom: 50 },
        tooltip: { trigger: 'axis' },
        xAxis: { type: 'value', name: xLabel, nameLocation: 'middle', nameGap: 30 },
        yAxis: { type: 'value', name: yLabel },
        series: [{ type: 'line', data: points, showSymbol: true, symbolSize: 7 }],
      }}
    />
  );
}
