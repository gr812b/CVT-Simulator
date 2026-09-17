import { useCallback, useEffect, useMemo, useRef } from 'react';
import ReactECharts from 'echarts-for-react';
import type { EChartsOption } from 'echarts';
import styles from './ValidationTraceChart.module.scss';

interface Props {
  title: string;
  unit: string;
  timeS: number[];
  measured: number[];
  measuredLabel?: string;
  cropStartS: number;
  cropEndS: number;
  onCropChange?: (startS: number, endS: number) => void;
  simulated?: Array<[number, number]>;
  simulatedLabel?: string;
  uncertaintyAbsolute?: number;
}

interface ChartInstance {
  dispatchAction: (payload: Record<string, unknown>) => void;
}

interface BrushArea {
  coordRange?: unknown;
}

interface BrushSelectedEvent {
  batch?: Array<{ areas?: BrushArea[] }>;
}

function cssColor(name: string, fallback: string): string {
  if (typeof window === 'undefined') return fallback;
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim() || fallback;
}


function interpolateSeries(series: Array<[number, number]> | undefined, target: number): number | null {
  if (series === undefined || series.length === 0) return null;
  let previous: [number, number] | null = null;
  for (const point of series) {
    if (!Number.isFinite(point[0]) || !Number.isFinite(point[1])) continue;
    if (point[0] === target) return point[1];
    if (point[0] > target) {
      if (previous === null) return point[1];
      const span = point[0] - previous[0];
      if (span <= 0) return point[1];
      const alpha = (target - previous[0]) / span;
      return previous[1] + alpha * (point[1] - previous[1]);
    }
    previous = point;
  }
  return previous?.[1] ?? null;
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

function formatTooltipNumber(value: number | null): string {
  if (value === null || !Number.isFinite(value)) return '—';
  const magnitude = Math.abs(value);
  if (magnitude >= 1000) return value.toFixed(0);
  if (magnitude >= 100) return value.toFixed(1);
  if (magnitude >= 10) return value.toFixed(2);
  return value.toFixed(3);
}

function rgba(hexOrCss: string, alpha: number): string {
  const hex = hexOrCss.trim();
  if (/^#[0-9a-fA-F]{6}$/.test(hex)) {
    const value = Number.parseInt(hex.slice(1), 16);
    const r = (value >> 16) & 255;
    const g = (value >> 8) & 255;
    const b = value & 255;
    return `rgba(${r}, ${g}, ${b}, ${alpha})`;
  }
  return `color-mix(in srgb, ${hexOrCss} ${Math.round(alpha * 100)}%, transparent)`;
}

export function ValidationTraceChart({
  title,
  unit,
  timeS,
  measured,
  measuredLabel = 'Measured',
  cropStartS,
  cropEndS,
  onCropChange,
  simulated,
  simulatedLabel = 'CINDER',
  uncertaintyAbsolute,
}: Props) {
  const minTime = timeS[0] ?? 0;
  const maxTime = timeS[timeS.length - 1] ?? 1;
  const chartRef = useRef<ChartInstance | null>(null);
  const pendingBrushRangeRef = useRef<[number, number] | null>(null);

  const nearestSample = useCallback((target: number): number => {
    let best = timeS[0] ?? target;
    let bestDistance = Math.abs(best - target);
    for (const value of timeS) {
      const distance = Math.abs(value - target);
      if (distance < bestDistance) {
        best = value;
        bestDistance = distance;
      }
    }
    return best;
  }, [timeS]);

  const activateSelection = useCallback((instance: ChartInstance, syncArea: boolean) => {
    if (onCropChange === undefined) return;
    if (syncArea) {
      instance.dispatchAction({
        type: 'brush',
        areas: [{
          brushType: 'lineX',
          xAxisIndex: 0,
          coordRange: [cropStartS, cropEndS],
        }],
      });
    }
    instance.dispatchAction({
      type: 'takeGlobalCursor',
      key: 'brush',
      brushOption: { brushType: 'lineX', brushMode: 'single' },
    });
  }, [cropEndS, cropStartS, onCropChange]);

  useEffect(() => {
    if (chartRef.current !== null) activateSelection(chartRef.current, true);
  }, [activateSelection]);

  const option = useMemo<EChartsOption>(() => {
    const text = cssColor('--text-color', '#ffffff');
    const grid = cssColor('--grid-color', '#404040');
    const primary = cssColor('--primary', '#bb0808');
    const measuredColor = cssColor('--line2', '#2ecc71');
    const simulatedColor = cssColor('--line1', '#bb0808');
    const tooltipBackground = cssColor('--tooltip-bg', '#2a2a2a');
    const measuredPoints = timeS.map((time, index): [number, number] => [time, measured[index]]);
    const tooltipFormatter = (params: unknown): string => {
      const time = tooltipAxisValue(params);
      if (time === null) return '';
      const measuredValue = interpolateSeries(measuredPoints, time);
      const simulatedValue = interpolateSeries(simulated, time);
      const lines = [
        `<strong>${time.toFixed(3)} s</strong>`,
        `${measuredLabel}: ${formatTooltipNumber(measuredValue)} ${unit}`,
      ];
      if (simulated !== undefined) {
        lines.push(`${simulatedLabel}: ${formatTooltipNumber(simulatedValue)} ${unit}`);
      }
      if (uncertaintyAbsolute !== undefined && uncertaintyAbsolute > 0) {
        lines.push(`Uncertainty: ±${formatTooltipNumber(uncertaintyAbsolute)} ${unit}`);
      }
      return lines.join('<br/>');
    };

    const measuredSeries: Record<string, unknown>[] = [
      {
        name: measuredLabel,
        type: 'line',
        symbol: 'circle',
        symbolSize: 4,
        showSymbol: true,
        itemStyle: { color: measuredColor },
        lineStyle: { color: measuredColor, width: 2 },
        data: measuredPoints,
        markLine: onCropChange === undefined ? undefined : {
          silent: true,
          symbol: 'none',
          label: { color: text, formatter: '{b}' },
          lineStyle: { color: primary, width: 1.25, type: 'dashed' },
          data: [
            { name: 'Start', xAxis: cropStartS },
            { name: 'End', xAxis: cropEndS },
          ],
        },
      },
    ];
    if (uncertaintyAbsolute !== undefined && uncertaintyAbsolute > 0) {
      measuredSeries.push(
        {
          name: `${measuredLabel} + uncertainty`,
          type: 'line',
          symbol: 'none',
          lineStyle: { color: measuredColor, opacity: 0.45, type: 'dashed' },
          data: timeS.map((time, index) => [time, measured[index] + uncertaintyAbsolute]),
        },
        {
          name: `${measuredLabel} - uncertainty`,
          type: 'line',
          symbol: 'none',
          lineStyle: { color: measuredColor, opacity: 0.45, type: 'dashed' },
          data: timeS.map((time, index) => [time, measured[index] - uncertaintyAbsolute]),
        },
      );
    }
    if (simulated !== undefined) {
      measuredSeries.push({
        name: simulatedLabel,
        type: 'line',
        symbol: 'none',
        lineStyle: { color: simulatedColor, width: 2.4 },
        data: simulated,
      });
    }

    return {
      animation: false,
      backgroundColor: 'transparent',
      textStyle: { color: text },
      color: [measuredColor, simulatedColor],
      tooltip: {
        trigger: 'axis',
        backgroundColor: tooltipBackground,
        borderColor: grid,
        textStyle: { color: text },
        axisPointer: { lineStyle: { color: grid }, snap: false },
        formatter: tooltipFormatter,
      },
      legend: { top: 0, textStyle: { color: text } },
      toolbox: {
        show: true,
        right: 4,
        top: 0,
        feature: {
          dataZoom: { yAxisIndex: 'none', title: { zoom: 'Zoom', back: 'Zoom back' } },
          restore: { title: 'Reset zoom' },
        },
        iconStyle: { borderColor: text },
        emphasis: { iconStyle: { borderColor: primary } },
      },
      grid: { left: 64, right: 32, top: 46, bottom: 54, containLabel: true },
      xAxis: {
        type: 'value',
        name: 'Elapsed time [s]',
        nameLocation: 'middle',
        nameGap: 32,
        min: minTime,
        max: maxTime,
        nameTextStyle: { color: text },
        axisLabel: { color: text },
        axisLine: { lineStyle: { color: grid } },
        axisTick: { lineStyle: { color: grid } },
        splitLine: { lineStyle: { color: grid } },
      },
      yAxis: {
        type: 'value',
        name: unit,
        nameLocation: 'middle',
        nameGap: 46,
        nameTextStyle: { color: text },
        axisLabel: { color: text },
        axisLine: { lineStyle: { color: grid } },
        axisTick: { lineStyle: { color: grid } },
        splitLine: { lineStyle: { color: grid } },
      },
      brush: onCropChange === undefined ? undefined : {
        toolbox: [],
        xAxisIndex: 0,
        brushMode: 'single',
        transformable: true,
        removeOnClick: false,
        throttleType: 'debounce',
        throttleDelay: 40,
        brushStyle: {
          borderWidth: 1.5,
          borderColor: primary,
          color: rgba(primary, 0.14),
        },
      },
      series: measuredSeries,
    };
  }, [cropEndS, cropStartS, maxTime, measured, measuredLabel, minTime, onCropChange, simulated, simulatedLabel, timeS, uncertaintyAbsolute, unit]);

  const commitPendingBrush = useCallback(() => {
    if (onCropChange === undefined || pendingBrushRangeRef.current === null) return;
    const [rawStart, rawEnd] = pendingBrushRangeRef.current;
    pendingBrushRangeRef.current = null;
    let snappedStart = nearestSample(Math.min(rawStart, rawEnd));
    let snappedEnd = nearestSample(Math.max(rawStart, rawEnd));
    const startIndex = timeS.indexOf(snappedStart);
    const endIndex = timeS.indexOf(snappedEnd);
    if (startIndex >= endIndex && timeS.length >= 2) {
      if (startIndex < timeS.length - 1) snappedEnd = timeS[startIndex + 1];
      else snappedStart = timeS[Math.max(0, endIndex - 1)];
    }
    if (snappedStart !== cropStartS || snappedEnd !== cropEndS) {
      onCropChange(snappedStart, snappedEnd);
    }
  }, [cropEndS, cropStartS, nearestSample, onCropChange, timeS]);

  const onEvents = onCropChange === undefined ? undefined : {
    brushselected: (event: BrushSelectedEvent) => {
      const range = event.batch?.[0]?.areas?.[0]?.coordRange;
      if (!Array.isArray(range) || range.length < 2 || typeof range[0] !== 'number' || typeof range[1] !== 'number') return;
      pendingBrushRangeRef.current = [range[0], range[1]];
    },
    // ECharts documents this interaction event as brushEnd.  Register the
    // lower-case alias as well because generic event adapters commonly
    // normalize ECharts event names before subscribing.
    brushEnd: commitPendingBrush,
    brushend: commitPendingBrush,
    datazoom: () => {
      // Zoom is a separate viewing operation.  Once it finishes, direct dragging
      // on the plot returns to selecting the validation interval.
      window.setTimeout(() => {
        if (chartRef.current !== null) activateSelection(chartRef.current, false);
      }, 0);
    },
    restore: () => {
      window.setTimeout(() => {
        if (chartRef.current !== null) activateSelection(chartRef.current, true);
      }, 0);
    },
  };

  return (
    <section className={styles.card}>
      <div className={styles.heading}>
        <h3>{title}</h3>
        {onCropChange !== undefined && <span>Drag across the plot to select data · toolbar zoom is view-only</span>}
      </div>
      <ReactECharts
        option={option}
        onEvents={onEvents}
        onChartReady={(instance) => {
          chartRef.current = instance as ChartInstance;
          activateSelection(instance as ChartInstance, true);
        }}
        className={styles.chart}
        notMerge
      />
    </section>
  );
}
