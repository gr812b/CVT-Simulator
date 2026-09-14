import { useMemo } from 'react';
import ReactECharts from 'echarts-for-react';
import type { EChartsOption } from 'echarts';
import type { ConcreteDesignResponse } from '@api/primaryDesign';

interface Props {
  response: ConcreteDesignResponse | null;
  shiftM: number;
}

function numericSeries(
  response: ConcreteDesignResponse,
  key: string,
): Array<number | null> {
  return (response.loads.fields[key] ?? []).map((value) =>
    typeof value === 'number' ? value : null);
}

export function ForceChart({ response, shiftM }: Props) {
  const option = useMemo<EChartsOption>(() => {
    if (!response) return {};
    const shift = response.loads.axis_values.map((value) => value * 1000);
    const total = numericSeries(response, 'flyweight_total_closing_force_N');
    const normal = numericSeries(response, 'ramp_force_normal_N');
    const pivot = numericSeries(response, 'pivot_reaction_resultant_N');

    const pair = (values: Array<number | null>) =>
      shift.map((x, index) => [x, values[index]]);

    return {
      animation: false,
      grid: { left: 62, right: 24, top: 36, bottom: 54 },
      tooltip: { trigger: 'axis' },
      legend: { top: 0 },
      xAxis: {
        type: 'value',
        name: 'Primary closure [mm]',
        nameLocation: 'middle',
        nameGap: 34,
      },
      yAxis: {
        type: 'value',
        name: 'Force [N]',
        nameLocation: 'middle',
        nameGap: 48,
      },
      series: [
        {
          name: 'Flyweight closing',
          type: 'line',
          data: pair(total),
          showSymbol: false,
          lineStyle: { width: 3 },
          markLine: {
            silent: true,
            symbol: 'none',
            data: [{ xAxis: shiftM * 1000 }],
            lineStyle: { type: 'dashed', width: 1 },
          },
        },
        {
          name: 'Ramp normal / ramp',
          type: 'line',
          data: pair(normal),
          showSymbol: false,
          lineStyle: { width: 2, type: 'dashed' },
        },
        {
          name: 'Pivot resultant / flyweight',
          type: 'line',
          data: pair(pivot),
          showSymbol: false,
          lineStyle: { width: 2, type: 'dotted' },
        },
      ],
    };
  }, [response, shiftM]);

  if (!response) {
    return <div style={{ minHeight: 340, display: 'grid', placeItems: 'center', opacity: 0.6 }}>Waiting for load response…</div>;
  }
  return <ReactECharts option={option} style={{ width: '100%', height: 350 }} />;
}
