import { useMemo } from 'react';
import ReactECharts from 'echarts-for-react';
import type { EChartsOption } from 'echarts';
import styles from './ValidationTraceChart.module.scss';

interface Props {
  title: string;
  unit: string;
  timeS: number[];
  measured: number[];
  cropStartS: number;
  cropEndS: number;
  onCropChange?: (startS: number, endS: number) => void;
  simulated?: Array<[number, number]>;
  uncertaintyAbsolute?: number;
}

export function ValidationTraceChart({
  title,
  unit,
  timeS,
  measured,
  cropStartS,
  cropEndS,
  onCropChange,
  simulated,
  uncertaintyAbsolute,
}: Props) {
  const minTime = timeS[0] ?? 0;
  const maxTime = timeS[timeS.length - 1] ?? 1;
  const option = useMemo<EChartsOption>(() => {
    const measuredSeries: Record<string, unknown>[] = [
      {
        name: 'Measured',
        type: 'line',
        symbol: 'circle',
        symbolSize: 4,
        showSymbol: true,
        data: timeS.map((time, index) => [time, measured[index]]),
        markArea: {
          silent: true,
          data: [[{ xAxis: cropStartS }, { xAxis: cropEndS }]],
        },
        markLine: {
          silent: true,
          symbol: 'none',
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
          name: 'Measured + uncertainty',
          type: 'line',
          symbol: 'none',
          lineStyle: { opacity: 0.35, type: 'dashed' },
          data: timeS.map((time, index) => [time, measured[index] + uncertaintyAbsolute]),
        },
        {
          name: 'Measured - uncertainty',
          type: 'line',
          symbol: 'none',
          lineStyle: { opacity: 0.35, type: 'dashed' },
          data: timeS.map((time, index) => [time, measured[index] - uncertaintyAbsolute]),
        },
      );
    }
    if (simulated !== undefined) {
      measuredSeries.push({
        name: 'CINDER',
        type: 'line',
        symbol: 'none',
        lineWidth: 2,
        data: simulated,
      });
    }
    return {
      animation: false,
      tooltip: { trigger: 'axis' },
      legend: { top: 0 },
      grid: { left: 62, right: 24, top: 36, bottom: onCropChange === undefined ? 42 : 78 },
      xAxis: { type: 'value', name: 'Elapsed time [s]', min: minTime, max: maxTime },
      yAxis: { type: 'value', name: unit },
      series: measuredSeries,
      ...(onCropChange === undefined ? {} : {
        dataZoom: [
          { type: 'inside', xAxisIndex: 0, filterMode: 'none' },
          {
            type: 'slider',
            xAxisIndex: 0,
            filterMode: 'none',
            startValue: cropStartS,
            endValue: cropEndS,
            bottom: 8,
            height: 26,
            brushSelect: false,
            zoomLock: false,
          },
        ],
      }),
    };
  }, [cropEndS, cropStartS, maxTime, measured, minTime, onCropChange, simulated, timeS, uncertaintyAbsolute, unit]);

  const onEvents = onCropChange === undefined ? undefined : {
    datazoom: (event: {
      start?: number;
      end?: number;
      startValue?: number;
      endValue?: number;
      batch?: Array<{ start?: number; end?: number; startValue?: number; endValue?: number }>;
    }) => {
      const payload = event.batch?.[0] ?? event;
      const span = maxTime - minTime;
      const rawStart = typeof payload.startValue === 'number'
        ? payload.startValue
        : payload.start === undefined ? cropStartS : minTime + span * payload.start / 100;
      const rawEnd = typeof payload.endValue === 'number'
        ? payload.endValue
        : payload.end === undefined ? cropEndS : minTime + span * payload.end / 100;

      const nearest = (target: number) => timeS.reduce((best, value) => (
        Math.abs(value - target) < Math.abs(best - target) ? value : best
      ), timeS[0] ?? target);
      let snappedStart = nearest(rawStart);
      let snappedEnd = nearest(rawEnd);
      const startIndex = timeS.indexOf(snappedStart);
      const endIndex = timeS.indexOf(snappedEnd);

      // A tracking trace and a comparison interval both require at least two
      // measured rows. Preserve the dragged edge and expand by one real sample
      // if the slider collapses onto a single row.
      if (startIndex >= endIndex && timeS.length >= 2) {
        if (startIndex < timeS.length - 1) snappedEnd = timeS[startIndex + 1];
        else snappedStart = timeS[endIndex - 1];
      }
      onCropChange(snappedStart, snappedEnd);
    },
  };

  return (
    <section className={styles.card}>
      <h3>{title}</h3>
      <ReactECharts option={option} onEvents={onEvents} className={styles.chart} notMerge />
    </section>
  );
}
