import { useMemo } from 'react';
import ReactECharts from 'echarts-for-react';
import type { EChartsOption } from 'echarts';
import styles from './ValidationXYChart.module.scss';

interface Props {
  title: string;
  xLabel: string;
  yLabel: string;
  measured: Array<[number, number]>;
  simulated?: Array<[number, number]>;
  measuredLabel?: string;
  simulatedLabel?: string;
  note?: string;
}


function tooltipAxisValue(params: unknown): number | null {
  const entries = Array.isArray(params) ? params : [params];
  for (const entry of entries) {
    if (typeof entry !== 'object' || entry === null) continue;
    const axisValue = (entry as { axisValue?: unknown }).axisValue;
    if (typeof axisValue === 'number' && Number.isFinite(axisValue)) return axisValue;
    const data = (entry as { data?: unknown }).data;
    if (Array.isArray(data) && typeof data[0] === 'number' && Number.isFinite(data[0])) return data[0];
  }
  return null;
}

function nearestPointByX(series: Array<[number, number]> | undefined, target: number): [number, number] | null {
  if (series === undefined || series.length === 0) return null;
  let best: [number, number] | null = null;
  let distance = Number.POSITIVE_INFINITY;
  for (const point of series) {
    if (!Number.isFinite(point[0]) || !Number.isFinite(point[1])) continue;
    const candidate = Math.abs(point[0] - target);
    if (candidate < distance) {
      best = point;
      distance = candidate;
    }
  }
  return best;
}

function formatTooltipNumber(value: number | null): string {
  if (value === null || !Number.isFinite(value)) return '—';
  const magnitude = Math.abs(value);
  if (magnitude >= 1000) return value.toFixed(0);
  if (magnitude >= 100) return value.toFixed(1);
  if (magnitude >= 10) return value.toFixed(2);
  return value.toFixed(3);
}

function cssColor(name: string, fallback: string): string {
  if (typeof window === 'undefined') return fallback;
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim() || fallback;
}

export function ValidationXYChart({
  title,
  xLabel,
  yLabel,
  measured,
  simulated,
  measuredLabel = 'Measured',
  simulatedLabel = 'CINDER',
  note,
}: Props) {
  const option = useMemo<EChartsOption>(() => {
    const text = cssColor('--text-color', '#ffffff');
    const grid = cssColor('--grid-color', '#404040');
    const measuredColor = cssColor('--line2', '#2ecc71');
    const simulatedColor = cssColor('--line1', '#bb0808');
    const tooltipBackground = cssColor('--tooltip-bg', '#2a2a2a');
    const tooltipFormatter = (params: unknown): string => {
      const x = tooltipAxisValue(params);
      if (x === null) return '';
      const measuredPoint = nearestPointByX(measured, x);
      const simulatedPoint = nearestPointByX(simulated, x);
      const lines = [`<strong>${xLabel}: ${formatTooltipNumber(x)}</strong>`];
      if (measuredPoint !== null) {
        lines.push(`${measuredLabel}: ${formatTooltipNumber(measuredPoint[1])}`);
      }
      if (simulated !== undefined) {
        lines.push(`${simulatedLabel}: ${formatTooltipNumber(simulatedPoint?.[1] ?? null)}`);
      }
      return lines.join('<br/>');
    };

    const series: Record<string, unknown>[] = [
      {
        name: measuredLabel,
        type: 'line',
        showSymbol: true,
        symbol: 'circle',
        symbolSize: 4,
        itemStyle: { color: measuredColor },
        lineStyle: { color: measuredColor, width: 2 },
        data: measured,
      },
    ];
    if (simulated !== undefined) {
      series.push({
        name: simulatedLabel,
        type: 'line',
        showSymbol: false,
        lineStyle: { color: simulatedColor, width: 2.4 },
        data: simulated,
      });
    }

    return {
      animation: false,
      backgroundColor: 'transparent',
      textStyle: { color: text },
      tooltip: {
        trigger: 'axis',
        backgroundColor: tooltipBackground,
        borderColor: grid,
        textStyle: { color: text },
        axisPointer: { type: 'cross', lineStyle: { color: grid }, snap: false },
        formatter: tooltipFormatter,
      },
      legend: { top: 0, textStyle: { color: text } },
      toolbox: {
        show: true,
        right: 4,
        top: 0,
        feature: {
          dataZoom: { title: { zoom: 'Zoom', back: 'Zoom back' } },
          restore: { title: 'Reset zoom' },
        },
        iconStyle: { borderColor: text },
      },
      grid: { left: 72, right: 32, top: 46, bottom: 60, containLabel: true },
      xAxis: {
        type: 'value',
        name: xLabel,
        nameLocation: 'middle',
        nameGap: 34,
        nameTextStyle: { color: text },
        axisLabel: { color: text },
        axisLine: { lineStyle: { color: grid } },
        axisTick: { lineStyle: { color: grid } },
        splitLine: { lineStyle: { color: grid } },
      },
      yAxis: {
        type: 'value',
        name: yLabel,
        nameLocation: 'middle',
        nameGap: 50,
        nameTextStyle: { color: text },
        axisLabel: { color: text },
        axisLine: { lineStyle: { color: grid } },
        axisTick: { lineStyle: { color: grid } },
        splitLine: { lineStyle: { color: grid } },
      },
      series,
    };
  }, [measured, measuredLabel, simulated, simulatedLabel, xLabel, yLabel]);

  return (
    <section className={styles.card}>
      <div className={styles.heading}>
        <h3>{title}</h3>
        {note !== undefined && <span>{note}</span>}
      </div>
      <ReactECharts option={option} className={styles.chart} notMerge />
    </section>
  );
}
