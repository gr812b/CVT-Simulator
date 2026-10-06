import type { EChartsOption } from 'echarts';
import { CHART_COLORS } from './chartOptions';

/** Separate rows for tools and series keys; units sit above the plotting area. */
export function compactChartLayout(
  unit: string,
  textColor = CHART_COLORS.TEXT,
): EChartsOption {
  return {
    legend: {
      type: 'scroll',
      top: 34,
      left: 8,
      right: 8,
      tooltip: { show: true },
      pageTextStyle: { color: textColor },
      pageIconColor: textColor,
      textStyle: { color: textColor },
      formatter: (name: string) =>
        name.length > 24 ? `${name.slice(0, 22)}…` : name,
    },
    toolbox: { top: 2, right: 8 },
    grid: { top: 78, left: 10, right: 10, bottom: 30, containLabel: true },
    xAxis: { nameGap: 25 },
    yAxis: {
      name: unit,
      nameLocation: 'end',
      nameRotate: 0,
      nameGap: 9,
      nameTextStyle: { align: 'left' },
    },
  };
}
